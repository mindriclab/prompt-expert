"""Routen fuer die Modellauswahl: Liste, Override, VRAM-Status."""

from __future__ import annotations

import httpx
import respx

from app.models.provider import ModelInfo
from app.models.settings import ProviderSettings
from app.providers.ollama import OllamaProvider

STORED = "http://127.0.0.1:11434"
OTHER = "http://127.0.0.1:19999"

TAGS = {
    "models": [
        {
            "name": "qwen3-vl:32b",
            "size": 20_000_000_000,
            "details": {
                "families": ["qwen3vl", "clip"],
                "parameter_size": "32B",
                "quantization_level": "Q4_K_M",
            },
        },
        {
            "name": "llama3.1:8b",
            "size": 4_700_000_000,
            "details": {"families": ["llama"], "parameter_size": "8B"},
        },
    ]
}

PS = {
    "models": [
        {
            "name": "qwen3-vl:32b",
            "model": "qwen3-vl:32b",
            "size": 20_000_000_000,
            "size_vram": 19_800_000_000,
            "expires_at": "2026-09-20T18:30:00Z",
        }
    ]
}


def mock_tags(base: str, payload: dict | None = None) -> None:
    respx.get(f"{base}/api/tags").mock(return_value=httpx.Response(200, json=payload or TAGS))


def mock_show(base: str) -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        name = httpx.Response(200, content=request.content).json()["model"]
        caps = ["completion", "vision"] if "vl" in name else ["completion"]
        return httpx.Response(200, json={"capabilities": caps})

    respx.post(f"{base}/api/show").mock(side_effect=answer)


@respx.mock
def test_models_use_stored_base_url(client):
    mock_tags(STORED)
    mock_show(STORED)
    body = client.get("/api/provider/models").json()
    assert [entry["name"] for entry in body] == ["llama3.1:8b", "qwen3-vl:32b"]
    by_name = {entry["name"]: entry for entry in body}
    assert by_name["qwen3-vl:32b"]["supports_vision"] is True
    assert by_name["llama3.1:8b"]["supports_vision"] is False
    assert by_name["qwen3-vl:32b"]["quantization"] == "Q4_K_M"


@respx.mock
def test_models_accept_an_unsaved_base_url(client):
    """Die Settings-Ansicht muss nachsehen koennen, bevor gespeichert wird."""
    mock_tags(OTHER, {"models": [{"name": "nur-hier:latest", "details": {}}]})
    mock_show(OTHER)
    body = client.post(
        "/api/provider/models",
        json={"provider": {"kind": "ollama", "base_url": OTHER}},
    ).json()
    assert [entry["name"] for entry in body] == ["nur-hier:latest"]


@respx.mock
def test_running_reports_vram(client):
    respx.get(f"{STORED}/api/ps").mock(return_value=httpx.Response(200, json=PS))
    body = client.get("/api/provider/running").json()
    assert body["supported"] is True
    assert body["models"][0]["size_vram_bytes"] == 19_800_000_000
    assert body["models"][0]["expires_at"].startswith("2026-09-20")


def test_running_is_not_an_error_without_ollama(client):
    """Fehlender VRAM-Status ist Abwesenheit, kein Fehler - sonst zeigt die UI rot."""
    current = client.get("/api/settings").json()
    current["provider"]["kind"] = "openai_compat"
    current["provider"]["base_url"] = "http://127.0.0.1:1234/v1"
    assert client.put("/api/settings", json=current).status_code == 200

    response = client.get("/api/provider/running")
    assert response.status_code == 200
    body = response.json()
    assert body["supported"] is False
    assert body["models"] == []
    assert body["note"]


@respx.mock
async def test_capabilities_beyond_the_limit_stay_unproven():
    """Was ``/api/show`` nicht bestaetigt hat, darf die UI nicht als Tatsache zeigen."""
    mock_show(STORED)
    provider = OllamaProvider(ProviderSettings(base_url=STORED))
    models = [
        ModelInfo(name="qwen3-vl:32b", supports_vision=True),
        ModelInfo(name="mystery-model:7b"),
    ]
    await provider.enrich_capabilities(models, limit=1)
    assert models[0].capabilities == ["completion", "vision"]
    assert models[1].capabilities == []
    assert models[1].supports_vision is None


@respx.mock
async def test_show_failure_leaves_the_guess_alone():
    respx.post(f"{STORED}/api/show").mock(return_value=httpx.Response(500))
    provider = OllamaProvider(ProviderSettings(base_url=STORED))
    models = [ModelInfo(name="llama3.1:8b", supports_vision=None)]
    await provider.enrich_capabilities(models)
    assert models[0].supports_vision is None
