"""Auswahl des passenden Adapters anhand der Settings."""

from __future__ import annotations

from app.models.settings import ProviderSettings
from app.providers.base import ModelProvider
from app.providers.ollama import OllamaProvider
from app.providers.openai_compat import OpenAICompatProvider

_PROVIDERS = {
    "ollama": OllamaProvider,
    "openai_compat": OpenAICompatProvider,
}


def build_provider(settings: ProviderSettings) -> ModelProvider:
    provider_cls = _PROVIDERS.get(settings.kind, OpenAICompatProvider)
    return provider_cls(settings)
