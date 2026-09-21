"""Provider-Protokoll und gemeinsame HTTP-Fehlerbehandlung."""

from __future__ import annotations

import base64
import binascii
import re
from typing import Protocol, runtime_checkable

import httpx

from app.core.errors import AppError
from app.models.provider import (
    CompletionRequest,
    CompletionResult,
    ModelInfo,
    ProviderHealth,
)

DATA_URI_RE = re.compile(r"^data:image/(?P<fmt>jpeg|jpg|png|webp);base64,(?P<payload>.+)$", re.I)

VISION_FAMILY_HINTS = {
    "clip",
    "gemma3",
    "gemma4",
    "llava",
    "mllama",
    "mistral3",
    "qwen2vl",
    "qwen25vl",
    "qwen3vl",
    "siglip",
    "vision",
}


@runtime_checkable
class ModelProvider(Protocol):
    kind: str
    base_url: str

    async def health(self) -> ProviderHealth: ...

    async def list_models(self) -> list[ModelInfo]: ...

    async def complete(self, request: CompletionRequest) -> CompletionResult: ...


def split_data_uri(value: str) -> tuple[str, str]:
    """``data:image/png;base64,AAA`` -> ``("png", "AAA")``."""
    match = DATA_URI_RE.match(value.strip())
    if not match:
        raise AppError("image_rejected", "Bild wurde nicht als Data-URI übergeben.")
    payload = match.group("payload")
    try:
        base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise AppError("image_rejected", "Bilddaten sind kein gültiges Base64.") from exc
    return match.group("fmt").lower(), payload


def guess_vision_support(capabilities: list[str], families: list[str], name: str) -> bool | None:
    """True/False wenn belegbar, sonst None (unbekannt)."""
    if capabilities:
        return "vision" in {c.lower() for c in capabilities}
    lowered = {f.lower().replace("-", "").replace("_", "").replace(".", "") for f in families}
    if lowered & VISION_FAMILY_HINTS:
        return True
    flat = name.lower().replace("-", "").replace("_", "").replace(".", "")
    if any(hint in flat for hint in ("vl", "vision", "llava", "joycaption")):
        return True
    return None


def map_transport_error(exc: Exception, base_url: str) -> AppError:
    if isinstance(exc, httpx.ConnectTimeout | httpx.ConnectError):
        return AppError(
            "provider_unreachable",
            f"Unter {base_url} antwortet kein Modellserver. "
            "Starte Ollama oder prüfe die Base URL in den Einstellungen.",
        )
    if isinstance(exc, httpx.TimeoutException):
        return AppError(
            "provider_timeout",
            "Der Modellserver hat nicht rechtzeitig geantwortet. "
            "Modell zu groß fuer den freien VRAM oder Kontext zu lang.",
        )
    if isinstance(exc, httpx.HTTPError):
        return AppError(
            "provider_error", f"Verbindungsfehler zum Modellserver: {type(exc).__name__}"
        )
    return AppError("internal_error", detail=type(exc).__name__)


def missing_model_hint(model: str, kind: str) -> str:
    """Nur bei Ollama ist ``ollama pull`` der richtige Rat."""
    if kind == "ollama":
        return (
            f"Das Modell '{model}' ist auf dem Server nicht installiert. "
            f"Hol es mit: ollama pull {model}"
        )
    return (
        f"Der Modellserver kennt '{model}' nicht. Prüfe den Namen in den Einstellungen "
        "oder lade das Modell im Server selbst."
    )


def map_status_error(
    response: httpx.Response, model: str | None = None, kind: str = "ollama"
) -> AppError:
    body = response.text[:400]
    if response.status_code == 404 and model:
        return AppError("model_not_found", missing_model_hint(model, kind))
    if response.status_code in (401, 403):
        return AppError(
            "provider_error",
            "Der Modellserver hat die Anfrage abgelehnt (Authentifizierung).",
            detail=body,
        )
    return AppError(
        "provider_error",
        f"Der Modellserver antwortete mit HTTP {response.status_code}.",
        detail=body,
    )
