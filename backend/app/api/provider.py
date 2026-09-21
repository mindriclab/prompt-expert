"""Provider: Modelle auflisten, Verbindung testen, VRAM-Status."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.errors import AppError
from app.core.paths import APP_VERSION
from app.core.settings_store import get_store
from app.models.provider import (
    AppStatus,
    ModelInfo,
    ProviderHealth,
    ProviderTestResult,
    RunningModels,
)
from app.models.settings import ModelSettings, ProviderSettings
from app.providers.base import ModelProvider
from app.providers.factory import build_provider
from app.providers.ollama import OllamaProvider
from app.services.diagnostics import match_model, run_provider_test

log = logging.getLogger(__name__)

router = APIRouter(prefix="/provider", tags=["provider"])

NO_VRAM_NOTE = "Diesen Servertyp kann die App nicht nach belegtem VRAM fragen."

#: Obergrenze fuer den Statusabruf. Er wird gepollt und darf nie haengen bleiben.
STATUS_BUDGET_S = 8.0


class ProviderOverride(BaseModel):
    """Optionaler Override, damit die UI vor dem Speichern nachsehen kann."""

    provider: ProviderSettings | None = None


class ProviderTestRequest(ProviderOverride):
    models: ModelSettings | None = None
    probe: bool = Field(default=False, description="Zusätzlich eine echte Mini-Antwort erzeugen")


def _provider_for(body: ProviderOverride | None) -> ModelProvider:
    stored = get_store().load().provider
    return build_provider(body.provider if body and body.provider else stored)


async def _models(body: ProviderOverride | None) -> list[ModelInfo]:
    provider = _provider_for(body)
    models = await provider.list_models()
    if isinstance(provider, OllamaProvider):
        await provider.enrich_capabilities(models)
    return models


async def _running(body: ProviderOverride | None) -> RunningModels:
    provider = _provider_for(body)
    if not isinstance(provider, OllamaProvider):
        return RunningModels(supported=False, note=NO_VRAM_NOTE)
    return RunningModels(supported=True, models=await provider.running_models())


@router.get("/health", response_model=ProviderHealth)
async def provider_health() -> ProviderHealth:
    settings = get_store().load()
    return await build_provider(settings.provider).health()


@router.get("/models", response_model=list[ModelInfo])
async def provider_models() -> list[ModelInfo]:
    return await _models(None)


@router.post("/models", response_model=list[ModelInfo])
async def provider_models_for(body: ProviderOverride | None = None) -> list[ModelInfo]:
    """Wie oben, aber fuer eine Base URL, die noch nicht gespeichert ist."""
    return await _models(body)


@router.post("/test", response_model=ProviderTestResult)
async def provider_test(body: ProviderTestRequest | None = None) -> ProviderTestResult:
    settings = get_store().load()
    if body is not None and (body.provider or body.models):
        settings = settings.model_copy(
            update={
                "provider": body.provider or settings.provider,
                "models": body.models or settings.models,
            }
        )
    return await run_provider_test(settings, probe=bool(body and body.probe))


@router.get("/running", response_model=RunningModels)
async def provider_running() -> RunningModels:
    return await _running(None)


@router.post("/running", response_model=RunningModels)
async def provider_running_for(body: ProviderOverride | None = None) -> RunningModels:
    return await _running(body)


@router.get("/status", response_model=AppStatus)
async def provider_status() -> AppStatus:
    """Für die Statusleiste. Antwortet immer, auch wenn der Modellserver schweigt."""
    settings = get_store().load()
    provider = build_provider(settings.provider)
    status = AppStatus(
        version=APP_VERSION,
        provider_kind=provider.kind,
        base_url=settings.provider.base_url,
        reachable=False,
        text_model=settings.models.text_model,
        vision_model=settings.models.vision_model,
        library_enabled=settings.library.enabled,
    )

    try:
        health = await asyncio.wait_for(provider.health(), timeout=STATUS_BUDGET_S)
    except (TimeoutError, AppError) as exc:
        status.error_code = getattr(exc, "code", "provider_timeout")
        status.error_message = getattr(
            exc, "message", "Der Modellserver hat nicht rechtzeitig geantwortet."
        )
        return status

    status.reachable = health.reachable
    status.latency_ms = health.latency_ms
    status.server_version = health.server_version
    status.error_code = health.error_code
    status.error_message = health.error_message
    if not health.reachable or not isinstance(provider, OllamaProvider):
        return status

    try:
        loaded = await asyncio.wait_for(provider.running_models(), timeout=STATUS_BUDGET_S)
    except (TimeoutError, AppError):
        # Der VRAM-Stand ist eine Zugabe - er darf den Status nicht kippen.
        return status

    status.loaded = loaded
    status.vram_bytes = sum(entry.size_vram_bytes or 0 for entry in loaded) or None
    status.text_model_loaded = (
        match_model([entry.name for entry in loaded], settings.models.text_model) is not None
    )
    return status
