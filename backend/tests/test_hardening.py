"""Härtung: Statusabruf, Obergrenzen, blockierungsfreier Upload."""

from __future__ import annotations

import asyncio
import time

import httpx
import pytest
import respx

from app.core.logging import DropPolledAccess
from app.models.provider import ModelInfo
from app.models.settings import ProviderSettings
from app.providers.ollama import OllamaProvider

OLLAMA = "http://127.0.0.1:11434"

VERSION = {"version": "0.34.2"}
PS = {
    "models": [
        {
            "name": "orcarouter/Qwen3.8-27B-Uncensored:q4_K_M",
            "size": 17_456_766_646,
            "size_vram": 17_456_766_646,
            "expires_at": "2026-09-21T18:30:00Z",
        }
    ]
}


# --- Statusabruf -----------------------------------------------------------


@respx.mock
def test_status_reports_model_and_vram(client):
    respx.get(f"{OLLAMA}/api/version").mock(return_value=httpx.Response(200, json=VERSION))
    respx.get(f"{OLLAMA}/api/ps").mock(return_value=httpx.Response(200, json=PS))

    body = client.get("/api/provider/status").json()
    assert body["reachable"] is True
    assert body["server_version"] == "0.34.2"
    assert body["vram_bytes"] == 17_456_766_646
    assert body["text_model_loaded"] is True
    assert body["loaded"][0]["name"].startswith("orcarouter/")
    assert body["library_enabled"] is True


@respx.mock
def test_status_answers_even_when_the_server_is_down(client):
    """Die Statusleiste braucht immer eine Antwort - sonst zeigt sie nichts an."""
    respx.get(f"{OLLAMA}/api/version").mock(side_effect=httpx.ConnectError("refused"))

    response = client.get("/api/provider/status")
    assert response.status_code == 200
    body = response.json()
    assert body["reachable"] is False
    assert body["error_code"] == "provider_unreachable"
    assert "antwortet kein Modellserver" in body["error_message"]
    assert body["loaded"] == []
    assert body["text_model"]


@respx.mock
def test_status_survives_a_missing_vram_answer(client):
    """Der VRAM-Stand ist eine Zugabe und darf den Status nicht kippen."""
    respx.get(f"{OLLAMA}/api/version").mock(return_value=httpx.Response(200, json=VERSION))
    respx.get(f"{OLLAMA}/api/ps").mock(return_value=httpx.Response(500))

    body = client.get("/api/provider/status").json()
    assert body["reachable"] is True
    assert body["loaded"] == []
    assert body["vram_bytes"] is None


@respx.mock
def test_status_has_no_vram_for_other_servers(client):
    current = client.get("/api/settings").json()
    current["provider"]["kind"] = "openai_compat"
    current["provider"]["base_url"] = "http://127.0.0.1:1234"
    client.put("/api/settings", json=current)

    respx.get("http://127.0.0.1:1234/v1/models").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "irgendwas"}]})
    )
    body = client.get("/api/provider/status").json()
    assert body["reachable"] is True
    assert body["provider_kind"] == "openai_compat"
    assert body["loaded"] == []


def test_status_knows_a_switched_off_library(client):
    current = client.get("/api/settings").json()
    current["library"]["enabled"] = False
    client.put("/api/settings", json=current)
    assert client.get("/api/provider/status").json()["library_enabled"] is False


# --- Obergrenzen -----------------------------------------------------------


@respx.mock
async def test_capability_probing_gives_up_instead_of_hanging(monkeypatch):
    """Ein schweigender Server darf die Modellauswahl nicht minutenlang aufhalten."""
    monkeypatch.setattr("app.providers.ollama.SHOW_BUDGET_S", 0.3)

    async def never(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(5)
        return httpx.Response(200, json={"capabilities": ["vision"]})

    respx.post(f"{OLLAMA}/api/show").mock(side_effect=never)

    provider = OllamaProvider(ProviderSettings(base_url=OLLAMA))
    models = [ModelInfo(name=f"modell-{index}") for index in range(8)]

    started = time.perf_counter()
    await provider.enrich_capabilities(models)
    elapsed = time.perf_counter() - started

    assert elapsed < 3, "Die Abfrage hat das Budget nicht eingehalten"
    assert all(model.capabilities == [] for model in models)
    assert all(model.supports_vision is None for model in models)


# --- Upload blockiert den Event-Loop nicht ---------------------------------


async def test_upload_does_not_block_the_event_loop(client, monkeypatch, png_bytes):
    """Pillow muss in einem Thread laufen, nicht im Event-Loop.

    Gemessen wird über die Parallelität: vier Uploads, die je 0,4 s rechnen,
    brauchen zusammen gut 0,4 s, wenn sie ausgelagert sind - und 1,6 s, wenn sie
    nacheinander im Loop laufen. Von innen die Wartezeit zu stoppen ginge nicht:
    solange der Loop steht, kommt auch der Test nicht zum Messen.
    """
    from httpx import ASGITransport, AsyncClient

    from app.models.reference import StoredImage

    BLOCKS_FOR = 0.4
    PARALLEL = 4

    def slow_upload(raw, name, settings):
        time.sleep(BLOCKS_FOR)  # steht stellvertretend fuer Pillow
        return StoredImage(
            id="0" * 32, original_name=name, width=10, height=10, bytes=len(raw)
        ).with_urls()

    monkeypatch.setattr("app.services.images.store_upload", slow_upload)

    transport = ASGITransport(app=client.app)
    async with AsyncClient(transport=transport, base_url="http://pruefung", timeout=30) as http:
        started = time.perf_counter()
        responses = await asyncio.gather(
            *(
                http.post("/api/images", files={"file": ("gross.png", png_bytes, "image/png")})
                for _ in range(PARALLEL)
            )
        )
        elapsed = time.perf_counter() - started

    assert all(response.status_code == 200 for response in responses)
    assert elapsed < BLOCKS_FOR * PARALLEL / 2, (
        f"{PARALLEL} Uploads brauchten {elapsed:.2f}s - sie laufen nacheinander "
        "im Event-Loop statt in Threads"
    )


# --- Zugriffslog -----------------------------------------------------------


def test_polled_status_is_kept_out_of_the_access_log():
    import logging

    drop = DropPolledAccess()

    def line(message: str) -> logging.LogRecord:
        return logging.LogRecord("uvicorn.access", logging.INFO, "", 0, message, None, None)

    assert drop.filter(line('127.0.0.1 - "GET /api/provider/status HTTP/1.1" 200')) is False
    assert drop.filter(line('127.0.0.1 - "POST /api/compose/stream HTTP/1.1" 200')) is True


# --- Abbruch ---------------------------------------------------------------


def test_every_model_call_carries_a_timeout():
    """Kein Pfad zum Modellserver ohne Obergrenze - sonst haengt die UI."""
    from app.providers.openai_compat import OpenAICompatProvider

    provider = OpenAICompatProvider(
        ProviderSettings(base_url=OLLAMA, connect_timeout_s=3.0, request_timeout_s=90.0)
    )
    default = provider._timeout()
    assert default.connect == 3.0
    assert default.read == 90.0
    assert default.write is not None
    assert default.pool == 3.0

    explicit = provider._timeout(12.0)
    assert explicit.read == 12.0


@pytest.mark.parametrize("path", ["/api/provider/status", "/api/health", "/api/library/stats"])
def test_status_paths_answer_without_a_model_server(client, path):
    """Diese Wege muessen auch dann antworten, wenn Ollama aus ist."""
    with respx.mock:
        respx.route(host="127.0.0.1", port=11434).mock(side_effect=httpx.ConnectError("aus"))
        assert client.get(path).status_code == 200
