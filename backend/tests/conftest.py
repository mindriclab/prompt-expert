from __future__ import annotations

import io
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.core import paths
from app.core.settings_store import get_store
from app.main import create_app
from app.services.library import get_library


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch) -> Iterator[None]:
    """Jeder Test bekommt ein eigenes Datenverzeichnis."""
    monkeypatch.setenv(paths.DATA_DIR_ENV, str(tmp_path / "data"))
    paths.reset_caches()
    get_store().invalidate()
    get_library().invalidate()
    yield
    paths.reset_caches()
    get_store().invalidate()
    get_library().invalidate()


@pytest.fixture(autouse=True)
def no_built_frontend(tmp_path, monkeypatch) -> None:
    """Tests duerfen nicht davon abhaengen, ob jemand das Frontend gebaut hat."""
    monkeypatch.setattr("app.web.frontend_dist", lambda: tmp_path / "kein-frontend")


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture
def png_bytes() -> bytes:
    """Ein kleines, gueltiges PNG fuer Upload-Tests."""
    buffer = io.BytesIO()
    Image.new("RGB", (640, 480), (120, 40, 80)).save(buffer, format="PNG")
    return buffer.getvalue()
