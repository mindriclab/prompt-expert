"""Prompt Expert - Backend.

Start: python -m uvicorn app.main:app --host 127.0.0.1 --port 8756
"""

from __future__ import annotations

import logging
import os
import threading
import webbrowser
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import compose, health, images, library, profiles, provider, settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.paths import (
    APP_VERSION,
    DEFAULT_HOST,
    DEFAULT_PORT,
    data_dir,
    frontend_dist,
    legacy_data_dir,
)
from app.core.settings_store import get_store
from app.services.images import cleanup_old
from app.services.library import get_library
from app.services.profiles import get_registry
from app.web import mount_web

log = logging.getLogger(__name__)

#: Vite-Dev-Server im Entwicklungsmodus.
DEV_ORIGINS = ["http://127.0.0.1:5173", "http://localhost:5173"]

#: start.bat setzt das. Tests und der Dev-Server tun es bewusst nicht.
OPEN_BROWSER_ENV = "PE_OPEN_BROWSER"


def _open_browser_when_ready(url: str) -> None:
    """Erst oeffnen, wenn der Server wirklich antwortet - sonst sieht der Nutzer einen Fehler."""
    if os.environ.get(OPEN_BROWSER_ENV) != "1":
        return
    # Nur einmal, auch wenn Uvicorn den Prozess neu laedt.
    os.environ[OPEN_BROWSER_ENV] = "0"
    threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    log.info("Browser wird geoeffnet: %s", url)


@asynccontextmanager
async def lifespan(app_ref: FastAPI):
    configure_logging()
    registry = get_registry()
    registry.load(force=True)
    current = get_store().load()
    log.info("Datenverzeichnis: %s", data_dir())
    leftover = legacy_data_dir()
    if leftover is not None:
        log.warning(
            "Aus der Zeit vor der Umbenennung liegt noch %s herum. "
            "Der Ordner wird nicht mehr benutzt und kann gelöscht werden.",
            leftover,
        )
    log.info("Profile geladen: %d (%d ungültig)", len(registry.all()), len(registry.invalid()))
    for broken in registry.invalid():
        log.warning("Profil %s übersprungen: %s", broken.file, broken.error)
    log.info(
        "Provider: %s @ %s | Text: %s | Vision: %s",
        current.provider.kind,
        current.provider.base_url,
        current.models.text_model,
        current.models.vision_model,
    )
    if not current.provider.is_local:
        log.warning("Base URL ist nicht lokal: %s", current.provider.base_url)
    removed = cleanup_old()
    if removed:
        log.info("%d alte Referenzbilder aufgeräumt", removed)
    if current.library.enabled:
        try:
            get_library().ensure_schema()
            stats = get_library().stats()
            log.info(
                "Bibliothek: %d Einträge (%d Favoriten), %d kB",
                stats.count,
                stats.favorites,
                stats.bytes_on_disk // 1024,
            )
        except Exception:  # noqa: BLE001 - die App laeuft auch ohne Bibliothek
            log.exception("Bibliothek nicht verfügbar - die Läufe werden nicht gespeichert")
    else:
        log.info("Bibliothek ist abgeschaltet - Läufe werden nicht gespeichert")
    if getattr(app_ref.state, "frontend_mounted", False):
        log.info("Frontend wird aus %s ausgeliefert", frontend_dist())
    else:
        log.info("Kein gebautes Frontend gefunden - unter / steht die Statusseite")
    _open_browser_when_ready(f"http://{DEFAULT_HOST}:{DEFAULT_PORT}")
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Prompt Expert",
        version=APP_VERSION,
        summary="Lokale Prompt-Werkstatt fuer Bild- und Video-Generatoren. (c) by mindric lab",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=DEV_ORIGINS,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)

    api = APIRouter(prefix="/api")
    api.include_router(health.router)
    api.include_router(settings.router)
    api.include_router(profiles.router)
    api.include_router(provider.router)
    api.include_router(compose.router)
    api.include_router(images.router)
    api.include_router(library.router)
    app.include_router(api)

    # Muss nach den API-Routen kommen: der Frontend-Mount auf "/" faengt sonst alles ab.
    app.state.frontend_mounted = mount_web(app)
    return app


app = create_app()


def main() -> None:
    import uvicorn

    configure_logging()
    uvicorn.run("app.main:app", host=DEFAULT_HOST, port=DEFAULT_PORT, reload=False)


if __name__ == "__main__":
    main()
