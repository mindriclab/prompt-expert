from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def test_root_serves_status_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Prompt Expert" in response.text
    assert "/api/health" in response.text
    assert "mindric lab" in response.text


def test_favicon_does_not_404(client):
    assert client.get("/favicon.ico").status_code == 204


def test_api_routes_still_win_over_root(client):
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/docs").status_code == 200


def test_built_frontend_takes_over_when_present(tmp_path, monkeypatch):
    dist = tmp_path / "frontend" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("<html><body>echtes frontend</body></html>", encoding="utf-8")
    monkeypatch.setattr("app.web.frontend_dist", lambda: dist)

    with TestClient(create_app()) as frontend_client:
        root = frontend_client.get("/")
        assert root.status_code == 200
        assert "echtes frontend" in root.text
        # API bleibt erreichbar, obwohl "/" gemountet ist
        assert frontend_client.get("/api/health").json()["status"] == "ok"


# --- Automatischer Browserstart ----------------------------------------------


def test_browser_opens_only_when_start_bat_asks_for_it(monkeypatch):
    from app import main

    opened: list[str] = []
    monkeypatch.setattr(main.webbrowser, "open", opened.append)
    monkeypatch.setattr(main.threading, "Timer", lambda _delay, fn: _Immediate(fn))

    monkeypatch.delenv(main.OPEN_BROWSER_ENV, raising=False)
    main._open_browser_when_ready("http://127.0.0.1:8756")
    assert opened == []

    monkeypatch.setenv(main.OPEN_BROWSER_ENV, "1")
    main._open_browser_when_ready("http://127.0.0.1:8756")
    assert opened == ["http://127.0.0.1:8756"]

    # Ein Neustart des Servers im selben Prozess darf kein zweites Fenster oeffnen.
    main._open_browser_when_ready("http://127.0.0.1:8756")
    assert opened == ["http://127.0.0.1:8756"]


class _Immediate:
    """Ersetzt threading.Timer im Test: fuehrt sofort aus statt verzoegert."""

    def __init__(self, fn):
        self._fn = fn

    def start(self) -> None:
        self._fn()
