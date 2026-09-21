from __future__ import annotations

import base64

import httpx
import pytest
import respx

from app.core.errors import AppError
from app.models.provider import ChatMessage, CompletionRequest
from app.models.settings import ProviderSettings
from app.providers.base import guess_vision_support, split_data_uri
from app.providers.factory import build_provider
from app.providers.ollama import OllamaProvider
from app.providers.openai_compat import OpenAICompatProvider

OLLAMA_URL = "http://127.0.0.1:11434"
PIXEL = base64.b64encode(b"not-a-real-image").decode()
DATA_URI = f"data:image/jpeg;base64,{PIXEL}"

TAGS_PAYLOAD = {
    "models": [
        {
            "name": "orcarouter/Qwen3.8-27B-Uncensored:q4_K_M",
            "size": 18_000_000_000,
            "modified_at": "2026-09-01T10:00:00Z",
            "details": {
                "families": ["qwen3", "clip"],
                "parameter_size": "27B",
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


def ollama_provider() -> OllamaProvider:
    return OllamaProvider(ProviderSettings(base_url=OLLAMA_URL, connect_timeout_s=1.0))


def body_of(request: httpx.Request) -> dict:
    return httpx.Response(200, content=request.content).json()


def test_factory_picks_adapter():
    assert isinstance(build_provider(ProviderSettings(kind="ollama")), OllamaProvider)
    other = build_provider(ProviderSettings(kind="openai_compat", base_url="http://127.0.0.1:1234"))
    assert isinstance(other, OpenAICompatProvider)
    assert not isinstance(other, OllamaProvider)


def test_openai_base_is_derived_once():
    one = OpenAICompatProvider(ProviderSettings(base_url="http://h:1/"))
    two = OpenAICompatProvider(ProviderSettings(base_url="http://h:1/v1"))
    assert one.openai_base == "http://h:1/v1"
    assert two.openai_base == "http://h:1/v1"


def test_split_data_uri_roundtrip():
    assert split_data_uri(DATA_URI) == ("jpeg", PIXEL)
    with pytest.raises(AppError, match="Data-URI"):
        split_data_uri("nope")
    with pytest.raises(AppError, match="Base64"):
        split_data_uri("data:image/png;base64,!!!!")


def test_vision_guess():
    assert guess_vision_support(["completion", "vision"], [], "x") is True
    # gemeldete Fähigkeiten schlagen die Heuristik
    assert guess_vision_support(["completion"], ["clip"], "x") is False
    assert guess_vision_support([], ["clip"], "x") is True
    assert guess_vision_support([], ["llama"], "qwen2.5-vl:7b") is True
    assert guess_vision_support([], ["llama"], "llama3.1:8b") is None


@respx.mock
async def test_list_models_reads_tags():
    respx.get(f"{OLLAMA_URL}/api/tags").mock(return_value=httpx.Response(200, json=TAGS_PAYLOAD))
    models = await ollama_provider().list_models()
    assert [m.name for m in models] == [
        "llama3.1:8b",
        "orcarouter/Qwen3.8-27B-Uncensored:q4_K_M",
    ]
    qwen = models[1]
    assert qwen.parameter_size == "27B"
    assert qwen.quantization == "Q4_K_M"
    assert qwen.supports_vision is True
    assert models[0].supports_vision is None


@respx.mock
async def test_capabilities_are_enriched():
    respx.get(f"{OLLAMA_URL}/api/tags").mock(return_value=httpx.Response(200, json=TAGS_PAYLOAD))
    respx.post(f"{OLLAMA_URL}/api/show").mock(
        return_value=httpx.Response(200, json={"capabilities": ["completion", "tools"]})
    )
    provider = ollama_provider()
    models = await provider.list_models()
    await provider.enrich_capabilities(models)
    assert all(model.supports_vision is False for model in models)


@respx.mock
async def test_health_reports_version():
    respx.get(f"{OLLAMA_URL}/api/version").mock(
        return_value=httpx.Response(200, json={"version": "0.12.3"})
    )
    health = await ollama_provider().health()
    assert health.reachable is True
    assert health.server_version == "0.12.3"
    assert health.latency_ms is not None


@respx.mock
async def test_health_survives_dead_server():
    respx.get(f"{OLLAMA_URL}/api/version").mock(side_effect=httpx.ConnectError("refused"))
    health = await ollama_provider().health()
    assert health.reachable is False
    assert health.error_code == "provider_unreachable"
    assert "Base URL" in health.error_message


@respx.mock
async def test_native_chat_sends_schema_and_disables_thinking():
    route = respx.post(f"{OLLAMA_URL}/api/chat").mock(
        return_value=httpx.Response(
            200,
            json={
                "model": "m",
                "message": {"content": '{"ok": true}'},
                "prompt_eval_count": 12,
                "eval_count": 5,
            },
        )
    )
    request = CompletionRequest(
        model="m",
        messages=[ChatMessage(role="user", content="hi", images=[DATA_URI])],
        json_schema={"type": "object"},
        num_ctx=16384,
    )
    result = await ollama_provider().complete(request)

    body = body_of(route.calls.last.request)
    assert body["format"] == {"type": "object"}
    assert body["think"] is False
    assert body["options"]["num_ctx"] == 16384
    # rohes Base64, kein Data-URI
    assert body["messages"][0]["images"] == [PIXEL]
    assert result.text == '{"ok": true}'
    assert result.prompt_tokens == 12


@respx.mock
async def test_empty_answer_is_an_error():
    respx.post(f"{OLLAMA_URL}/api/chat").mock(
        return_value=httpx.Response(200, json={"message": {"content": "   "}})
    )
    with pytest.raises(AppError) as excinfo:
        await ollama_provider().complete(
            CompletionRequest(model="m", messages=[ChatMessage(role="user", content="hi")])
        )
    assert excinfo.value.code == "invalid_model_output"


@respx.mock
async def test_missing_model_is_named():
    respx.post(f"{OLLAMA_URL}/api/chat").mock(
        return_value=httpx.Response(404, json={"error": "model not found"})
    )
    with pytest.raises(AppError) as excinfo:
        await ollama_provider().complete(
            CompletionRequest(model="fehlt:q4", messages=[ChatMessage(role="user", content="hi")])
        )
    assert excinfo.value.code == "model_not_found"
    assert "ollama pull fehlt:q4" in excinfo.value.message


@respx.mock
async def test_timeout_is_distinguished_from_unreachable():
    respx.post(f"{OLLAMA_URL}/api/chat").mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(AppError) as excinfo:
        await ollama_provider().complete(
            CompletionRequest(model="m", messages=[ChatMessage(role="user", content="hi")])
        )
    assert excinfo.value.code == "provider_timeout"
    assert "VRAM" in excinfo.value.message


@respx.mock
async def test_openai_adapter_builds_vision_message():
    route = respx.post("http://127.0.0.1:1234/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "model": "local",
                "choices": [{"message": {"content": "hallo"}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2},
            },
        )
    )
    provider = OpenAICompatProvider(
        ProviderSettings(kind="openai_compat", base_url="http://127.0.0.1:1234", api_key="key")
    )
    result = await provider.complete(
        CompletionRequest(
            model="local",
            messages=[ChatMessage(role="user", content="was ist das", images=[DATA_URI])],
            json_schema={"type": "object"},
        )
    )
    sent = route.calls.last.request
    body = body_of(sent)
    assert sent.headers["authorization"] == "Bearer key"
    assert body["response_format"]["type"] == "json_schema"
    parts = body["messages"][0]["content"]
    assert parts[0]["type"] == "text"
    assert parts[1]["image_url"]["url"] == DATA_URI
    assert result.text == "hallo"


@respx.mock
async def test_openai_models_endpoint():
    respx.get("http://127.0.0.1:1234/v1/models").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "qwen2.5-vl"}, {"id": "mistral"}]})
    )
    provider = OpenAICompatProvider(
        ProviderSettings(kind="openai_compat", base_url="http://127.0.0.1:1234")
    )
    models = await provider.list_models()
    assert [m.name for m in models] == ["mistral", "qwen2.5-vl"]
    assert models[1].supports_vision is True
