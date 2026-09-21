"""Einheitliches Fehlerformat fuer alle Routen."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

#: code -> (HTTP-Status, Standardtext)
ERROR_CODES: dict[str, tuple[int, str]] = {
    "provider_unreachable": (502, "Unter dieser Adresse antwortet kein Modellserver."),
    "provider_timeout": (504, "Der Modellserver hat nicht rechtzeitig geantwortet."),
    "provider_error": (502, "Der Modellserver hat mit einem Fehler geantwortet."),
    "model_not_found": (404, "Das gewählte Modell ist nicht installiert."),
    "model_no_vision": (422, "Das gewählte Modell kann keine Bilder verarbeiten."),
    "invalid_model_output": (422, "Das Modell lieferte keine gültige Antwort."),
    "validation_error": (422, "Die Eingabe ist nicht gültig."),
    "age_gate": (422, "Diese Referenz wirkt nicht eindeutig erwachsen."),
    "profile_not_found": (404, "Dieses Zielprofil gibt es nicht."),
    "image_rejected": (400, "Diese Bilddatei wird nicht akzeptiert."),
    "not_found": (404, "Nicht gefunden."),
    "internal_error": (500, "Unerwarteter Fehler im Backend."),
}


class AppError(Exception):
    """Fehler, der als Fehlerobjekt an das Frontend geht."""

    def __init__(
        self,
        code: str,
        message: str | None = None,
        *,
        detail: Any = None,
        status_code: int | None = None,
    ) -> None:
        default_status, default_message = ERROR_CODES.get(code, (500, "Unerwarteter Fehler."))
        self.code = code
        self.message = message or default_message
        self.detail = detail
        self.status_code = status_code or default_status
        super().__init__(self.message)

    def to_payload(self) -> dict[str, Any]:
        return {"error": {"code": self.code, "message": self.message, "detail": self.detail}}


def error_response(error: AppError) -> JSONResponse:
    return JSONResponse(status_code=error.status_code, content=error.to_payload())


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return error_response(exc)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(
            AppError("validation_error", detail=[_slim_error(e) for e in exc.errors()])
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = "not_found" if exc.status_code == 404 else "internal_error"
        message = str(exc.detail) if exc.detail else None
        return error_response(AppError(code, message, status_code=exc.status_code))

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        return error_response(AppError("internal_error", detail=type(exc).__name__))


#: Pydantic-Fehlerarten -> deutscher Text. Platzhalter kommen aus ``ctx``.
VALIDATION_TEXTS: dict[str, str] = {
    "greater_than_equal": "Mindestens {ge}.",
    "less_than_equal": "Höchstens {le}.",
    "greater_than": "Muss größer als {gt} sein.",
    "less_than": "Muss kleiner als {lt} sein.",
    "missing": "Dieser Wert fehlt.",
    "string_too_short": "Zu kurz.",
    "string_too_long": "Zu lang.",
    "int_parsing": "Muss eine ganze Zahl sein.",
    "int_type": "Muss eine ganze Zahl sein.",
    "float_parsing": "Muss eine Zahl sein.",
    "float_type": "Muss eine Zahl sein.",
    "bool_parsing": "Muss ja oder nein sein.",
    "bool_type": "Muss ja oder nein sein.",
    "string_type": "Muss Text sein.",
    "extra_forbidden": "Dieses Feld gibt es nicht.",
    "literal_error": "Dieser Wert ist hier nicht erlaubt.",
}

#: Pydantic stellt eigenen Validatoren diesen Text voran.
_VALUE_ERROR_PREFIX = "Value error, "


def _reason(entry: dict[str, Any]) -> str:
    """Deutscher Grund. Eigene Validatoren schreiben schon deutsch, Pydantic nicht."""
    template = VALIDATION_TEXTS.get(str(entry.get("type", "")))
    if template:
        try:
            return template.format(**(entry.get("ctx") or {}))
        except (KeyError, IndexError, ValueError):
            return template
    message = str(entry.get("msg", "")).strip()
    if message.startswith(_VALUE_ERROR_PREFIX):
        return message[len(_VALUE_ERROR_PREFIX) :]
    return message or "Dieser Wert ist nicht gültig."


def _slim_error(entry: dict[str, Any]) -> dict[str, Any]:
    """Validierungsfehler ohne Rohwerte (koennten Nutzerinhalte enthalten)."""
    return {
        "field": ".".join(str(p) for p in entry.get("loc", ()) if p != "body"),
        "reason": _reason(entry),
    }
