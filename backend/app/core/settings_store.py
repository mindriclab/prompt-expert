"""Laden und Speichern der Settings-Datei."""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
from pathlib import Path

from pydantic import ValidationError

from app.core.paths import settings_file
from app.models.settings import AppSettings

log = logging.getLogger(__name__)


class SettingsStore:
    """Haelt die Settings im Speicher und schreibt sie atomar auf Platte."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._cached: AppSettings | None = None

    @property
    def path(self) -> Path:
        return self._path or settings_file()

    def load(self) -> AppSettings:
        if self._cached is not None:
            return self._cached
        self._cached = self._read_from_disk()
        return self._cached

    def save(self, settings: AppSettings) -> AppSettings:
        path = self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = settings.model_dump_json(indent=2)
        fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
            os.replace(tmp_name, path)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise
        self._cached = settings
        return settings

    def reset(self) -> AppSettings:
        return self.save(AppSettings())

    def invalidate(self) -> None:
        self._cached = None

    def _read_from_disk(self) -> AppSettings:
        path = self.path
        if not path.exists():
            return AppSettings()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return AppSettings.model_validate(raw)
        except (json.JSONDecodeError, ValidationError, OSError) as exc:
            backup = path.with_suffix(".json.bak")
            log.warning(
                "settings.json ist unbrauchbar (%s). Sicherung nach %s, es gelten die Defaults.",
                type(exc).__name__,
                backup.name,
            )
            with contextlib.suppress(OSError):
                path.replace(backup)
            return AppSettings()


_store = SettingsStore()


def get_store() -> SettingsStore:
    return _store
