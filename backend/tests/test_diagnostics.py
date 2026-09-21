from __future__ import annotations

import httpx
import respx

from app.models.settings import AppSettings, ModelSettings, ProviderSettings
from app.services.diagnostics import match_model, run_provider_test

OLLAMA_URL = "http://127.0.0.1:11434"
VISION_MODEL = "orcarouter/Qwen3.8-27B-Uncensored:q4_K_M"


def settings_for(text_model: str = VISION_MODEL, vision_model: str = VISION_MODEL) -> AppSettings:
    return AppSettings(
        provider=ProviderSettings(base_url=OLLAMA_URL, connect_timeout_s=1.0),
        models=ModelSettings(text_model=text_model, vision_model=vision_model),
    )


def tags(*names: str) -> dict:
    return {
        "models": [
            {"name": name, "size": 1, "details": {"families": ["qwen3"]}} for name in names
        ]
    }


def status_of(result, check_id: str) -> str:
    return next(check.status for check in result.checks if check.id == check_id)


def message_of(result, check_id: str) -> str:
    return next(check.message for check in result.checks if check.id == check_id)


def test_match_model_tolerates_latest_tag():
    assert match_model(["mistral:latest"], "mistral") == "mistral:latest"
    assert match_model(["Mistral:7b"], "mistral:7b") == "Mistral:7b"
    assert match_model(["mistral:7b"], "mistral:13b") is None


@respx.mock
async def test_everything_green():
    respx.get(f"{OLLAMA_URL}/api/version").mock(
        return_value=httpx.Response(200, json={"version": "0.12.3"})
    )
    respx.get(f"{OLLAMA_URL}/api/tags").mock(
        return_value=httpx.Response(200, json=tags(VISION_MODEL))
    )
    respx.post(f"{OLLAMA_URL}/api/show").mock(
        return_value=httpx.Response(200, json={"capabilities": ["completion", "vision"]})
    )

    result = await run_provider_test(settings_for())

    assert result.ok is True
    assert result.server_version == "0.12.3"
    assert [check.status for check in result.checks] == ["ok", "ok", "ok", "ok", "ok"]
    assert result.models[0].supports_vision is True


@respx.mock
async def test_dead_server_stops_after_first_check():
    respx.get(f"{OLLAMA_URL}/api/version").mock(side_effect=httpx.ConnectError("refused"))

    result = await run_provider_test(settings_for())

    assert result.ok is False
    assert len(result.checks) == 1
    assert status_of(result, "connection") == "fail"
    assert "Starte Ollama" in message_of(result, "connection")


@respx.mock
async def test_missing_model_names_the_pull_command():
    respx.get(f"{OLLAMA_URL}/api/version").mock(return_value=httpx.Response(200, json={}))
    respx.get(f"{OLLAMA_URL}/api/tags").mock(
        return_value=httpx.Response(200, json=tags("llama3.1:8b"))
    )
    respx.post(f"{OLLAMA_URL}/api/show").mock(
        return_value=httpx.Response(200, json={"capabilities": ["completion"]})
    )

    result = await run_provider_test(settings_for())

    assert result.ok is False
    assert status_of(result, "connection") == "ok"
    assert status_of(result, "models") == "ok"
    assert status_of(result, "text_model") == "fail"
    assert f"ollama pull {VISION_MODEL}" in message_of(result, "text_model")
    assert status_of(result, "vision_capability") == "skipped"


@respx.mock
async def test_text_model_ok_but_vision_model_cannot_see():
    respx.get(f"{OLLAMA_URL}/api/version").mock(return_value=httpx.Response(200, json={}))
    respx.get(f"{OLLAMA_URL}/api/tags").mock(
        return_value=httpx.Response(200, json=tags("textonly:24b"))
    )
    respx.post(f"{OLLAMA_URL}/api/show").mock(
        return_value=httpx.Response(200, json={"capabilities": ["completion", "tools"]})
    )

    result = await run_provider_test(settings_for("textonly:24b", "textonly:24b"))

    assert result.ok is False
    assert status_of(result, "text_model") == "ok"
    assert status_of(result, "vision_model") == "ok"
    assert status_of(result, "vision_capability") == "fail"
    assert "keine Bilder" in message_of(result, "vision_capability")


@respx.mock
async def test_unknown_capabilities_only_warn():
    respx.get(f"{OLLAMA_URL}/api/version").mock(return_value=httpx.Response(200, json={}))
    respx.get(f"{OLLAMA_URL}/api/tags").mock(
        return_value=httpx.Response(
            200,
            json={"models": [{"name": "mystery:7b", "size": 1, "details": {"families": ["x"]}}]},
        )
    )
    respx.post(f"{OLLAMA_URL}/api/show").mock(return_value=httpx.Response(500, json={}))

    result = await run_provider_test(settings_for("mystery:7b", "mystery:7b"))

    assert status_of(result, "vision_capability") == "warn"
    assert result.ok is True  # eine Warnung blockiert nicht


@respx.mock
async def test_empty_server_is_a_failure():
    respx.get(f"{OLLAMA_URL}/api/version").mock(return_value=httpx.Response(200, json={}))
    respx.get(f"{OLLAMA_URL}/api/tags").mock(return_value=httpx.Response(200, json={"models": []}))

    result = await run_provider_test(settings_for())

    assert result.ok is False
    assert status_of(result, "models") == "fail"


@respx.mock
async def test_probe_runs_a_real_completion():
    respx.get(f"{OLLAMA_URL}/api/version").mock(return_value=httpx.Response(200, json={}))
    respx.get(f"{OLLAMA_URL}/api/tags").mock(
        return_value=httpx.Response(200, json=tags(VISION_MODEL))
    )
    respx.post(f"{OLLAMA_URL}/api/show").mock(
        return_value=httpx.Response(200, json={"capabilities": ["completion", "vision"]})
    )
    chat = respx.post(f"{OLLAMA_URL}/api/chat").mock(
        return_value=httpx.Response(200, json={"message": {"content": "ready"}})
    )

    result = await run_provider_test(settings_for(), probe=True)

    assert chat.called
    assert result.ok is True
    assert status_of(result, "probe") == "ok"
    assert "ready" in message_of(result, "probe")


@respx.mock
async def test_probe_failure_is_reported_not_raised():
    respx.get(f"{OLLAMA_URL}/api/version").mock(return_value=httpx.Response(200, json={}))
    respx.get(f"{OLLAMA_URL}/api/tags").mock(
        return_value=httpx.Response(200, json=tags(VISION_MODEL))
    )
    respx.post(f"{OLLAMA_URL}/api/show").mock(
        return_value=httpx.Response(200, json={"capabilities": ["completion", "vision"]})
    )
    respx.post(f"{OLLAMA_URL}/api/chat").mock(side_effect=httpx.ReadTimeout("slow"))

    result = await run_provider_test(settings_for(), probe=True)

    assert result.ok is False
    assert status_of(result, "probe") == "fail"
