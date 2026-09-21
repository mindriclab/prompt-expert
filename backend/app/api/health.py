"""Healthcheck."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.paths import APP_VERSION, data_dir
from app.core.settings_store import get_store
from app.services.profiles import get_registry

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    status: str
    version: str
    data_dir: str
    settings_file: str
    profiles: int
    profiles_invalid: int
    provider_kind: str
    provider_base_url: str
    provider_is_local: bool
    text_model: str
    vision_model: str


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = get_store().load()
    registry = get_registry()
    return HealthResponse(
        status="ok",
        version=APP_VERSION,
        data_dir=str(data_dir()),
        settings_file=str(get_store().path),
        profiles=len(registry.all()),
        profiles_invalid=len(registry.invalid()),
        provider_kind=settings.provider.kind,
        provider_base_url=settings.provider.base_url,
        provider_is_local=settings.provider.is_local,
        text_model=settings.models.text_model,
        vision_model=settings.models.vision_model,
    )
