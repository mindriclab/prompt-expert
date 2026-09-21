"""Settings-Schema. Wird als JSON im Datenverzeichnis abgelegt."""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

DEFAULT_MODEL = "orcarouter/Qwen3.8-27B-Uncensored:q4_K_M"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"

ProviderKind = Literal["ollama", "openai_compat"]
Language = Literal["de", "en"]
Density = Literal["sparse", "balanced", "detailed"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProviderSettings(StrictModel):
    kind: ProviderKind = "ollama"
    base_url: str = DEFAULT_OLLAMA_URL
    api_key: str | None = None
    connect_timeout_s: float = Field(default=5.0, ge=1.0, le=60.0)
    request_timeout_s: float = Field(default=180.0, ge=10.0, le=1800.0)

    @field_validator("base_url")
    @classmethod
    def _check_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Base URL muss mit http:// oder https:// beginnen")
        return value

    @field_validator("api_key")
    @classmethod
    def _blank_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @property
    def is_local(self) -> bool:
        host = (urlparse(self.base_url).hostname or "").lower()
        return host in {"127.0.0.1", "localhost", "::1", "0.0.0.0"}


class ModelSettings(StrictModel):
    text_model: str = DEFAULT_MODEL
    vision_model: str = DEFAULT_MODEL
    temperature: float = Field(default=0.8, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2048, ge=256, le=32768)
    num_ctx: int = Field(default=16384, ge=2048, le=262144)
    disable_thinking: bool = True

    @field_validator("text_model", "vision_model")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Modellname darf nicht leer sein")
        return value


class ImageSettings(StrictModel):
    max_edge: int = Field(default=1280, ge=384, le=2048)
    jpeg_quality: int = Field(default=85, ge=50, le=100)
    max_images: int = Field(default=6, ge=1, le=6)
    max_upload_mb: int = Field(default=25, ge=1, le=100)


class DefaultsSettings(StrictModel):
    profile_id: str = "flux_image"
    language: Language = "en"
    density: Density = "balanced"


class LibrarySettings(StrictModel):
    enabled: bool = True
    store_thumbnails: bool = True
    max_entries: int = Field(default=5000, ge=100, le=100000)


class AppSettings(StrictModel):
    schema_version: int = 1
    provider: ProviderSettings = Field(default_factory=ProviderSettings)
    models: ModelSettings = Field(default_factory=ModelSettings)
    images: ImageSettings = Field(default_factory=ImageSettings)
    defaults: DefaultsSettings = Field(default_factory=DefaultsSettings)
    library: LibrarySettings = Field(default_factory=LibrarySettings)

    def redacted(self) -> dict:
        """Fuer Logs: ohne API-Key."""
        data = self.model_dump()
        if data["provider"].get("api_key"):
            data["provider"]["api_key"] = "***"
        return data
