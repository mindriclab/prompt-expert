"""Strukturierte Modellantworten: Schema erzwingen, prüfen, einmal reparieren."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import BaseModel, ValidationError

from app.core.errors import AppError
from app.models.provider import ChatMessage, CompletionRequest
from app.providers.base import ModelProvider

log = logging.getLogger(__name__)

FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


def extract_json(text: str) -> str:
    """Holt das JSON-Objekt aus einer Antwort, auch wenn Zäune oder Text drumherum stehen."""
    cleaned = FENCE_RE.sub("", text.strip())
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise AppError(
            "invalid_model_output",
            "Die Antwort des Modells enthielt kein JSON-Objekt.",
        )
    return cleaned[start : end + 1]


def _short_validation_error(exc: ValidationError) -> str:
    parts = []
    for entry in exc.errors()[:4]:
        field = ".".join(str(p) for p in entry.get("loc", ())) or "root"
        parts.append(f"{field}: {entry.get('msg', '')}")
    return "; ".join(parts)


async def request_model_json[T: BaseModel](
    provider: ModelProvider,
    request: CompletionRequest,
    schema: dict[str, Any],
    model_cls: type[T],
) -> tuple[T, int]:
    """Fordert JSON nach Schema an und validiert es. Ein Reparaturversuch, dann Abbruch."""
    attempt_request = request.model_copy(update={"json_schema": schema})
    problem = ""
    raw = ""
    total_ms = 0

    for attempt in (1, 2):
        completion = await provider.complete(attempt_request)
        total_ms += completion.duration_ms or 0
        raw = completion.text
        try:
            payload = json.loads(extract_json(raw))
            return model_cls.model_validate(payload), total_ms
        except AppError as exc:
            problem = exc.message
        except json.JSONDecodeError as exc:
            problem = f"Ungültiges JSON an Position {exc.pos}: {exc.msg}"
        except ValidationError as exc:
            problem = _short_validation_error(exc)

        if attempt == 1:
            log.info("Modellantwort unbrauchbar (%s) - ein Reparaturversuch", problem)
            attempt_request = attempt_request.model_copy(
                update={
                    "messages": [
                        *attempt_request.messages,
                        ChatMessage(role="assistant", content=raw[:2000]),
                        ChatMessage(
                            role="user",
                            content=(
                                "That was not valid against the schema. "
                                f"Problem: {problem}. "
                                "Return the corrected JSON object only, nothing else."
                            ),
                        ),
                    ],
                    "temperature": 0.0,
                }
            )

    raise AppError(
        "invalid_model_output",
        "Das Modell lieferte auch nach einem Korrekturversuch kein gültiges Ergebnis. "
        "Ein anderes Modell oder ein kürzerer Eingabeprompt hilft meistens.",
        detail=problem,
    )
