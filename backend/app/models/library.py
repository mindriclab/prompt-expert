"""Verträge der Prompt-Bibliothek.

Ein Eintrag ist **ein Lauf**, nicht eine Variante: Briefing, Referenzen, Analyse und
alle erzeugten Varianten gehören zusammen und werden zusammen gefunden, markiert,
exportiert und gelöscht.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.aspect import AspectRatio
from app.models.compose import ComposeMode, Intent, PromptBundle, PromptCritique, VideoSource
from app.models.reference import Role
from app.models.scene import SceneSpec
from app.models.settings import Density, Language

ExportFormat = Literal["txt", "json", "csv"]

MAX_TAG_LENGTH = 40
MAX_TAGS = 12
#: Die Kurzzeile in der Liste. Laenger wird in keiner Spalte lesbar.
TITLE_CHARS = 90


def normalise_tags(values: list[str]) -> list[str]:
    """Klein, getrimmt, ohne Dubletten, in stabiler Reihenfolge."""
    seen: dict[str, None] = {}
    for raw in values:
        tag = " ".join(raw.strip().lower().split())[:MAX_TAG_LENGTH]
        if tag:
            seen.setdefault(tag, None)
    return list(seen)[:MAX_TAGS]


def derive_title(briefing: str, input_prompt: str, bundles: list[PromptBundle]) -> str:
    """Kurzzeile für die Liste: das, was der Nutzer selbst geschrieben hat, zuerst."""
    first_prompt = bundles[0].main_prompt if bundles else ""
    for candidate in (briefing, input_prompt, first_prompt):
        text = " ".join(candidate.split())
        if text:
            return text[:TITLE_CHARS]
    return "ohne Text"


class LibraryThumb(BaseModel):
    """Vorschaubild einer Referenz, in der Bibliothek dauerhaft abgelegt."""

    position: int
    role: Role
    url: str = ""


class LibraryListItem(BaseModel):
    """Schlanke Zeile für Liste und Suche - ohne die Prompttexte."""

    id: int
    created_at: str
    title: str
    mode: ComposeMode
    #: Nur bei ``mode == "video"`` aussagekräftig.
    video_source: VideoSource = "startframe"
    profile_id: str
    profile_label: str
    language: Language
    density: Density
    favorite: bool
    tags: list[str] = Field(default_factory=list)
    variant_count: int = 0
    char_count: int = 0
    duration_ms: int = 0
    thumbs: list[LibraryThumb] = Field(default_factory=list)


class LibraryEntry(LibraryListItem):
    """Ein vollständiger Lauf."""

    intent: Intent = "reproduce"
    aspect_ratio: AspectRatio = "auto"
    clip_seconds: int | None = None
    model: str = ""
    vision_model: str | None = None
    input_prompt: str = ""
    briefing: str = ""
    shots: list[str] = Field(default_factory=list)
    critique: PromptCritique | None = None
    scene: SceneSpec | None = None
    bundles: list[PromptBundle] = Field(default_factory=list)


class LibraryPage(BaseModel):
    items: list[LibraryListItem] = Field(default_factory=list)
    total: int = 0
    offset: int = 0
    limit: int = 50


class LibraryStats(BaseModel):
    count: int = 0
    favorites: int = 0
    tags: list[str] = Field(default_factory=list)
    bytes_on_disk: int = 0


class LibraryUpdate(BaseModel):
    """Nur die Felder, die der Nutzer nachträglich ändern darf."""

    model_config = ConfigDict(extra="forbid")

    favorite: bool | None = None
    tags: list[str] | None = None

    @field_validator("tags")
    @classmethod
    def _clean(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else normalise_tags(value)


class ImportResult(BaseModel):
    imported: int = 0
    skipped: int = 0
    note: str | None = None


class ExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: Leer heisst: alles, was der aktuelle Filter liefert.
    ids: list[int] = Field(default_factory=list)
    format: ExportFormat = "txt"
