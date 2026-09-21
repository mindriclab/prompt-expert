"""Prompt-Bibliothek: suchen, markieren, exportieren, löschen.

Die Routen sind bewusst synchron: ``sqlite3`` blockiert, und FastAPI schiebt
``def``-Handler in den Threadpool. Die Abfragen sind lokal und winzig.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Query, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ValidationError

from app.core.errors import AppError
from app.core.settings_store import get_store
from app.models.compose import ComposeMode, VideoSource
from app.models.library import (
    ExportRequest,
    ImportResult,
    LibraryEntry,
    LibraryPage,
    LibraryStats,
    LibraryUpdate,
)
from app.services.library import get_library
from app.services.library_export import MEDIA_TYPES, filename, render

router = APIRouter(prefix="/library", tags=["library"])

#: Obergrenze je Ausfuhr. Schuetzt vor einem versehentlichen Komplettexport im Megabyte-Bereich.
MAX_EXPORT = 2000
#: Obergrenze fuer eine Einfuhr. Eine Sicherung dieser Groesse ist schon ungewoehnlich.
MAX_IMPORT_MB = 64


class DeletedResponse(BaseModel):
    deleted: int


@router.get("", response_model=LibraryPage)
def search_library(
    query: str = "",
    favorite: bool | None = None,
    mode: ComposeMode | None = None,
    video_source: VideoSource | None = None,
    profile_id: str | None = None,
    tag: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> LibraryPage:
    return get_library().search(
        query=query,
        favorite=favorite,
        mode=mode,
        video_source=video_source,
        profile_id=profile_id,
        tag=tag,
        limit=limit,
        offset=offset,
    )


@router.get("/stats", response_model=LibraryStats)
def library_stats() -> LibraryStats:
    return get_library().stats()


@router.get("/{entry_id}", response_model=LibraryEntry)
def read_entry(entry_id: int) -> LibraryEntry:
    return get_library().get(entry_id)


@router.patch("/{entry_id}", response_model=LibraryEntry)
def update_entry(entry_id: int, body: LibraryUpdate) -> LibraryEntry:
    if body.favorite is None and body.tags is None:
        raise AppError("validation_error", "Es wurde nichts zum Ändern übergeben.")
    return get_library().set_fields(entry_id, favorite=body.favorite, tags=body.tags)


@router.delete("/{entry_id}", response_model=DeletedResponse)
def delete_entry(entry_id: int) -> DeletedResponse:
    if not get_library().delete(entry_id):
        raise AppError(
            "not_found",
            f"Den Bibliothekseintrag {entry_id} gibt es nicht (mehr).",
            status_code=404,
        )
    return DeletedResponse(deleted=1)


@router.delete("", response_model=DeletedResponse)
def clear_library(confirm: bool = False) -> DeletedResponse:
    """Komplett leeren. Ohne ``confirm=true`` passiert nichts."""
    if not confirm:
        raise AppError(
            "validation_error",
            "Das Leeren der Bibliothek muss ausdrücklich bestätigt werden.",
        )
    return DeletedResponse(deleted=get_library().clear())


@router.get("/{entry_id}/thumb/{position}")
def entry_thumb(entry_id: int, position: int) -> FileResponse:
    return FileResponse(
        get_library().thumb_file(entry_id, position),
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=86400"},
    )


@router.post("/export")
def export_entries(body: ExportRequest) -> Response:
    library = get_library()
    if body.ids:
        if len(body.ids) > MAX_EXPORT:
            raise AppError(
                "validation_error",
                f"Höchstens {MAX_EXPORT} Einträge auf einmal.",
            )
        entries = library.entries_by_ids(body.ids)
    else:
        page = library.search(limit=MAX_EXPORT)
        entries = library.entries_by_ids([item.id for item in page.items])

    if not entries:
        raise AppError("not_found", "Es gibt nichts zu exportieren.", status_code=404)

    name = filename(body.format, len(entries))
    return Response(
        content=render(entries, body.format),
        media_type=MEDIA_TYPES[body.format],
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.post("/import", response_model=ImportResult)
async def import_entries(file: UploadFile) -> ImportResult:
    """Eine JSON-Sicherung einlesen, die dieser Export erzeugt hat."""
    raw = await file.read()
    if len(raw) > MAX_IMPORT_MB * 1024 * 1024:
        raise AppError(
            "validation_error",
            f"Die Datei ist größer als {MAX_IMPORT_MB} MB. Das ist keine Bibliothekssicherung.",
        )
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AppError(
            "validation_error",
            "Die Datei ist kein gültiges JSON. Erwartet wird eine Sicherung aus dem Export.",
        ) from exc

    rows = payload.get("entries") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise AppError(
            "validation_error",
            "In der Datei steht keine Liste von Einträgen. "
            "Erwartet wird eine Sicherung aus dem Export dieser App.",
        )

    entries: list[LibraryEntry] = []
    unreadable = 0
    for row in rows:
        try:
            entries.append(LibraryEntry.model_validate(row))
        except ValidationError:
            unreadable += 1
    if not entries:
        raise AppError(
            "validation_error",
            "Kein einziger Eintrag in der Datei war lesbar.",
        )

    _, _, max_entries = library_settings()
    # sqlite3 blockiert - das gehoert nicht in den Event-Loop.
    imported, skipped = await asyncio.to_thread(
        get_library().import_entries, entries, max_entries=max_entries
    )

    notes: list[str] = []
    if skipped:
        notes.append(f"{skipped} war(en) schon vorhanden")
    if unreadable:
        notes.append(f"{unreadable} Eintrag/Einträge waren nicht lesbar")
    notes.append("Vorschaubilder sind in einer Sicherung nicht enthalten")
    return ImportResult(imported=imported, skipped=skipped, note=" · ".join(notes))


def library_settings() -> tuple[bool, bool, int]:
    """(aktiv, Thumbnails, Obergrenze) aus den Settings."""
    library = get_store().load().library
    return library.enabled, library.store_thumbnails, library.max_entries
