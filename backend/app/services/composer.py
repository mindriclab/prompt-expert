"""Kompositions-Pipeline.

Phase 1 ist beschreibend: entweder die Analyse eines vorhandenen Prompts oder die
Analyse der Referenzbilder zu einem SceneSpec. Phase 2 ist kreativ und sieht nur noch
das Ergebnis von Phase 1 - nie das Rohbild.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.errors import AppError
from app.models.aspect import aspect_phrase, contains_ratio
from app.models.compose import (
    ComposeRequest,
    ComposeResponse,
    PromptBundle,
    PromptCritique,
    Variant,
)
from app.models.profile import Profile
from app.models.provider import ChatMessage, CompletionRequest
from app.models.reference import ReferenceInput
from app.models.scene import SceneSpec, scene_schema
from app.models.settings import AppSettings
from app.prompts.composition import (
    bundle_schema,
    compose_messages,
    critique_messages,
    critique_schema,
)
from app.prompts.vision import vision_messages
from app.providers.base import ModelProvider
from app.services import images
from app.services.model_json import request_model_json
from app.services.motion_check import check_motion
from app.services.sanitize import (
    enforce_max_chars,
    normalise_tags,
    strip_banned_phrases,
    strip_decoration,
)
from app.services.shots import detect_shots, missing_shots

log = logging.getLogger(__name__)

Emit = Callable[[str, dict[str, Any]], Awaitable[None]]

#: Abweichung von der eingestellten Temperatur, damit die Varianten sich unterscheiden.
#: Beim Nachbauen bleibt alles niedrig - dort ist Treue wichtiger als Abwechslung.
VARIANT_TEMPERATURE_OFFSET: dict[str, dict[Variant, float]] = {
    "default": {"precise": -0.3, "cinematic": 0.0, "experimental": 0.25},
    "reproduce": {"precise": -0.4, "cinematic": -0.35, "experimental": -0.15},
    "video_reproduce": {"precise": -0.4, "cinematic": -0.35, "experimental": -0.15},
    "video_startframe": {"precise": -0.4, "cinematic": -0.35, "experimental": -0.15},
}

#: Die Bildanalyse soll beschreiben, nicht dichten.
VISION_TEMPERATURE = 0.2
VISION_MIN_TOKENS = 3072

TEXT_FIELDS = (
    "main_prompt",
    "negative_prompt",
    "motion_prompt",
    "audio_prompt",
    "dialogue",
    "camera_notes",
)


class BundleDraft(BaseModel):
    """Rohantwort des Modells. Felder je nach Profil vorhanden."""

    model_config = ConfigDict(extra="ignore")

    main_prompt: str = ""
    negative_prompt: str | None = None
    motion_prompt: str | None = None
    audio_prompt: str | None = None
    dialogue: str | None = None
    camera_notes: str | None = None
    rationale: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


async def _noop(_: str, __: dict[str, Any]) -> None:
    return None


def _completion_request(
    settings: AppSettings,
    messages: list[ChatMessage],
    temperature: float,
    *,
    vision: bool = False,
) -> CompletionRequest:
    return CompletionRequest(
        model=settings.models.vision_model if vision else settings.models.text_model,
        messages=messages,
        temperature=temperature,
        max_tokens=max(settings.models.max_tokens, VISION_MIN_TOKENS)
        if vision
        else settings.models.max_tokens,
        num_ctx=settings.models.num_ctx,
        disable_thinking=settings.models.disable_thinking,
        timeout_s=settings.provider.request_timeout_s,
    )


def brief_set_for(request: ComposeRequest) -> str:
    if request.mode == "video":
        return "video_startframe" if request.uses_startframe else "video_reproduce"
    if request.mode == "image" and request.intent == "reproduce":
        return "reproduce"
    return "default"


def finalise_bundle(
    draft: BundleDraft,
    profile: Profile,
    variant: Variant,
    label: str,
    aspect_ratio: str = "auto",
    references: list[ReferenceInput] | None = None,
    clip_seconds: int | None = None,
    shots: list[str] | None = None,
) -> PromptBundle:
    """Setzt die Profilregeln durch, die das Modell nur meistens einhält."""
    values: dict[str, str | None] = {}
    for field in TEXT_FIELDS:
        raw = getattr(draft, field, None)
        if field not in profile.fields or not raw or not raw.strip():
            values[field] = None
            continue
        values[field] = strip_decoration(raw)

    warnings = list(draft.warnings)
    main = values.get("main_prompt") or ""

    if profile.grammar == "tags":
        main = normalise_tags(main)
        if values.get("negative_prompt"):
            values["negative_prompt"] = normalise_tags(values["negative_prompt"])

    main, removed = strip_banned_phrases(main, profile.banned_phrases)
    if removed:
        warnings.append("Füllphrasen entfernt: " + ", ".join(removed))

    main, trimmed = enforce_max_chars(main, profile.length.max_chars, profile.grammar)
    if trimmed:
        warnings.append(f"Auf das Profil-Maximum von {profile.length.max_chars} Zeichen gekürzt.")

    # Referenz-Zuordnung ist Pflicht, kein Wunsch: fehlt sie, wird sie angehaengt.
    if main and profile.reference_slots and references:
        missing = [
            index for index in range(1, len(references) + 1) if f"(Image {index})" not in main
        ]
        if missing:
            attribution = ", ".join(
                f"{reference.role} from (Image {index})"
                for index, reference in enumerate(references, start=1)
            )
            separator = ", " if profile.grammar == "tags" else ". "
            main = f"{main.rstrip('.').rstrip()}{separator}Reference use: {attribution}"
            if profile.grammar != "tags":
                main += "."
            warnings.append(
                "Die Referenz-Zuordnung fehlte im Prompt und wurde ergänzt. "
                "Prüfe, ob sie am richtigen Element sitzt."
            )

    # Das Seitenverhaeltnis ist eine Nutzerentscheidung - es wird gesetzt, nicht erbeten.
    if main and profile.aspect_ratio_in_prompt and not contains_ratio(main, aspect_ratio):
        phrase = aspect_phrase(aspect_ratio)
        main = (
            f"{main}, {phrase}"
            if profile.grammar == "tags"
            else f"{main.rstrip('.').rstrip()}. {phrase[0].upper()}{phrase[1:]}."
        )

    if profile.kind == "video" and main:
        warnings.extend(check_motion(main, clip_seconds))
        if shots:
            absent = missing_shots(main, shots)
            if absent:
                warnings.append(
                    "Diese vorgegebenen Shots fehlen im Prompt: " + ", ".join(absent)
                )

    if not main:
        warnings.append("Das Modell lieferte keinen Hauptprompt.")
    values["main_prompt"] = main

    if profile.negative_prompt.used:
        values["negative_prompt"] = _merge_negative_base(
            values.get("negative_prompt"), profile.negative_prompt.base
        )
    else:
        values["negative_prompt"] = None

    return PromptBundle(
        variant=variant,
        profile_id=profile.id,
        main_prompt=values["main_prompt"] or "",
        negative_prompt=values["negative_prompt"],
        motion_prompt=values["motion_prompt"],
        audio_prompt=values["audio_prompt"],
        dialogue=values["dialogue"],
        camera_notes=values["camera_notes"],
        rationale=[line.strip() for line in draft.rationale if line.strip()],
        warnings=warnings,
    ).fill_meta(label)


def _merge_negative_base(existing: str | None, base: list[str]) -> str:
    """Grundbegriffe des Profils ergänzen, ohne Dubletten."""
    parts = [p.strip() for p in (existing or "").replace("\n", ",").split(",")]
    merged: dict[str, None] = {}
    for part in (*parts, *base):
        key = part.strip()
        if key and key.lower() not in {k.lower() for k in merged}:
            merged[key] = None
    return ", ".join(merged)


async def analyse_references(
    request: ComposeRequest,
    settings: AppSettings,
    provider: ModelProvider,
) -> SceneSpec:
    """Phase 1 für den Bildmodus. Bricht ab, wenn das Alter nicht eindeutig ist."""
    for_video = request.mode == "video"
    data_uris = [images.as_data_uri(reference.id) for reference in request.references]
    analysis_kind = request.video_source if for_video else request.intent
    messages = vision_messages(
        request.references, data_uris, request.briefing, analysis_kind, for_video
    )

    scene, _ = await request_model_json(
        provider,
        _completion_request(settings, messages, VISION_TEMPERATURE, vision=True),
        scene_schema(include_motion=for_video),
        SceneSpec,
    )

    if not scene.age_gate.clearly_adult:
        reason = scene.age_gate.reason.strip()
        raise AppError(
            "age_gate",
            "Diese Referenz wirkt nicht eindeutig erwachsen. Analyse abgebrochen."
            + (f" Begründung des Modells: {reason}" if reason else ""),
        )
    return scene


async def compose(
    request: ComposeRequest,
    settings: AppSettings,
    profile: Profile,
    provider: ModelProvider,
    emit: Emit | None = None,
) -> ComposeResponse:
    send = emit or _noop
    started = time.perf_counter()
    target_chars = profile.length.for_density(request.density)
    labels = request.label_for
    offsets = VARIANT_TEMPERATURE_OFFSET[brief_set_for(request)]

    critique: PromptCritique | None = None
    scene: SceneSpec | None = None
    shots = detect_shots(request.briefing) if profile.kind == "video" else []

    if request.mode == "improve":
        await send(
            "stage",
            {"stage": "critique", "message": "Prompt wird analysiert", "index": 0, "total": 1},
        )
        critique, _ = await request_model_json(
            provider,
            _completion_request(
                settings, critique_messages(request, profile), settings.models.temperature * 0.5
            ),
            critique_schema(),
            PromptCritique,
        )
        await send("critique", critique.model_dump())

    elif request.mode in ("image", "video") and request.references:
        count = len(request.references)
        message = (
            "Referenzbild wird analysiert"
            if count == 1
            else f"{count} Referenzbilder werden analysiert"
        )
        await send(
            "stage",
            {"stage": "analyse", "message": message, "index": 0, "total": 1},
        )
        scene = await analyse_references(request, settings, provider)
        await send("scene", scene.model_dump())

    bundles: list[PromptBundle] = []
    total = len(request.variants)
    schema = bundle_schema(profile)

    for index, variant in enumerate(request.variants, start=1):
        await send(
            "stage",
            {
                "stage": "compose",
                "message": f"Variante {index} von {total}: {labels[variant]}",
                "index": index,
                "total": total,
                "variant": variant,
            },
        )
        temperature = min(2.0, max(0.0, settings.models.temperature + offsets[variant]))
        draft, duration_ms = await request_model_json(
            provider,
            _completion_request(
                settings,
                compose_messages(request, profile, variant, target_chars, critique, scene),
                temperature,
            ),
            schema,
            BundleDraft,
        )
        bundle = finalise_bundle(
            draft,
            profile,
            variant,
            labels[variant],
            request.aspect_ratio,
            # Im Startframe-Modus gibt es keine Slots - dort ist nur ein Frame im Spiel.
            None if request.uses_startframe else request.references,
            request.clip_seconds,
            shots,
        )
        bundle.duration_ms = duration_ms
        bundles.append(bundle)
        await send("bundle", bundle.model_dump())

    return ComposeResponse(
        mode=request.mode,
        intent=request.intent,
        profile_id=profile.id,
        profile_label=profile.label,
        language=request.language,
        density=request.density,
        model=settings.models.text_model,
        video_source=request.video_source,
        clip_seconds=request.clip_seconds,
        shots=shots,
        aspect_ratio=request.aspect_ratio,
        vision_model=settings.models.vision_model if scene is not None else None,
        critique=critique,
        scene=scene,
        bundles=bundles,
        duration_ms=int((time.perf_counter() - started) * 1000),
    )
