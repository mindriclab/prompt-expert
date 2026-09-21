"""Settings lesen, schreiben, zurücksetzen."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.errors import AppError
from app.core.settings_store import get_store
from app.models.settings import AppSettings
from app.services.profiles import get_registry

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=AppSettings)
async def read_settings() -> AppSettings:
    return get_store().load()


@router.put("", response_model=AppSettings)
async def write_settings(settings: AppSettings) -> AppSettings:
    if not get_registry().has(settings.defaults.profile_id):
        raise AppError(
            "profile_not_found",
            f"Standardprofil '{settings.defaults.profile_id}' gibt es nicht.",
        )
    return get_store().save(settings)


@router.post("/reset", response_model=AppSettings)
async def reset_settings() -> AppSettings:
    return get_store().reset()
