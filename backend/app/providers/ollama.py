"""Ollama-Adapter.

Erbt den OpenAI-kompatiblen Pfad und nutzt zusaetzlich die nativen Endpunkte:
``/api/tags`` (verlaessliche Modellliste), ``/api/show`` (Fähigkeiten),
``/api/ps`` (was im VRAM liegt) und ``/api/chat`` (JSON-Schema, num_ctx, think).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from typing import Any

from app.core.errors import AppError
from app.models.provider import (
    ChatMessage,
    CompletionRequest,
    CompletionResult,
    ModelInfo,
    ProviderHealth,
    RunningModel,
)
from app.providers.base import guess_vision_support, split_data_uri
from app.providers.openai_compat import OpenAICompatProvider

log = logging.getLogger(__name__)

KEEP_ALIVE = "30m"

#: Wie viele Modelle hoechstens per ``/api/show`` nachgefragt werden.
SHOW_LIMIT = 60
#: Gleichzeitige ``/api/show``-Aufrufe. Lokal und billig, aber nicht unbegrenzt.
SHOW_CONCURRENCY = 6
#: Lesetimeout je ``/api/show``. Lokal antwortet das in Millisekunden.
SHOW_READ_TIMEOUT = 10.0
#: Gesamtbudget fuer alle Faehigkeitsabfragen zusammen. Danach gilt, was da ist.
SHOW_BUDGET_S = 20.0


class OllamaProvider(OpenAICompatProvider):
    kind = "ollama"

    async def health(self) -> ProviderHealth:
        started = time.perf_counter()
        try:
            response = await self._request("GET", f"{self.base_url}/api/version", read_timeout=10.0)
        except AppError as exc:
            return ProviderHealth(
                reachable=False,
                kind=self.kind,
                base_url=self.base_url,
                error_code=exc.code,
                error_message=exc.message,
            )
        version = None
        with contextlib.suppress(ValueError):
            version = response.json().get("version")
        return ProviderHealth(
            reachable=True,
            kind=self.kind,
            base_url=self.base_url,
            latency_ms=int((time.perf_counter() - started) * 1000),
            server_version=version,
        )

    async def list_models(self) -> list[ModelInfo]:
        response = await self._request("GET", f"{self.base_url}/api/tags", read_timeout=20.0)
        entries = response.json().get("models", [])
        models: list[ModelInfo] = []
        for entry in entries:
            name = entry.get("name") or entry.get("model")
            if not name:
                continue
            details = entry.get("details") or {}
            families = details.get("families") or (
                [details["family"]] if details.get("family") else []
            )
            models.append(
                ModelInfo(
                    name=name,
                    size_bytes=entry.get("size"),
                    parameter_size=details.get("parameter_size"),
                    quantization=details.get("quantization_level"),
                    families=list(families),
                    modified_at=entry.get("modified_at"),
                    supports_vision=guess_vision_support([], list(families), name),
                )
            )
        return sorted(models, key=lambda m: m.name)

    async def enrich_capabilities(self, models: list[ModelInfo], limit: int = SHOW_LIMIT) -> None:
        """Fähigkeiten ueber ``/api/show`` nachladen - je Modell ein Aufruf.

        Wichtig fuer die Modellauswahl: nur was hier belegt wird, ist eine Tatsache.
        Ohne Antwort bleibt ``supports_vision`` beim Namensraten oder bei ``None``.
        """
        targets = models[:limit]
        gate = asyncio.Semaphore(SHOW_CONCURRENCY)

        async def show_one(name: str) -> dict[str, Any]:
            async with gate:
                return await self.show(name)

        gathered = asyncio.gather(
            *(show_one(model.name) for model in targets), return_exceptions=True
        )
        try:
            results = await asyncio.wait_for(gathered, timeout=SHOW_BUDGET_S)
        except TimeoutError:
            # Lieber "unbekannt" als eine Oberflaeche, die minutenlang wartet.
            log.warning(
                "Fähigkeiten von %d Modellen nicht innerhalb von %.0f s ermittelt",
                len(targets),
                SHOW_BUDGET_S,
            )
            return
        for model, result in zip(targets, results, strict=True):
            if isinstance(result, BaseException):
                continue
            capabilities = [str(c) for c in (result.get("capabilities") or [])]
            if capabilities:
                model.capabilities = capabilities
                model.supports_vision = guess_vision_support(
                    capabilities, model.families, model.name
                )

    async def show(self, model: str) -> dict[str, Any]:
        response = await self._request(
            "POST",
            f"{self.base_url}/api/show",
            json={"model": model},
            read_timeout=SHOW_READ_TIMEOUT,
            model=model,
        )
        return response.json()

    async def running_models(self) -> list[RunningModel]:
        """Aktuell geladene Modelle inkl. VRAM-Belegung."""
        response = await self._request("GET", f"{self.base_url}/api/ps", read_timeout=10.0)
        running: list[RunningModel] = []
        for entry in response.json().get("models", []):
            name = entry.get("name") or entry.get("model")
            if not name:
                continue
            running.append(
                RunningModel(
                    name=name,
                    size_bytes=entry.get("size"),
                    size_vram_bytes=entry.get("size_vram"),
                    expires_at=entry.get("expires_at"),
                )
            )
        return running

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        options: dict[str, Any] = {
            "temperature": request.temperature,
            "num_predict": request.max_tokens,
        }
        if request.num_ctx:
            options["num_ctx"] = request.num_ctx

        body: dict[str, Any] = {
            "model": request.model,
            "messages": [self._render_native(m) for m in request.messages],
            "stream": False,
            "keep_alive": KEEP_ALIVE,
            "options": options,
        }
        if request.json_schema:
            body["format"] = request.json_schema
        if request.disable_thinking:
            body["think"] = False

        started = time.perf_counter()
        response = await self._request(
            "POST",
            f"{self.base_url}/api/chat",
            json=body,
            read_timeout=request.timeout_s,
            model=request.model,
        )
        payload = response.json()
        text = (payload.get("message") or {}).get("content") or ""
        if not text.strip():
            raise AppError(
                "invalid_model_output",
                "Das Modell lieferte eine leere Antwort. "
                "Ein anderes Modell oder ein kleinerer Kontext hilft meistens.",
            )
        return CompletionResult(
            text=text,
            model=payload.get("model", request.model),
            prompt_tokens=payload.get("prompt_eval_count"),
            completion_tokens=payload.get("eval_count"),
            duration_ms=int((time.perf_counter() - started) * 1000),
        )

    @staticmethod
    def _render_native(message: ChatMessage) -> dict[str, Any]:
        entry: dict[str, Any] = {"role": message.role, "content": message.content}
        if message.images:
            entry["images"] = [split_data_uri(uri)[1] for uri in message.images]
        return entry
