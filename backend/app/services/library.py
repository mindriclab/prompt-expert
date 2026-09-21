"""Prompt-Bibliothek auf SQLite (stdlib ``sqlite3``).

Bewusst **ohne FTS5**: bei einigen tausend Einträgen auf einem lokalen Rechner ist
``LIKE`` sofort fertig, und die App bleibt unabhängig davon, mit welchen Optionen
das SQLite der jeweiligen Python-Installation gebaut wurde.

Die Prompttexte stehen in eigenen Spalten, alles Strukturierte (Varianten, Analyse,
SceneSpec) als JSON in ``payload``. So bleibt die Suche einfach und das Schema stabil,
auch wenn die Pipeline später weitere Felder liefert.
"""

from __future__ import annotations

import json
import logging
import shutil
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from app.core.errors import AppError
from app.core.paths import library_file, thumbs_dir
from app.models.compose import ComposeRequest, ComposeResponse, PromptBundle, PromptCritique
from app.models.library import (
    LibraryEntry,
    LibraryListItem,
    LibraryPage,
    LibraryStats,
    LibraryThumb,
    derive_title,
    normalise_tags,
)
from app.models.scene import SceneSpec
from app.services.images import thumb_source_path

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at    TEXT    NOT NULL,
    mode          TEXT    NOT NULL,
    intent        TEXT    NOT NULL,
    video_source  TEXT    NOT NULL,
    profile_id    TEXT    NOT NULL,
    profile_label TEXT    NOT NULL,
    language      TEXT    NOT NULL,
    density       TEXT    NOT NULL,
    aspect_ratio  TEXT    NOT NULL,
    clip_seconds  INTEGER,
    model         TEXT    NOT NULL,
    vision_model  TEXT,
    input_prompt  TEXT    NOT NULL DEFAULT '',
    briefing      TEXT    NOT NULL DEFAULT '',
    title         TEXT    NOT NULL,
    favorite      INTEGER NOT NULL DEFAULT 0,
    variant_count INTEGER NOT NULL DEFAULT 0,
    char_count    INTEGER NOT NULL DEFAULT 0,
    duration_ms   INTEGER NOT NULL DEFAULT 0,
    search_text   TEXT    NOT NULL DEFAULT '',
    payload       TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS entries_created ON entries (created_at DESC);
CREATE INDEX IF NOT EXISTS entries_favorite ON entries (favorite);

CREATE TABLE IF NOT EXISTS tags (
    entry_id INTEGER NOT NULL REFERENCES entries (id) ON DELETE CASCADE,
    tag      TEXT    NOT NULL,
    PRIMARY KEY (entry_id, tag)
);

CREATE INDEX IF NOT EXISTS tags_tag ON tags (tag);

CREATE TABLE IF NOT EXISTS thumbs (
    entry_id INTEGER NOT NULL REFERENCES entries (id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    role     TEXT    NOT NULL,
    file     TEXT    NOT NULL,
    PRIMARY KEY (entry_id, position)
);
"""


class LibraryStore:
    """Alle Zugriffe auf ``library.db``. Verbindungen sind kurzlebig und je Aufruf neu."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._ready_for: Path | None = None

    @property
    def path(self) -> Path:
        return self._path or library_file()

    # -- Verbindung ---------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        path = self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    @contextmanager
    def _session(self) -> Iterator[sqlite3.Connection]:
        """Transaktion **und** Schliessen.

        ``with sqlite3.connect(...)`` beendet nur die Transaktion - die Verbindung
        bliebe offen, das WAL-Journal unaufgeraeumt und unter Windows die Datei
        gesperrt.
        """
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def ensure_schema(self) -> None:
        path = self.path
        with self._lock:
            if self._ready_for == path:
                return
            with self._session() as connection:
                connection.executescript(SCHEMA)
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            self._ready_for = path

    def invalidate(self) -> None:
        """Nur fuer Tests: erzwingt beim naechsten Zugriff ein neues Schema."""
        with self._lock:
            self._ready_for = None

    # -- Schreiben ----------------------------------------------------------

    def remember(
        self,
        request: ComposeRequest,
        result: ComposeResponse,
        *,
        store_thumbnails: bool = True,
        max_entries: int = 5000,
    ) -> int:
        """Einen abgeschlossenen Lauf ablegen. Gibt die neue Kennung zurück."""
        self.ensure_schema()
        row = _row_from_result(request, result)

        with self._session() as connection:
            entry_id = _insert(connection, row)
            if store_thumbnails:
                self._copy_thumbs(connection, entry_id, request)

        removed = self.prune(max_entries)
        log.info(
            "Bibliothek: Lauf %d abgelegt (%s, %s, %d Varianten)%s",
            entry_id,
            result.mode,
            result.profile_id,
            len(result.bundles),
            f", {removed} alte Einträge entfernt" if removed else "",
        )
        return entry_id

    def import_entries(
        self, entries: list[LibraryEntry], *, max_entries: int = 5000
    ) -> tuple[int, int]:
        """Einträge aus einer JSON-Sicherung übernehmen.

        Kennungen werden neu vergeben - die alten könnten kollidieren. Einträge,
        die schon da sind, werden übersprungen statt verdoppelt; erkannt an
        Zeitpunkt, Modus, Profil und Kurzzeile.
        """
        self.ensure_schema()
        imported = 0
        skipped = 0

        with self._session() as connection:
            for entry in entries:
                existing = connection.execute(
                    "SELECT 1 FROM entries WHERE created_at = ? AND mode = ? "
                    "AND profile_id = ? AND title = ?",
                    (entry.created_at, entry.mode, entry.profile_id, entry.title),
                ).fetchone()
                if existing is not None:
                    skipped += 1
                    continue
                entry_id = _insert(connection, _row_from_entry(entry))
                connection.executemany(
                    "INSERT OR IGNORE INTO tags (entry_id, tag) VALUES (?, ?)",
                    [(entry_id, tag) for tag in normalise_tags(entry.tags)],
                )
                if entry.favorite:
                    connection.execute(
                        "UPDATE entries SET favorite = 1 WHERE id = ?", (entry_id,)
                    )
                imported += 1

        removed = self.prune(max_entries)
        log.info(
            "Bibliothek: %d Einträge importiert, %d übersprungen%s",
            imported,
            skipped,
            f", {removed} alte entfernt" if removed else "",
        )
        return imported, skipped

    def _copy_thumbs(
        self, connection: sqlite3.Connection, entry_id: int, request: ComposeRequest
    ) -> None:
        """Vorschaubilder in die Bibliothek kopieren.

        Muss kopieren, nicht verweisen: die Uploads werden beim Start nach 24 Stunden
        aufgeräumt, ein Bibliothekseintrag soll das überleben.
        """
        target_dir = thumbs_dir()
        for position, reference in enumerate(request.references):
            try:
                source = thumb_source_path(reference.id)
                if source is None:
                    continue
                name = f"{entry_id}_{position}.jpg"
                shutil.copyfile(source, target_dir / name)
            except OSError as exc:
                log.warning("Bibliothek: Vorschaubild %s nicht kopiert (%s)", reference.id, exc)
                continue
            connection.execute(
                "INSERT OR REPLACE INTO thumbs (entry_id, position, role, file) VALUES (?,?,?,?)",
                (entry_id, position, reference.role, name),
            )

    def set_fields(
        self, entry_id: int, *, favorite: bool | None = None, tags: list[str] | None = None
    ) -> LibraryEntry:
        self.ensure_schema()
        with self._session() as connection:
            if not _exists(connection, entry_id):
                raise _not_found(entry_id)
            if favorite is not None:
                connection.execute(
                    "UPDATE entries SET favorite = ? WHERE id = ?",
                    (1 if favorite else 0, entry_id),
                )
            if tags is not None:
                connection.execute("DELETE FROM tags WHERE entry_id = ?", (entry_id,))
                connection.executemany(
                    "INSERT INTO tags (entry_id, tag) VALUES (?, ?)",
                    [(entry_id, tag) for tag in normalise_tags(tags)],
                )
        return self.get(entry_id)

    # -- Lesen --------------------------------------------------------------

    def get(self, entry_id: int) -> LibraryEntry:
        self.ensure_schema()
        with self._session() as connection:
            row = connection.execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
            if row is None:
                raise _not_found(entry_id)
            tags = _tags_for(connection, [entry_id])
            thumbs = _thumbs_for(connection, [entry_id])
        return _to_entry(row, tags.get(entry_id, []), thumbs.get(entry_id, []))

    def search(
        self,
        *,
        query: str = "",
        favorite: bool | None = None,
        mode: str | None = None,
        video_source: str | None = None,
        profile_id: str | None = None,
        tag: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> LibraryPage:
        self.ensure_schema()
        where: list[str] = []
        params: list[object] = []

        if query.strip():
            needle = f"%{query.strip().lower()}%"
            where.append(
                "(search_text LIKE ? OR id IN (SELECT entry_id FROM tags WHERE tag LIKE ?))"
            )
            params += [needle, needle]
        if favorite is not None:
            where.append("favorite = ?")
            params.append(1 if favorite else 0)
        if mode:
            where.append("mode = ?")
            params.append(mode)
        if video_source:
            # Nur im Videomodus gefuellt - sonst steht dort der unbenutzte Standardwert.
            where.append("mode = 'video' AND video_source = ?")
            params.append(video_source)
        if profile_id:
            where.append("profile_id = ?")
            params.append(profile_id)
        if tag:
            where.append("id IN (SELECT entry_id FROM tags WHERE tag = ?)")
            params.append(tag.strip().lower())

        clause = f" WHERE {' AND '.join(where)}" if where else ""
        with self._session() as connection:
            total = int(
                connection.execute(
                    f"SELECT COUNT(*) FROM entries{clause}", params
                ).fetchone()[0]
            )
            rows = connection.execute(
                f"SELECT * FROM entries{clause} ORDER BY id DESC LIMIT ? OFFSET ?",
                [*params, limit, offset],
            ).fetchall()
            ids = [int(row["id"]) for row in rows]
            tags = _tags_for(connection, ids)
            thumbs = _thumbs_for(connection, ids)

        return LibraryPage(
            items=[
                _to_item(row, tags.get(int(row["id"]), []), thumbs.get(int(row["id"]), []))
                for row in rows
            ],
            total=total,
            offset=offset,
            limit=limit,
        )

    def entries_by_ids(self, ids: list[int]) -> list[LibraryEntry]:
        """Für den Export. Reihenfolge wie in der Liste: neueste zuerst."""
        self.ensure_schema()
        if not ids:
            return []
        marks = ",".join("?" for _ in ids)
        with self._session() as connection:
            rows = connection.execute(
                f"SELECT * FROM entries WHERE id IN ({marks}) ORDER BY id DESC", ids
            ).fetchall()
            found = [int(row["id"]) for row in rows]
            tags = _tags_for(connection, found)
            thumbs = _thumbs_for(connection, found)
        return [
            _to_entry(row, tags.get(int(row["id"]), []), thumbs.get(int(row["id"]), []))
            for row in rows
        ]

    def stats(self) -> LibraryStats:
        self.ensure_schema()
        with self._session() as connection:
            count, favorites = connection.execute(
                "SELECT COUNT(*), COALESCE(SUM(favorite), 0) FROM entries"
            ).fetchone()
            tags = [
                str(row[0])
                for row in connection.execute(
                    "SELECT tag, COUNT(*) AS n FROM tags GROUP BY tag ORDER BY n DESC, tag LIMIT 40"
                ).fetchall()
            ]
        size = self.path.stat().st_size if self.path.is_file() else 0
        return LibraryStats(
            count=int(count), favorites=int(favorites), tags=tags, bytes_on_disk=size
        )

    def thumb_file(self, entry_id: int, position: int) -> Path:
        self.ensure_schema()
        with self._session() as connection:
            row = connection.execute(
                "SELECT file FROM thumbs WHERE entry_id = ? AND position = ?",
                (entry_id, position),
            ).fetchone()
        if row is None:
            raise AppError("not_found", "Dieses Vorschaubild gibt es nicht.", status_code=404)
        path = thumbs_dir() / str(row["file"])
        if not path.is_file():
            raise AppError("not_found", "Dieses Vorschaubild gibt es nicht mehr.", status_code=404)
        return path

    # -- Loeschen -----------------------------------------------------------

    def delete(self, entry_id: int) -> bool:
        self.ensure_schema()
        with self._session() as connection:
            files = [
                str(row["file"])
                for row in connection.execute(
                    "SELECT file FROM thumbs WHERE entry_id = ?", (entry_id,)
                ).fetchall()
            ]
            cursor = connection.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
            removed = cursor.rowcount > 0
        _remove_files(files)
        return removed

    def clear(self) -> int:
        """Alles löschen - Einträge, Tags und die kopierten Vorschaubilder."""
        self.ensure_schema()
        with self._session() as connection:
            files = [
                str(row["file"])
                for row in connection.execute("SELECT file FROM thumbs").fetchall()
            ]
            count = int(connection.execute("SELECT COUNT(*) FROM entries").fetchone()[0])
            connection.execute("DELETE FROM entries")
            connection.execute("DELETE FROM sqlite_sequence WHERE name = 'entries'")
        _remove_files(files)
        log.info("Bibliothek: %d Einträge gelöscht", count)
        return count

    def prune(self, max_entries: int) -> int:
        """Über dem Limit fallen die ältesten Einträge - Favoriten nie."""
        self.ensure_schema()
        with self._session() as connection:
            total = int(connection.execute("SELECT COUNT(*) FROM entries").fetchone()[0])
            surplus = total - max_entries
            if surplus <= 0:
                return 0
            rows = connection.execute(
                "SELECT id FROM entries WHERE favorite = 0 ORDER BY id ASC LIMIT ?",
                (surplus,),
            ).fetchall()
            ids = [int(row["id"]) for row in rows]
            if not ids:
                return 0
            marks = ",".join("?" for _ in ids)
            files = [
                str(row["file"])
                for row in connection.execute(
                    f"SELECT file FROM thumbs WHERE entry_id IN ({marks})", ids
                ).fetchall()
            ]
            connection.execute(f"DELETE FROM entries WHERE id IN ({marks})", ids)
        _remove_files(files)
        return len(ids)


# -- Hilfen ----------------------------------------------------------------


#: Spaltenreihenfolge des INSERT. Einmal definiert, zweimal benutzt: Lauf und Import.
_COLUMNS = (
    "created_at",
    "mode",
    "intent",
    "video_source",
    "profile_id",
    "profile_label",
    "language",
    "density",
    "aspect_ratio",
    "clip_seconds",
    "model",
    "vision_model",
    "input_prompt",
    "briefing",
    "title",
    "variant_count",
    "char_count",
    "duration_ms",
    "search_text",
    "payload",
)


def _insert(connection: sqlite3.Connection, row: dict[str, object]) -> int:
    marks = ",".join("?" for _ in _COLUMNS)
    cursor = connection.execute(
        f"INSERT INTO entries ({','.join(_COLUMNS)}, favorite) VALUES ({marks}, 0)",
        [row[column] for column in _COLUMNS],
    )
    return int(cursor.lastrowid or 0)


def _payload(shots, critique, scene, bundles) -> str:
    return json.dumps(
        {
            "shots": list(shots),
            "critique": critique.model_dump() if critique else None,
            "scene": scene.model_dump() if scene else None,
            "bundles": [bundle.model_dump() for bundle in bundles],
        },
        ensure_ascii=False,
    )


def _row_from_result(request: ComposeRequest, result: ComposeResponse) -> dict[str, object]:
    return {
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "mode": result.mode,
        "intent": result.intent,
        "video_source": result.video_source,
        "profile_id": result.profile_id,
        "profile_label": result.profile_label,
        "language": result.language,
        "density": result.density,
        "aspect_ratio": result.aspect_ratio,
        "clip_seconds": result.clip_seconds,
        "model": result.model,
        "vision_model": result.vision_model,
        "input_prompt": request.input_prompt,
        "briefing": request.briefing,
        "title": derive_title(request.briefing, request.input_prompt, result.bundles),
        "variant_count": len(result.bundles),
        "char_count": max((bundle.char_count for bundle in result.bundles), default=0),
        "duration_ms": result.duration_ms,
        "search_text": _search_text(
            request.briefing,
            request.input_prompt,
            result.profile_label,
            result.profile_id,
            result.bundles,
        ),
        "payload": _payload(result.shots, result.critique, result.scene, result.bundles),
    }


def _row_from_entry(entry: LibraryEntry) -> dict[str, object]:
    """Aus einer JSON-Sicherung. Vorschaubilder stehen darin nicht drin."""
    return {
        "created_at": entry.created_at,
        "mode": entry.mode,
        "intent": entry.intent,
        "video_source": entry.video_source,
        "profile_id": entry.profile_id,
        "profile_label": entry.profile_label,
        "language": entry.language,
        "density": entry.density,
        "aspect_ratio": entry.aspect_ratio,
        "clip_seconds": entry.clip_seconds,
        "model": entry.model,
        "vision_model": entry.vision_model,
        "input_prompt": entry.input_prompt,
        "briefing": entry.briefing,
        "title": entry.title or derive_title(entry.briefing, entry.input_prompt, entry.bundles),
        "variant_count": len(entry.bundles),
        "char_count": max((bundle.char_count for bundle in entry.bundles), default=0),
        "duration_ms": entry.duration_ms,
        "search_text": _search_text(
            entry.briefing,
            entry.input_prompt,
            entry.profile_label,
            entry.profile_id,
            entry.bundles,
        ),
        "payload": _payload(entry.shots, entry.critique, entry.scene, entry.bundles),
    }


def _search_text(
    briefing: str,
    input_prompt: str,
    profile_label: str,
    profile_id: str,
    bundles: list[PromptBundle],
) -> str:
    """Alles Durchsuchbare in einer Spalte, klein geschrieben."""
    parts = [briefing, input_prompt, profile_label, profile_id]
    for bundle in bundles:
        parts += [bundle.main_prompt, bundle.negative_prompt or "", bundle.camera_notes or ""]
    return "\n".join(part for part in parts if part).lower()


def _exists(connection: sqlite3.Connection, entry_id: int) -> bool:
    row = connection.execute("SELECT 1 FROM entries WHERE id = ?", (entry_id,)).fetchone()
    return row is not None


def _not_found(entry_id: int) -> AppError:
    return AppError(
        "not_found",
        f"Den Bibliothekseintrag {entry_id} gibt es nicht (mehr).",
        status_code=404,
    )


def _tags_for(connection: sqlite3.Connection, ids: list[int]) -> dict[int, list[str]]:
    if not ids:
        return {}
    marks = ",".join("?" for _ in ids)
    result: dict[int, list[str]] = {}
    for row in connection.execute(
        f"SELECT entry_id, tag FROM tags WHERE entry_id IN ({marks}) ORDER BY tag", ids
    ):
        result.setdefault(int(row["entry_id"]), []).append(str(row["tag"]))
    return result


def _thumbs_for(connection: sqlite3.Connection, ids: list[int]) -> dict[int, list[LibraryThumb]]:
    if not ids:
        return {}
    marks = ",".join("?" for _ in ids)
    result: dict[int, list[LibraryThumb]] = {}
    for row in connection.execute(
        f"SELECT entry_id, position, role FROM thumbs WHERE entry_id IN ({marks}) "
        "ORDER BY entry_id, position",
        ids,
    ):
        entry_id = int(row["entry_id"])
        position = int(row["position"])
        result.setdefault(entry_id, []).append(
            LibraryThumb(
                position=position,
                role=str(row["role"]),
                url=f"/api/library/{entry_id}/thumb/{position}",
            )
        )
    return result


def _remove_files(names: list[str]) -> None:
    base = thumbs_dir()
    for name in names:
        # Der Name stammt aus der eigenen Datenbank, trotzdem nicht aus dem Ordner ausbrechen.
        candidate = (base / name).resolve()
        if candidate.parent != base.resolve():
            continue
        candidate.unlink(missing_ok=True)


def _to_item(
    row: sqlite3.Row, tags: list[str], thumbs: list[LibraryThumb]
) -> LibraryListItem:
    return LibraryListItem(
        id=int(row["id"]),
        created_at=str(row["created_at"]),
        title=str(row["title"]),
        mode=str(row["mode"]),
        video_source=str(row["video_source"]),
        profile_id=str(row["profile_id"]),
        profile_label=str(row["profile_label"]),
        language=str(row["language"]),
        density=str(row["density"]),
        favorite=bool(row["favorite"]),
        tags=tags,
        variant_count=int(row["variant_count"]),
        char_count=int(row["char_count"]),
        duration_ms=int(row["duration_ms"]),
        thumbs=thumbs,
    )


def _to_entry(row: sqlite3.Row, tags: list[str], thumbs: list[LibraryThumb]) -> LibraryEntry:
    payload = json.loads(str(row["payload"]))
    critique = payload.get("critique")
    scene = payload.get("scene")
    return LibraryEntry(
        **_to_item(row, tags, thumbs).model_dump(),
        intent=str(row["intent"]),
        aspect_ratio=str(row["aspect_ratio"]),
        clip_seconds=row["clip_seconds"],
        model=str(row["model"]),
        vision_model=row["vision_model"],
        input_prompt=str(row["input_prompt"]),
        briefing=str(row["briefing"]),
        shots=list(payload.get("shots") or []),
        critique=PromptCritique.model_validate(critique) if critique else None,
        scene=SceneSpec.model_validate(scene) if scene else None,
        bundles=[PromptBundle.model_validate(item) for item in payload.get("bundles") or []],
    )


_store = LibraryStore()


def get_library() -> LibraryStore:
    return _store
