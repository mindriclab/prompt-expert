"""Seitenverhältnisse.

Das Seitenverhältnis ist eine Entscheidung des Nutzers, keine Erfindung des Modells.
Es wird deshalb deterministisch in den Prompt geschrieben, nicht nur erbeten.
"""

from __future__ import annotations

from typing import Literal

AspectRatio = Literal[
    "auto",
    "1:1",
    "4:5",
    "5:4",
    "2:3",
    "3:2",
    "3:4",
    "4:3",
    "9:16",
    "16:9",
    "21:9",
]

#: Reihenfolge für die UI.
ASPECT_RATIOS: tuple[AspectRatio, ...] = (
    "auto",
    "1:1",
    "4:5",
    "2:3",
    "3:4",
    "9:16",
    "5:4",
    "3:2",
    "4:3",
    "16:9",
    "21:9",
)

_NUMERIC = {
    ratio: int(ratio.split(":")[0]) / int(ratio.split(":")[1])
    for ratio in ASPECT_RATIOS
    if ratio != "auto"
}


def orientation_of(ratio: str) -> str:
    if ratio == "auto" or ":" not in ratio:
        return ""
    width, height = (int(part) for part in ratio.split(":"))
    if width == height:
        return "square"
    return "landscape" if width > height else "portrait"


def aspect_phrase(ratio: str) -> str:
    """Formulierung, die in den Prompt geht."""
    orientation = orientation_of(ratio)
    return f"{orientation} {ratio} aspect ratio" if orientation else ""


def nearest_ratio(width: int, height: int) -> AspectRatio:
    """Das nächstliegende Standardverhältnis zu einer Bildgröße."""
    if width <= 0 or height <= 0:
        return "auto"
    actual = width / height
    return min(_NUMERIC, key=lambda ratio: abs(_NUMERIC[ratio] - actual))  # type: ignore[return-value]


def contains_ratio(text: str, ratio: str) -> bool:
    """Steht das Verhältnis schon im Text? Erkennt 4:5 ebenso wie 4 : 5."""
    if ratio == "auto":
        return True
    compact = text.replace(" ", "").lower()
    return ratio.replace(" ", "") in compact
