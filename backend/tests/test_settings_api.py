from __future__ import annotations

import json

from app.core.settings_store import get_store
from app.models.settings import DEFAULT_MODEL


def test_defaults_are_served(client):
    body = client.get("/api/settings").json()
    assert body["provider"]["base_url"] == "http://127.0.0.1:11434"
    assert body["models"]["text_model"] == DEFAULT_MODEL
    assert body["library"]["enabled"] is True


def test_roundtrip_persists_to_disk(client):
    current = client.get("/api/settings").json()
    current["provider"]["base_url"] = "http://127.0.0.1:1234/v1"
    current["provider"]["kind"] = "openai_compat"
    current["models"]["text_model"] = "some-local-model"
    current["images"]["max_edge"] = 1024

    saved = client.put("/api/settings", json=current)
    assert saved.status_code == 200
    assert saved.json()["images"]["max_edge"] == 1024

    on_disk = json.loads(get_store().path.read_text(encoding="utf-8"))
    assert on_disk["models"]["text_model"] == "some-local-model"
    assert client.get("/api/settings").json()["provider"]["kind"] == "openai_compat"


def test_trailing_slash_is_normalised(client):
    current = client.get("/api/settings").json()
    current["provider"]["base_url"] = "http://127.0.0.1:11434/"
    assert client.put("/api/settings", json=current).json()["provider"]["base_url"] == (
        "http://127.0.0.1:11434"
    )


def test_invalid_values_are_rejected(client):
    current = client.get("/api/settings").json()
    current["provider"]["base_url"] = "ftp://nope"
    response = client.put("/api/settings", json=current)
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["detail"][0]["field"] == "provider.base_url"


def test_unknown_field_is_rejected(client):
    current = client.get("/api/settings").json()
    current["provider"]["secret_upload_url"] = "http://example.com"
    assert client.put("/api/settings", json=current).status_code == 422


def test_unknown_default_profile_is_rejected(client):
    current = client.get("/api/settings").json()
    current["defaults"]["profile_id"] = "gibtsnicht"
    response = client.put("/api/settings", json=current)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "profile_not_found"


def test_validation_reasons_are_german(client):
    """Die Settings-Ansicht zeigt diese Texte direkt am Feld - englisch geht nicht."""
    current = client.get("/api/settings").json()
    current["images"]["max_edge"] = 100
    current["models"]["max_tokens"] = 99999
    detail = client.put("/api/settings", json=current).json()["error"]["detail"]
    reasons = {entry["field"]: entry["reason"] for entry in detail}
    assert reasons["images.max_edge"] == "Mindestens 384."
    assert reasons["models.max_tokens"] == "Höchstens 32768."


def test_own_validator_text_is_kept_without_prefix(client):
    current = client.get("/api/settings").json()
    current["provider"]["base_url"] = "ftp://nope"
    detail = client.put("/api/settings", json=current).json()["error"]["detail"]
    assert detail[0]["reason"] == "Base URL muss mit http:// oder https:// beginnen"


def test_reset_restores_defaults(client):
    current = client.get("/api/settings").json()
    current["images"]["jpeg_quality"] = 60
    client.put("/api/settings", json=current)
    assert client.post("/api/settings/reset").json()["images"]["jpeg_quality"] == 85


def test_corrupt_file_falls_back_to_defaults(client):
    store = get_store()
    store.path.write_text("{kaputt", encoding="utf-8")
    store.invalidate()
    assert client.get("/api/settings").json()["images"]["jpeg_quality"] == 85
    assert store.path.with_suffix(".json.bak").exists()


def test_api_key_is_redacted_in_log_dump():
    from app.models.settings import AppSettings, ProviderSettings

    settings = AppSettings(provider=ProviderSettings(api_key="geheim"))
    assert settings.redacted()["provider"]["api_key"] == "***"
