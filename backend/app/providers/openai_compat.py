"""Adapter fuer jeden OpenAI-kompatiblen lokalen Server.

Deckt LM Studio, llama.cpp-server, KoboldCpp, vLLM und (ueber ``/v1``) auch Ollama ab.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.core.errors import AppError
from app.models.provider import (
    ChatMessage,
    CompletionRequest,
    CompletionResult,
    ModelInfo,
    ProviderHealth,
)
from app.models.settings import ProviderSettings
from app.providers.base import guess_vision_support, map_status_error, map_transport_error


class OpenAICompatProvider:
    kind = "openai_compat"

    def __init__(self, settings: ProviderSettings) -> None:
        self.settings = settings
        self.base_url = settings.base_url

    # -- HTTP ---------------------------------------------------------------

    @property
    def openai_base(self) -> str:
        base = self.base_url.rstrip("/")
        return base if base.endswith("/v1") else f"{base}/v1"

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.settings.api_key:
            headers["Authorization"] = f"Bearer {self.settings.api_key}"
        return headers

    def _timeout(self, read_timeout: float | None = None) -> httpx.Timeout:
        return httpx.Timeout(
            connect=self.settings.connect_timeout_s,
            read=read_timeout or self.settings.request_timeout_s,
            write=30.0,
            pool=self.settings.connect_timeout_s,
        )

    async def _request(
        self,
        method: str,
        url: str,
        *,
        json: dict[str, Any] | None = None,
        read_timeout: float | None = None,
        model: str | None = None,
    ) -> httpx.Response:
        try:
            async with httpx.AsyncClient(timeout=self._timeout(read_timeout)) as client:
                response = await client.request(method, url, json=json, headers=self._headers())
        except Exception as exc:  # noqa: BLE001 - wird auf AppError abgebildet
            raise map_transport_error(exc, self.base_url) from exc
        if response.status_code >= 400:
            raise map_status_error(response, model, self.kind)
        return response

    # -- Protokoll ----------------------------------------------------------

    async def health(self) -> ProviderHealth:
        started = time.perf_counter()
        try:
            await self._request("GET", f"{self.openai_base}/models", read_timeout=10.0)
        except AppError as exc:
            return ProviderHealth(
                reachable=False,
                kind=self.kind,
                base_url=self.base_url,
                error_code=exc.code,
                error_message=exc.message,
            )
        return ProviderHealth(
            reachable=True,
            kind=self.kind,
            base_url=self.base_url,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    async def list_models(self) -> list[ModelInfo]:
        response = await self._request("GET", f"{self.openai_base}/models", read_timeout=15.0)
        payload = response.json()
        models: list[ModelInfo] = []
        for entry in payload.get("data", []):
            name = entry.get("id")
            if not name:
                continue
            models.append(
                ModelInfo(
                    name=name,
                    supports_vision=guess_vision_support([], [], name),
                )
            )
        return sorted(models, key=lambda m: m.name)

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        body: dict[str, Any] = {
            "model": request.model,
            "messages": [self._render_message(m) for m in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": False,
        }
        if request.json_schema:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "structured_result",
                    "strict": True,
                    "schema": request.json_schema,
                },
            }
        started = time.perf_counter()
        response = await self._request(
            "POST",
            f"{self.openai_base}/chat/completions",
            json=body,
            read_timeout=request.timeout_s,
            model=request.model,
        )
        payload = response.json()
        choices = payload.get("choices") or []
        if not choices:
            raise AppError(
                "invalid_model_output", "Der Modellserver lieferte keine Antwort zurück."
            )
        text = (choices[0].get("message") or {}).get("content") or ""
        usage = payload.get("usage") or {}
        return CompletionResult(
            text=text,
            model=payload.get("model", request.model),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            duration_ms=int((time.perf_counter() - started) * 1000),
        )

    # -- Hilfen -------------------------------------------------------------

    @staticmethod
    def _render_message(message: ChatMessage) -> dict[str, Any]:
        if not message.images:
            return {"role": message.role, "content": message.content}
        parts: list[dict[str, Any]] = [{"type": "text", "text": message.content}]
        parts.extend(
            {"type": "image_url", "image_url": {"url": uri}} for uri in message.images
        )
        return {"role": message.role, "content": parts}
