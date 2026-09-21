"""Laedt die Zielprofile aus dem Profilverzeichnis."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import ValidationError

from app.core.errors import AppError
from app.core.paths import profiles_dir
from app.models.profile import InvalidProfile, Profile

log = logging.getLogger(__name__)


class ProfileRegistry:
    def __init__(self, directory: Path | None = None) -> None:
        self._directory = directory
        self._profiles: dict[str, Profile] = {}
        self._invalid: list[InvalidProfile] = []
        self._loaded = False

    @property
    def directory(self) -> Path:
        return self._directory or profiles_dir()

    def load(self, *, force: bool = False) -> None:
        if self._loaded and not force:
            return
        profiles: dict[str, Profile] = {}
        invalid: list[InvalidProfile] = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                profile = Profile.model_validate(raw)
            except (json.JSONDecodeError, ValidationError, OSError) as exc:
                invalid.append(InvalidProfile(file=path.name, error=_short_error(exc)))
                log.warning("Profil %s ist ungültig: %s", path.name, _short_error(exc))
                continue
            if profile.id != path.stem:
                invalid.append(
                    InvalidProfile(
                        file=path.name,
                        error=f"id '{profile.id}' passt nicht zum Dateinamen '{path.stem}'",
                    )
                )
                continue
            profiles[profile.id] = profile
        self._profiles = profiles
        self._invalid = invalid
        self._loaded = True

    def all(self) -> list[Profile]:
        self.load()
        return sorted(self._profiles.values(), key=lambda p: (p.kind, p.label))

    def invalid(self) -> list[InvalidProfile]:
        self.load()
        return list(self._invalid)

    def get(self, profile_id: str) -> Profile:
        self.load()
        profile = self._profiles.get(profile_id)
        if profile is None:
            known = ", ".join(sorted(self._profiles)) or "keine"
            raise AppError(
                "profile_not_found",
                f"Zielprofil '{profile_id}' gibt es nicht. Verfügbar: {known}.",
            )
        return profile

    def has(self, profile_id: str) -> bool:
        self.load()
        return profile_id in self._profiles


def _short_error(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        first = exc.errors()[0]
        field = ".".join(str(p) for p in first.get("loc", ()))
        return f"{field or 'profil'}: {first.get('msg', '')}"
    return f"{type(exc).__name__}: {exc}"


_registry = ProfileRegistry()


def get_registry() -> ProfileRegistry:
    return _registry
