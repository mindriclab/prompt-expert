"""Der OpenAI-kompatible Adapter gegen einen echten HTTP-Server.

Alle anderen Providertests hängen sich mit ``respx`` in den Transport. Das prüft
die Logik, aber nicht, ob über eine echte Verbindung das Richtige auf der Leitung
steht. Hier läuft ein kleiner Server, der sich wie LM Studio oder llama.cpp verhält:
gleiche Pfade, gleiche Antwortform, gleiche Fehlerfälle.
"""

from __future__ import annotations

import socket
import threading
import time
from typing import Any

import pytest
import uvicorn
from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse

from app.models.provider import ChatMessage, CompletionRequest
from app.models.settings import AppSettings, ModelSettings, ProviderSettings
from app.providers.openai_compat import OpenAICompatProvider
from app.services.diagnostics import run_provider_test

PIXEL = "data:image/jpeg;base64,aGFsbG8="
STUB_MODEL = "stub-7b-instruct"

#: Was der Stub zuletzt bekommen hat - so laesst sich die Leitung pruefen.
seen: dict[str, Any] = {}


def build_stub() -> FastAPI:
    app = FastAPI()

    @app.get("/v1/models")
    async def models(authorization: str | None = Header(default=None)) -> dict:
        seen["authorization"] = authorization
        return {
            "object": "list",
            "data": [{"id": STUB_MODEL, "object": "model"}, {"id": "stub-vl", "object": "model"}],
        }

    @app.post("/v1/chat/completions")
    async def completions(request: Request) -> JSONResponse:
        body = await request.json()
        seen["body"] = body
        if body.get("model") == "gibtsnicht":
            return JSONResponse({"error": {"message": "model not found"}}, status_code=404)
        content = '{"ok": true}' if body.get("response_format") else "ready"
        return JSONResponse(
            {
                "id": "chatcmpl-1",
                "model": body.get("model"),
                "choices": [
                    {"index": 0, "message": {"role": "assistant", "content": content}}
                ],
                "usage": {"prompt_tokens": 11, "completion_tokens": 3},
            }
        )

    return app


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.fixture(scope="module")
def stub_url() -> str:
    port = _free_port()
    config = uvicorn.Config(build_stub(), host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    if not server.started:
        pytest.skip("Der Stub-Server ist nicht gestartet")

    yield f"http://127.0.0.1:{port}"

    server.should_exit = True
    thread.join(timeout=5)


def provider_for(url: str, api_key: str | None = None) -> OpenAICompatProvider:
    return OpenAICompatProvider(
        ProviderSettings(
            kind="openai_compat", base_url=url, api_key=api_key, connect_timeout_s=2.0
        )
    )


# --- Grundlagen ------------------------------------------------------------


async def test_health_and_models_over_real_http(stub_url):
    provider = provider_for(stub_url)
    health = await provider.health()
    assert health.reachable is True
    assert health.latency_ms is not None

    models = await provider.list_models()
    assert [model.name for model in models] == ["stub-7b-instruct", "stub-vl"]
    # Ein OpenAI-kompatibler Server meldet keine Faehigkeiten - Namensraten bleibt Raten.
    assert {model.name: model.supports_vision for model in models} == {
        "stub-7b-instruct": None,
        "stub-vl": True,
    }


async def test_api_key_reaches_the_server(stub_url):
    await provider_for(stub_url, api_key="geheim").list_models()
    assert seen["authorization"] == "Bearer geheim"


async def test_base_url_with_v1_is_not_doubled(stub_url):
    provider = provider_for(f"{stub_url}/v1")
    assert provider.openai_base == f"{stub_url}/v1"
    assert (await provider.health()).reachable is True


async def test_unreachable_port_is_reported_in_german():
    from app.core.errors import AppError

    provider = provider_for(f"http://127.0.0.1:{_free_port()}")
    health = await provider.health()
    assert health.reachable is False
    assert health.error_code == "provider_unreachable"
    assert "antwortet kein Modellserver" in (health.error_message or "")

    with pytest.raises(AppError) as failure:
        await provider.list_models()
    assert failure.value.code == "provider_unreachable"


# --- Was tatsaechlich auf der Leitung steht --------------------------------


async def test_completion_body_matches_the_openai_shape(stub_url):
    result = await provider_for(stub_url).complete(
        CompletionRequest(
            model=STUB_MODEL,
            messages=[
                ChatMessage(role="system", content="sei knapp"),
                ChatMessage(role="user", content="sag ready"),
            ],
            temperature=0.3,
            max_tokens=32,
        )
    )
    assert result.text == "ready"
    assert result.prompt_tokens == 11
    assert result.duration_ms is not None

    body = seen["body"]
    assert body["model"] == STUB_MODEL
    assert body["stream"] is False
    assert body["temperature"] == 0.3
    assert body["max_tokens"] == 32
    assert body["messages"] == [
        {"role": "system", "content": "sei knapp"},
        {"role": "user", "content": "sag ready"},
    ]


async def test_images_travel_as_image_url_parts(stub_url):
    await provider_for(stub_url).complete(
        CompletionRequest(
            model="stub-vl",
            messages=[ChatMessage(role="user", content="was ist das", images=[PIXEL])],
        )
    )
    content = seen["body"]["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "was ist das"}
    assert content[1] == {"type": "image_url", "image_url": {"url": PIXEL}}


async def test_json_schema_is_requested_in_strict_form(stub_url):
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}}
    result = await provider_for(stub_url).complete(
        CompletionRequest(
            model=STUB_MODEL,
            messages=[ChatMessage(role="user", content="x")],
            json_schema=schema,
        )
    )
    assert result.text == '{"ok": true}'
    response_format = seen["body"]["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    assert response_format["json_schema"]["schema"] == schema


async def test_missing_model_becomes_a_pull_hint(stub_url):
    from app.core.errors import AppError

    with pytest.raises(AppError) as failure:
        await provider_for(stub_url).complete(
            CompletionRequest(model="gibtsnicht", messages=[ChatMessage(role="user", content="x")])
        )
    assert failure.value.code == "model_not_found"
    assert "gibtsnicht" in failure.value.message
    assert "ollama pull" not in failure.value.message


# --- Der Verbindungstest der Settings-Ansicht ------------------------------


async def test_provider_test_against_a_non_ollama_server(stub_url):
    settings = AppSettings(
        provider=ProviderSettings(kind="openai_compat", base_url=stub_url, connect_timeout_s=2.0),
        models=ModelSettings(text_model=STUB_MODEL, vision_model="stub-vl"),
    )
    result = await run_provider_test(settings, probe=True)
    checks = {check.id: check for check in result.checks}

    assert result.ok is True
    assert checks["connection"].status == "ok"
    assert checks["models"].status == "ok"
    assert checks["text_model"].status == "ok"
    assert checks["vision_model"].status == "ok"
    assert checks["vision_capability"].status == "ok"
    assert checks["probe"].status == "ok"
    assert "ready" in checks["probe"].message


async def test_provider_test_names_the_missing_model(stub_url):
    settings = AppSettings(
        provider=ProviderSettings(kind="openai_compat", base_url=stub_url, connect_timeout_s=2.0),
        models=ModelSettings(text_model="fehlt-hier", vision_model=STUB_MODEL),
    )
    result = await run_provider_test(settings)
    checks = {check.id: check for check in result.checks}

    assert result.ok is False
    assert checks["text_model"].status == "fail"
    # Bei einem Nicht-Ollama-Server waere "ollama pull" ein falscher Rat.
    assert "ollama pull" not in checks["text_model"].message
    assert "kennt 'fehlt-hier' nicht" in checks["text_model"].message
    # Ohne gemeldete Faehigkeiten wird nichts behauptet.
    assert checks["vision_capability"].status == "warn"
