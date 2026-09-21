"""Zielprofile."""

from __future__ import annotations

from fastapi import APIRouter

from app.models.profile import Profile, ProfileList
from app.services.profiles import get_registry

router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.get("", response_model=ProfileList)
async def list_profiles() -> ProfileList:
    registry = get_registry()
    return ProfileList(profiles=registry.all(), invalid=registry.invalid())


@router.post("/reload", response_model=ProfileList)
async def reload_profiles() -> ProfileList:
    registry = get_registry()
    registry.load(force=True)
    return ProfileList(profiles=registry.all(), invalid=registry.invalid())


@router.get("/{profile_id}", response_model=Profile)
async def read_profile(profile_id: str) -> Profile:
    return get_registry().get(profile_id)
