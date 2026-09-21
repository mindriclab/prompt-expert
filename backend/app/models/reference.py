"""Referenzbilder und ihre Rollen."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Role = Literal["subject", "style", "composition", "wardrobe", "environment"]

ROLE_HINTS: dict[Role, str] = {
    "subject": "the person or main object: appearance, body, wardrobe, pose, expression",
    "style": "the look only: rendering, grade, grain, artistic treatment - not the content",
    "composition": "framing, camera angle, where things sit in the frame - not the content",
    "wardrobe": "clothing, materials and accessories in detail",
    "environment": "the location, background, props, time of day, weather",
}

ROLE_LABELS: dict[Role, str] = {
    "subject": "Subjekt",
    "style": "Stil",
    "composition": "Komposition",
    "wardrobe": "Kleidung / Detail",
    "environment": "Umgebung",
}


class StoredImage(BaseModel):
    """Ein verarbeitetes Referenzbild im lokalen Sitzungsspeicher."""

    id: str
    original_name: str
    width: int
    height: int
    bytes: int
    thumb_url: str = ""

    def with_urls(self) -> StoredImage:
        self.thumb_url = f"/api/images/{self.id}/thumb"
        return self


class ReferenceInput(BaseModel):
    """Verweis auf ein hochgeladenes Bild plus seine Rolle."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[0-9a-f]{32}$")
    role: Role = "subject"

    @field_validator("id")
    @classmethod
    def _lowercase(cls, value: str) -> str:
        return value.lower()
