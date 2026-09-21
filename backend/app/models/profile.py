"""Schema der Zielprofile (``app/profiles/*.json``)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ProfileKind = Literal["image", "video", "edit"]
#: Woher das Bildmaterial bei Video kommt.
VideoSource = Literal["startframe", "references"]
Grammar = Literal["prose", "tags"]
ExplicitVocabulary = Literal["anatomical", "suggestive", "none"]

#: Felder, die ein Profil befuellen darf.
OUTPUT_FIELDS = {
    "main_prompt",
    "negative_prompt",
    "motion_prompt",
    "audio_prompt",
    "dialogue",
    "camera_notes",
}

DENSITY_FACTORS = {"sparse": 0.55, "balanced": 1.0, "detailed": 1.6}


class NegativePromptSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    used: bool = False
    style: Grammar = "tags"
    base: list[str] = Field(default_factory=list)


class LengthSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_chars: int = Field(ge=80, le=6000)
    max_chars: int = Field(ge=100, le=12000)

    @model_validator(mode="after")
    def _check_order(self) -> LengthSpec:
        if self.max_chars < self.target_chars:
            raise ValueError("max_chars muss mindestens target_chars sein")
        return self

    def for_density(self, density: str) -> int:
        factor = DENSITY_FACTORS.get(density, 1.0)
        return min(int(self.target_chars * factor), self.max_chars)


class RuleSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    must: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)


class Profile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9_]+$")
    label: str
    target: str
    kind: ProfileKind
    grammar: Grammar
    language: Literal["de", "en"] = "en"
    fields: list[str]
    negative_prompt: NegativePromptSpec = Field(default_factory=NegativePromptSpec)
    length: LengthSpec
    explicit_vocabulary: ExplicitVocabulary = "anatomical"
    rules: RuleSpec = Field(default_factory=RuleSpec)
    preferred_terms: list[str] = Field(default_factory=list)
    banned_phrases: list[str] = Field(default_factory=list)
    notes_for_model: str = ""
    #: Kurzer Hinweis, den die UI beim Profil anzeigt (z. B. Inhaltsfilter des Zielsystems).
    ui_note: str = ""
    #: Schreibt das Zielsystem das Seitenverhaeltnis in den Prompt, oder steht es im Workflow?
    aspect_ratio_in_prompt: bool = False
    #: Versteht das Zielsystem Zuordnungen wie "(Image 1)" bei mehreren Referenzen?
    reference_slots: bool = False
    #: Nimmt das Ziel einen Startframe, Identitaets-Referenzen oder beides?
    video_sources: list[VideoSource] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_fields(self) -> Profile:
        unknown = [f for f in self.fields if f not in OUTPUT_FIELDS]
        if unknown:
            raise ValueError(f"unbekannte Ausgabefelder: {', '.join(sorted(unknown))}")
        if "main_prompt" not in self.fields:
            raise ValueError("fields muss main_prompt enthalten")
        if self.negative_prompt.used and "negative_prompt" not in self.fields:
            raise ValueError("negative_prompt.used=true erfordert negative_prompt in fields")
        if not self.negative_prompt.used and "negative_prompt" in self.fields:
            raise ValueError("negative_prompt in fields erfordert negative_prompt.used=true")
        if self.kind == "image" and {"motion_prompt", "audio_prompt"} & set(self.fields):
            raise ValueError("Bildprofile dürfen keine Motion- oder Audiofelder fuehren")
        return self


class InvalidProfile(BaseModel):
    file: str
    error: str


class ProfileList(BaseModel):
    profiles: list[Profile]
    invalid: list[InvalidProfile] = Field(default_factory=list)
