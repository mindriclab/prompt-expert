"""Komposition: einmalig als JSON oder als Ereignisstrom mit Statusstufen."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import sqlite3
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.core.errors import AppError
from app.core.settings_store import get_store
from app.models.compose import ComposeRequest, ComposeResponse
from app.models.settings import AppSettings
from app.providers.factory import build_provider
from app.services.composer import compose
from app.services.library import get_library
from app.services.profiles import get_registry

log = logging.getLogger(__name__)

router = APIRouter(prefix="/compose", tags=["compose"])

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _prepare(body: ComposeRequest):
    settings = get_store().load()
    profile = get_registry().get(body.profile_id)
    if body.mode == "improve" and not body.input_prompt:
        raise AppError("validation_error", "Es fehlt der Prompt, der verbessert werden soll.")
    return settings, profile, build_provider(settings.provider)


async def _remember(
    body: ComposeRequest, result: ComposeResponse, settings: AppSettings
) -> ComposeResponse:
    """Den fertigen Lauf in die Bibliothek legen.

    Ein Fehler hier darf ein Ergebnis nicht wegwerfen, für das der Nutzer gerade
    eine Minute gewartet hat - er wird am Ergebnis vermerkt, nicht geworfen.
    """
    if not settings.library.enabled:
        return result
    try:
        result.library_id = await asyncio.to_thread(
            get_library().remember,
            body,
            result,
            store_thumbnails=settings.library.store_thumbnails,
            max_entries=settings.library.max_entries,
        )
    except (OSError, sqlite3.Error) as exc:
        log.warning("Bibliothek: Lauf nicht gespeichert (%s)", type(exc).__name__)
        result.library_error = (
            "Der Lauf konnte nicht in der Bibliothek abgelegt werden. "
            "Das Ergebnis steht trotzdem hier."
        )
    return result


@router.post("", response_model=ComposeResponse)
async def compose_once(body: ComposeRequest) -> ComposeResponse:
    """Blockierende Variante - für Skripte und Tests."""
    settings, profile, provider = _prepare(body)
    result = await compose(body, settings, profile, provider)
    return await _remember(body, result, settings)


@router.post("/stream")
async def compose_stream(body: ComposeRequest) -> StreamingResponse:
    """Server-Sent Events: ``stage``, ``critique``, ``bundle``, ``result``, ``error``.

    Bricht der Client die Verbindung ab, wird der laufende Modellaufruf abgebrochen.
    """
    settings, profile, provider = _prepare(body)

    async def event_stream() -> AsyncIterator[str]:
        queue: asyncio.Queue[tuple[str, dict[str, Any]] | None] = asyncio.Queue()

        async def emit(event: str, data: dict[str, Any]) -> None:
            await queue.put((event, data))

        async def runner() -> None:
            try:
                result = await compose(body, settings, profile, provider, emit)
                await _remember(body, result, settings)
                await queue.put(("result", result.model_dump()))
            except AppError as exc:
                await queue.put(("error", exc.to_payload()["error"]))
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - darf den Strom nicht sprengen
                log.exception("Komposition fehlgeschlagen")
                failure = AppError("internal_error", detail=type(exc).__name__)
                await queue.put(("error", failure.to_payload()["error"]))
            finally:
                await queue.put(None)

        task = asyncio.create_task(runner())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                event, data = item
                yield _sse(event, data)
        finally:
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
                log.info("Komposition vom Client abgebrochen")

    return StreamingResponse(
        event_stream(), media_type="text/event-stream", headers=SSE_HEADERS
    )
