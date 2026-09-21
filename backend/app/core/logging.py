"""Logging-Setup. Keine Bilddaten, keine vollstaendigen Nutzerprompts auf INFO."""

from __future__ import annotations

import contextlib
import logging
import os
import sys

#: Wird alle paar Sekunden von der Statusleiste abgefragt.
POLLED_PATHS = ("/api/provider/status",)


class DropPolledAccess(logging.Filter):
    """Haelt das Zugriffslog lesbar: der Statusabruf steht sonst im Sekundentakt darin."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        return not any(path in message for path in POLLED_PATHS)


def configure_logging() -> None:
    level_name = os.environ.get("LPS_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    # Die Meldungen sind deutsch. Ohne das schreibt die Windows-Konsole
    # "Eintr?ge" statt "Einträge", weil sie auf cp1252 steht.
    stream = sys.stderr
    if hasattr(stream, "reconfigure"):
        with contextlib.suppress(OSError, ValueError):
            stream.reconfigure(encoding="utf-8", errors="replace")

    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=stream,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    access = logging.getLogger("uvicorn.access")
    if not any(isinstance(entry, DropPolledAccess) for entry in access.filters):
        access.addFilter(DropPolledAccess())
