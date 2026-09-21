from __future__ import annotations

from app.core.paths import APP_VERSION


def test_health_reports_state(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == APP_VERSION
    assert body["profiles"] == 8
    assert body["profiles_invalid"] == 0
    assert body["provider_kind"] == "ollama"
    assert body["provider_is_local"] is True
    assert body["data_dir"].endswith("data")


def test_unknown_route_uses_error_envelope(client):
    response = client.get("/api/gibtsnicht")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
