"""Verzeichnisse und Konstanten der Anwendung."""

from __future__ import annotations

import contextlib
import os
from functools import lru_cache
from pathlib import Path

APP_NAME = "PromptExpert"
#: Fruehere Bezeichnung - vorhandene Daten werden einmalig uebernommen.
LEGACY_APP_NAME = "LocalPromptStudio"
APP_VERSION = "0.1.0"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8756

#: Ueberschreibt das Datenverzeichnis (wird von den Tests genutzt).
DATA_DIR_ENV = "LPS_DATA_DIR"


def _default_data_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / APP_NAME
    return Path.home() / f".{APP_NAME.lower()}"


def _migrate_legacy(path: Path) -> None:
    """Daten aus der Zeit vor der Umbenennung uebernehmen, genau einmal."""
    if path.exists() or path.name != APP_NAME:
        return
    legacy = path.with_name(LEGACY_APP_NAME)
    if not legacy.is_dir():
        return
    # Scheitert das Umbenennen, werden einfach frische Defaults angelegt.
    with contextlib.suppress(OSError):
        legacy.rename(path)


@lru_cache(maxsize=1)
def data_dir() -> Path:
    override = os.environ.get(DATA_DIR_ENV)
    path = Path(override) if override else _default_data_dir()
    _migrate_legacy(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def legacy_data_dir() -> Path | None:
    """Der alte Ordner, falls er die Umbenennung überlebt hat - sonst None."""
    if os.environ.get(DATA_DIR_ENV):
        return None
    legacy = _default_data_dir().with_name(LEGACY_APP_NAME)
    return legacy if legacy.is_dir() else None


def settings_file() -> Path:
    return data_dir() / "settings.json"


def library_file() -> Path:
    return data_dir() / "library.db"


def thumbs_dir() -> Path:
    path = data_dir() / "thumbs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def profiles_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "profiles"


def project_root() -> Path:
    """Wurzel des Repos (enthaelt backend/, frontend/, docs/)."""
    return Path(__file__).resolve().parents[3]


def frontend_dist() -> Path:
    """Gebautes Frontend. Existiert erst ab Meilenstein 2."""
    return project_root() / "frontend" / "dist"


def reset_caches() -> None:
    """Nur fuer Tests: Verzeichnis-Cache leeren."""
    data_dir.cache_clear()
