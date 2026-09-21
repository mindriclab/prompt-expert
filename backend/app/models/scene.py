"""SceneSpec - das Ergebnis der Bildanalyse.

Beschreibend, nicht kreativ. Die Komposition arbeitet danach nur noch mit diesem
Objekt und sieht das Rohbild nie wieder.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.reference import Role


class SubjectSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")

    role: Role = "subject"
    appearance: str = ""
    build: str = ""
    hair: str = ""
    face: str = ""
    wardrobe: str = ""
    pose: str = ""
    expression: str = ""
    explicit_detail: str = ""
    continuity_features: list[str] = Field(default_factory=list)


class SceneBlock(BaseModel):
    model_config = ConfigDict(extra="ignore")

    setting: str = ""
    time_of_day: str = ""
    atmosphere: str = ""
    props: list[str] = Field(default_factory=list)


class VisualBlock(BaseModel):
    model_config = ConfigDict(extra="ignore")

    style: str = ""
    composition: str = ""
    lighting: str = ""
    palette: list[str] = Field(default_factory=list)
    materials: list[str] = Field(default_factory=list)


class CameraBlock(BaseModel):
    model_config = ConfigDict(extra="ignore")

    shot: str = ""
    lens: str = ""
    angle: str = ""
    focus: str = ""
    depth_of_field: str = ""


class MotionBlock(BaseModel):
    """Erst ab Meilenstein 4 angefordert."""

    model_config = ConfigDict(extra="ignore")

    subject_motion: str = ""
    camera_motion: str = ""
    beats: list[str] = Field(default_factory=list)
    physics_notes: str = ""


class AgeGate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    clearly_adult: bool = True
    reason: str = ""


class SceneSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")

    subjects: list[SubjectSpec] = Field(default_factory=list)
    scene: SceneBlock = Field(default_factory=SceneBlock)
    visual: VisualBlock = Field(default_factory=VisualBlock)
    camera: CameraBlock = Field(default_factory=CameraBlock)
    motion: MotionBlock | None = None
    uncertainties: list[str] = Field(default_factory=list)
    age_gate: AgeGate = Field(default_factory=AgeGate)


def _strings(*names: str) -> dict[str, Any]:
    return {name: {"type": "string"} for name in names}


def _string_list() -> dict[str, Any]:
    return {"type": "array", "items": {"type": "string"}}


def _object(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def scene_schema(*, include_motion: bool = False) -> dict[str, Any]:
    """JSON-Schema für die Vision-Antwort."""
    subject = _object(
        {
            **_strings(
                "role",
                "appearance",
                "build",
                "hair",
                "face",
                "wardrobe",
                "pose",
                "expression",
                "explicit_detail",
            ),
            "continuity_features": _string_list(),
        }
    )

    properties: dict[str, Any] = {
        "subjects": {"type": "array", "items": subject},
        "scene": _object(
            {**_strings("setting", "time_of_day", "atmosphere"), "props": _string_list()}
        ),
        "visual": _object(
            {
                **_strings("style", "composition", "lighting"),
                "palette": _string_list(),
                "materials": _string_list(),
            }
        ),
        "camera": _object(_strings("shot", "lens", "angle", "focus", "depth_of_field")),
        "uncertainties": _string_list(),
        "age_gate": _object({"clearly_adult": {"type": "boolean"}, "reason": {"type": "string"}}),
    }

    if include_motion:
        properties["motion"] = _object(
            {
                **_strings("subject_motion", "camera_motion", "physics_notes"),
                "beats": _string_list(),
            }
        )

    return _object(properties)
