"""Verträge der Kompositions-Pipeline."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.aspect import AspectRatio
from app.models.reference import ReferenceInput
from app.models.scene import SceneSpec
from app.models.settings import Density, Language

Variant = Literal["precise", "cinematic", "experimental"]
ComposeMode = Literal["improve", "image", "video"]
#: Was mit den Referenzbildern im Bildmodus geschehen soll.
Intent = Literal["reproduce", "inspire"]
#: Woher das Bildmaterial im Videomodus kommt. Ersetzt dort die Absicht.
VideoSource = Literal["startframe", "references"]

ALL_VARIANTS: tuple[Variant, ...] = ("precise", "cinematic", "experimental")

MAX_INPUT_CHARS = 12000
MAX_BRIEFING_CHARS = 4000
MAX_REFERENCES = 6

#: Beim Nachbauen sind kreative Varianten sinnlos - dort zählt die Formulierungsstrategie.
VARIANT_LABELS: dict[str, dict[Variant, str]] = {
    "default": {
        "precise": "Präzise",
        "cinematic": "Cinematic",
        "experimental": "Experimentell",
    },
    "reproduce": {
        "precise": "Detailliert",
        "cinematic": "Kompakt",
        "experimental": "Anders formuliert",
    },
}


def label_set(
    mode: ComposeMode, intent: Intent, video_source: VideoSource = "startframe"
) -> dict[Variant, str]:
    # Startframe und Nachbauen sind beide treue Aufgaben - dort zaehlt die
    # Formulierungsstrategie, nicht die kreative Abweichung.
    if mode == "video":
        return VARIANT_LABELS["reproduce" if video_source == "startframe" else "default"]
    if mode == "image" and intent == "reproduce":
        return VARIANT_LABELS["reproduce"]
    return VARIANT_LABELS["default"]


def variant_label(
    variant: Variant,
    mode: ComposeMode,
    intent: Intent,
    video_source: VideoSource = "startframe",
) -> str:
    return label_set(mode, intent, video_source)[variant]


class ComposeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: ComposeMode = "improve"
    #: Nur im Bildmodus wirksam.
    intent: Intent = "reproduce"
    #: Nur im Videomodus wirksam: Startframe oder Identitaets-Referenzen.
    video_source: VideoSource = "startframe"
    #: Optionale Cliplaenge. None heisst: keine Laengenvorgabe und keine Laengenpruefung.
    clip_seconds: int | None = Field(default=None, ge=1, le=120)
    profile_id: str
    density: Density = "balanced"
    language: Language = "en"
    #: "auto" heisst: nichts in den Prompt schreiben.
    aspect_ratio: AspectRatio = "auto"
    #: Der vorhandene Prompt - Pflicht im Modus "improve".
    input_prompt: str = Field(default="", max_length=MAX_INPUT_CHARS)
    #: Absicht des Nutzers, im Bildmodus ohne Referenzen die einzige Quelle.
    briefing: str = Field(default="", max_length=MAX_BRIEFING_CHARS)
    references: list[ReferenceInput] = Field(default_factory=list)
    variants: list[Variant] = Field(default_factory=lambda: list(ALL_VARIANTS))

    @field_validator("input_prompt", "briefing")
    @classmethod
    def _trim(cls, value: str) -> str:
        return value.strip()

    @field_validator("variants")
    @classmethod
    def _unique_and_ordered(cls, value: list[Variant]) -> list[Variant]:
        if not value:
            raise ValueError("Mindestens eine Variante ist nötig")
        seen = dict.fromkeys(value)
        return [v for v in ALL_VARIANTS if v in seen]

    @field_validator("references")
    @classmethod
    def _limit_references(cls, value: list[ReferenceInput]) -> list[ReferenceInput]:
        if len(value) > MAX_REFERENCES:
            raise ValueError(f"Höchstens {MAX_REFERENCES} Referenzbilder")
        ids = [entry.id for entry in value]
        if len(set(ids)) != len(ids):
            raise ValueError("Dasselbe Referenzbild wurde mehrfach übergeben")
        return value

    @model_validator(mode="after")
    def _check_mode(self) -> ComposeRequest:
        if self.mode == "improve":
            if not self.input_prompt:
                raise ValueError("Es fehlt der Prompt, der verbessert werden soll")
            if self.references:
                raise ValueError("Der Modus 'improve' nimmt keine Referenzbilder")
        elif self.mode in ("image", "video") and not self.references and not self.briefing:
            raise ValueError("Es fehlt ein Referenzbild oder eine Beschreibung")
        if self.mode == "video" and self.video_source == "startframe" and len(self.references) > 1:
            raise ValueError(
                "Ein Startframe ist genau ein Bild. Für mehrere Bilder die Quelle "
                "'references' wählen"
            )
        return self

    @property
    def label_for(self) -> dict[Variant, str]:
        return label_set(self.mode, self.intent, self.video_source)

    @property
    def uses_startframe(self) -> bool:
        return self.mode == "video" and self.video_source == "startframe"


class PromptCritique(BaseModel):
    """Analyse eines vorhandenen Prompts."""

    summary: str = ""
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)


class PromptBundle(BaseModel):
    """Ein fertiges Ergebnis für genau eine Variante."""

    variant: Variant
    variant_label: str = ""
    profile_id: str
    main_prompt: str
    negative_prompt: str | None = None
    motion_prompt: str | None = None
    audio_prompt: str | None = None
    dialogue: str | None = None
    camera_notes: str | None = None
    rationale: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    char_count: int = 0
    duration_ms: int | None = None

    def fill_meta(self, label: str) -> PromptBundle:
        self.variant_label = label
        self.char_count = len(self.main_prompt)
        return self


class ComposeResponse(BaseModel):
    mode: ComposeMode
    intent: Intent
    profile_id: str
    profile_label: str
    language: Language
    density: Density
    model: str
    vision_model: str | None = None
    video_source: VideoSource = "startframe"
    clip_seconds: int | None = None
    shots: list[str] = Field(default_factory=list)
    aspect_ratio: AspectRatio = "auto"
    critique: PromptCritique | None = None
    scene: SceneSpec | None = None
    bundles: list[PromptBundle] = Field(default_factory=list)
    duration_ms: int = 0
    #: Kennung des Bibliothekseintrags. None heisst: nicht gespeichert.
    library_id: int | None = None
    #: Warum nicht gespeichert wurde - nur gesetzt, wenn die Bibliothek aktiv ist.
    library_error: str | None = None
