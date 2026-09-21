"""Verbindungs- und Modelltest fuer den konfigurierten Provider.

Liefert bewusst keine Exception, sondern ein Ergebnisobjekt mit Einzelpruefungen -
das Frontend soll auch sehen, was funktioniert, wenn etwas anderes scheitert.
"""

from __future__ import annotations

from app.core.errors import AppError
from app.models.provider import (
    ChatMessage,
    CompletionRequest,
    ModelInfo,
    ProviderCheck,
    ProviderTestResult,
)
from app.models.settings import AppSettings
from app.providers.base import missing_model_hint
from app.providers.factory import build_provider
from app.providers.ollama import OllamaProvider


def match_model(available: list[str], wanted: str) -> str | None:
    """Findet ein Modell, auch wenn der ``:latest``-Tag fehlt."""
    candidates = {name.lower(): name for name in available}
    for probe in (wanted, f"{wanted}:latest"):
        hit = candidates.get(probe.lower())
        if hit:
            return hit
    return None


def _similar(available: list[str], wanted: str, limit: int = 3) -> list[str]:
    stem = wanted.split(":")[0].split("/")[-1].lower()
    hits = [name for name in available if stem[:8] and stem[:8] in name.lower()]
    return hits[:limit]


async def run_provider_test(settings: AppSettings, *, probe: bool = False) -> ProviderTestResult:
    provider = build_provider(settings.provider)
    checks: list[ProviderCheck] = []
    result = ProviderTestResult(
        ok=False,
        kind=provider.kind,
        base_url=settings.provider.base_url,
        text_model=settings.models.text_model,
        vision_model=settings.models.vision_model,
    )

    health = await provider.health()
    result.latency_ms = health.latency_ms
    result.server_version = health.server_version
    if not health.reachable:
        checks.append(
            ProviderCheck(
                id="connection",
                label="Verbindung",
                status="fail",
                message=health.error_message or "Der Modellserver antwortet nicht.",
            )
        )
        result.checks = checks
        return result

    version = f" (Version {health.server_version})" if health.server_version else ""
    checks.append(
        ProviderCheck(
            id="connection",
            label="Verbindung",
            status="ok",
            message=f"Erreichbar in {health.latency_ms} ms{version}.",
        )
    )

    try:
        models = await provider.list_models()
    except AppError as exc:
        checks.append(
            ProviderCheck(id="models", label="Modellliste", status="fail", message=exc.message)
        )
        result.checks = checks
        return result

    if isinstance(provider, OllamaProvider) and models:
        await provider.enrich_capabilities(models)

    result.models = models
    names = [m.name for m in models]
    if not models:
        checks.append(
            ProviderCheck(
                id="models",
                label="Modellliste",
                status="fail",
                message="Der Server meldet kein einziges installiertes Modell.",
            )
        )
        result.checks = checks
        return result

    checks.append(
        ProviderCheck(
            id="models",
            label="Modellliste",
            status="ok",
            message=f"{len(models)} Modell(e) installiert.",
        )
    )

    text_hit = match_model(names, settings.models.text_model)
    checks.append(
        _model_check(
            "text_model", "Textmodell", settings.models.text_model, text_hit, names, provider.kind
        )
    )

    vision_hit = match_model(names, settings.models.vision_model)
    vision_check = _model_check(
        "vision_model",
        "Vision-Modell",
        settings.models.vision_model,
        vision_hit,
        names,
        provider.kind,
    )
    checks.append(vision_check)

    if vision_hit:
        info = next((m for m in models if m.name == vision_hit), None)
        checks.append(_vision_capability_check(info))
    else:
        checks.append(
            ProviderCheck(
                id="vision_capability",
                label="Bildunterstützung",
                status="skipped",
                message="Wird geprüft, sobald ein installiertes Vision-Modell gewählt ist.",
            )
        )

    if probe and text_hit:
        checks.append(await _probe_check(provider, settings, text_hit))
    elif probe:
        checks.append(
            ProviderCheck(
                id="probe",
                label="Testantwort",
                status="skipped",
                message="Kein installiertes Textmodell zum Testen.",
            )
        )

    result.checks = checks
    result.ok = not any(check.status == "fail" for check in checks)
    return result


def _model_check(
    check_id: str, label: str, wanted: str, hit: str | None, names: list[str], kind: str
) -> ProviderCheck:
    if hit:
        return ProviderCheck(
            id=check_id, label=label, status="ok", message=f"'{hit}' ist installiert."
        )
    similar = _similar(names, wanted)
    hint = f" Ähnlich vorhanden: {', '.join(similar)}." if similar else ""
    return ProviderCheck(
        id=check_id,
        label=label,
        status="fail",
        message=f"{missing_model_hint(wanted, kind)}.{hint}",
    )


def _vision_capability_check(info: ModelInfo | None) -> ProviderCheck:
    if info is None or info.supports_vision is None:
        return ProviderCheck(
            id="vision_capability",
            label="Bildunterstützung",
            status="warn",
            message="Der Server meldet keine Fähigkeiten. Die Bildanalyse wird es zeigen.",
        )
    if info.supports_vision:
        return ProviderCheck(
            id="vision_capability",
            label="Bildunterstützung",
            status="ok",
            message=f"'{info.name}' kann Bilder verarbeiten.",
        )
    return ProviderCheck(
        id="vision_capability",
        label="Bildunterstützung",
        status="fail",
        message=f"'{info.name}' kann keine Bilder verarbeiten. Wähle ein Vision-Modell.",
    )


async def _probe_check(provider, settings: AppSettings, model: str) -> ProviderCheck:
    request = CompletionRequest(
        model=model,
        messages=[
            ChatMessage(role="system", content="Answer with exactly one word."),
            ChatMessage(role="user", content="Reply with the single word: ready"),
        ],
        temperature=0.0,
        max_tokens=16,
        num_ctx=settings.models.num_ctx,
        disable_thinking=settings.models.disable_thinking,
        timeout_s=min(settings.provider.request_timeout_s, 120.0),
    )
    try:
        completion = await provider.complete(request)
    except AppError as exc:
        return ProviderCheck(id="probe", label="Testantwort", status="fail", message=exc.message)
    snippet = completion.text.strip().splitlines()[0][:60] if completion.text.strip() else "(leer)"
    return ProviderCheck(
        id="probe",
        label="Testantwort",
        status="ok",
        message=f"Antwort nach {completion.duration_ms} ms: \"{snippet}\"",
    )
