from __future__ import annotations

import asyncio
import json

import pytest

from app.api.compose import compose_stream
from app.core.errors import AppError
from app.models.compose import (
    ComposeRequest,
    ComposeResponse,
    PromptBundle,
    PromptCritique,
)

PAYLOAD = {
    "mode": "improve",
    "profile_id": "flux_image",
    "density": "balanced",
    "language": "en",
    "input_prompt": "girl in alley, neon",
}


def fake_response() -> ComposeResponse:
    return ComposeResponse(
        mode="improve",
        intent="reproduce",
        profile_id="flux_image",
        profile_label="FLUX / Krea — Bild",
        language="en",
        density="balanced",
        model="testmodell",
        critique=PromptCritique(summary="Zu vage."),
        bundles=[
            PromptBundle(
                variant="precise", profile_id="flux_image", main_prompt="eine praezise Fassung"
            ).fill_meta("Präzise")
        ],
        duration_ms=1234,
    )


def parse_sse(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip().split("\n\n"):
        if not block.strip():
            continue
        name = ""
        payload = "{}"
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line[7:]
            elif line.startswith("data: "):
                payload = line[6:]
        events.append((name, json.loads(payload)))
    return events


# --- JSON-Route ------------------------------------------------------------


def test_compose_returns_bundles(client, monkeypatch):
    async def fake_compose(request, settings, profile, provider, emit=None):
        assert request.profile_id == "flux_image"
        assert profile.id == "flux_image"
        return fake_response()

    monkeypatch.setattr("app.api.compose.compose", fake_compose)
    body = client.post("/api/compose", json=PAYLOAD).json()
    assert body["bundles"][0]["main_prompt"] == "eine praezise Fassung"
    assert body["bundles"][0]["variant_label"] == "Präzise"
    assert body["critique"]["summary"] == "Zu vage."


def test_unknown_profile_is_rejected(client):
    response = client.post("/api/compose", json={**PAYLOAD, "profile_id": "gibtsnicht"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "profile_not_found"


def test_empty_prompt_is_rejected(client):
    response = client.post("/api/compose", json={**PAYLOAD, "input_prompt": "   "})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_unknown_field_is_rejected(client):
    assert client.post("/api/compose", json={**PAYLOAD, "seed": 42}).status_code == 422


def test_provider_error_uses_error_envelope(client, monkeypatch):
    async def failing(*args, **kwargs):
        raise AppError("provider_unreachable")

    monkeypatch.setattr("app.api.compose.compose", failing)
    response = client.post("/api/compose", json=PAYLOAD)
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "provider_unreachable"


# --- Ereignisstrom ---------------------------------------------------------


def test_stream_emits_stages_then_result(client, monkeypatch):
    async def fake_compose(request, settings, profile, provider, emit=None):
        await emit("stage", {"stage": "critique", "message": "Prompt wird analysiert"})
        await emit("critique", {"summary": "Zu vage."})
        await emit("stage", {"stage": "compose", "index": 1, "total": 1, "variant": "precise"})
        await emit("bundle", {"variant": "precise", "main_prompt": "x"})
        return fake_response()

    monkeypatch.setattr("app.api.compose.compose", fake_compose)
    response = client.post("/api/compose/stream", json=PAYLOAD)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    events = parse_sse(response.text)
    assert [name for name, _ in events] == ["stage", "critique", "stage", "bundle", "result"]
    assert events[-1][1]["profile_label"] == "FLUX / Krea — Bild"
    assert events[1][1]["summary"] == "Zu vage."


def test_stream_reports_errors_as_events_not_http_status(client, monkeypatch):
    async def failing(request, settings, profile, provider, emit=None):
        await emit("stage", {"stage": "critique", "message": "los"})
        raise AppError("provider_timeout")

    monkeypatch.setattr("app.api.compose.compose", failing)
    response = client.post("/api/compose/stream", json=PAYLOAD)
    assert response.status_code == 200  # Der Strom lief bereits
    events = parse_sse(response.text)
    assert events[-1][0] == "error"
    assert events[-1][1]["code"] == "provider_timeout"


def test_stream_validates_before_streaming(client):
    response = client.post("/api/compose/stream", json={**PAYLOAD, "profile_id": "gibtsnicht"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "profile_not_found"


async def test_disconnect_cancels_the_running_model_call(monkeypatch):
    """TestClient puffert den Strom, deshalb wird der Generator direkt getrieben."""
    cancelled = asyncio.Event()

    async def slow_compose(request, settings, profile, provider, emit=None):
        await emit("stage", {"stage": "critique", "message": "Prompt wird analysiert"})
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return fake_response()

    monkeypatch.setattr("app.api.compose.compose", slow_compose)

    response = await compose_stream(ComposeRequest(**PAYLOAD))
    iterator = response.body_iterator
    first = await anext(iterator)
    assert first.startswith("event: stage")

    await iterator.aclose()  # der Client legt mitten im Lauf auf

    assert cancelled.is_set(), "Der laufende Modellaufruf wurde nicht abgebrochen"


@pytest.mark.parametrize("density", ["sparse", "balanced", "detailed"])
def test_all_densities_are_accepted(client, monkeypatch, density):
    async def fake_compose(request, settings, profile, provider, emit=None):
        assert request.density == density
        return fake_response()

    monkeypatch.setattr("app.api.compose.compose", fake_compose)
    assert client.post("/api/compose", json={**PAYLOAD, "density": density}).status_code == 200
