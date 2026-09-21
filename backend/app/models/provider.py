"""Datentypen der Provider-Schicht."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Role = Literal["system", "user", "assistant"]
CheckStatus = Literal["ok", "warn", "fail", "skipped"]


class ModelInfo(BaseModel):
    name: str
    size_bytes: int | None = None
    parameter_size: str | None = None
    quantization: str | None = None
    families: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    supports_vision: bool | None = None
    modified_at: str | None = None


class ProviderHealth(BaseModel):
    reachable: bool
    kind: str
    base_url: str
    latency_ms: int | None = None
    server_version: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class ChatMessage(BaseModel):
    role: Role
    content: str
    #: Data-URIs (``data:image/jpeg;base64,...``)
    images: list[str] = Field(default_factory=list)


class CompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    temperature: float = 0.8
    max_tokens: int = 2048
    num_ctx: int | None = None
    json_schema: dict[str, Any] | None = None
    disable_thinking: bool = True
    timeout_s: float | None = None

    @property
    def has_images(self) -> bool:
        return any(message.images for message in self.messages)


class CompletionResult(BaseModel):
    text: str
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    duration_ms: int | None = None


class RunningModel(BaseModel):
    """Ein Modell, das der Server gerade geladen hat."""

    name: str
    size_bytes: int | None = None
    size_vram_bytes: int | None = None
    expires_at: str | None = None


class RunningModels(BaseModel):
    """Antwort von ``/provider/running``.

    ``supported=False`` ist kein Fehler, sondern heisst: dieser Servertyp sagt es nicht.
    """

    supported: bool
    models: list[RunningModel] = Field(default_factory=list)
    note: str | None = None


class AppStatus(BaseModel):
    """Kompakter Zustand für die Statusleiste.

    Bewusst billig: eine Anfrage an den Modellserver für die Erreichbarkeit, eine
    für den VRAM. Keine Modellliste, keine Fähigkeitsabfrage - das wird gepollt.
    """

    version: str
    provider_kind: str
    base_url: str
    reachable: bool
    latency_ms: int | None = None
    server_version: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    text_model: str
    vision_model: str
    #: Nur bei Ollama gefüllt. Leer heisst: nichts geladen oder nicht abfragbar.
    loaded: list[RunningModel] = Field(default_factory=list)
    vram_bytes: int | None = None
    #: Liegt das konfigurierte Textmodell gerade im VRAM?
    text_model_loaded: bool = False
    library_enabled: bool = True


class ProviderCheck(BaseModel):
    id: str
    label: str
    status: CheckStatus
    message: str


class ProviderTestResult(BaseModel):
    ok: bool
    kind: str
    base_url: str
    latency_ms: int | None = None
    server_version: str | None = None
    text_model: str
    vision_model: str
    models: list[ModelInfo] = Field(default_factory=list)
    checks: list[ProviderCheck] = Field(default_factory=list)
