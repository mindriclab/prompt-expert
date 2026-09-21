"""Erkennung einer Shot-Gliederung im Briefing.

Gibt der Nutzer seine Einstellungen selbst vor (``Shot 1: ... Shot 2: ...``), soll der
erzeugte Prompt genau diese Struktur behalten. Ohne Gliederung entsteht ein durchgehender
Clip wie bisher.
"""

from __future__ import annotations

import re

#: Erkannte Schreibweisen: Shot 1, Shot #2, Szene 3, Scene 2, Cut 1, Take 4, Einstellung 2.
SHOT_RE = re.compile(
    r"(?:^|[\n\r;.\-–—]|\s)"
    r"(?P<label>(?:shot|szene|scene|cut|take|einstellung)\s*#?\s*(?P<number>\d{1,2}))"
    r"\s*[:.)\-–—]?",
    re.IGNORECASE,
)

#: Erst ab zwei Markierungen ist es eine Gliederung und kein beilaeufiges Wort.
MIN_SHOTS = 2


def detect_shots(text: str) -> list[str]:
    """Die Shot-Markierungen in der Reihenfolge ihres Auftretens, sonst eine leere Liste."""
    if not text:
        return []
    labels: list[str] = []
    numbers: list[int] = []
    for match in SHOT_RE.finditer(text):
        label = " ".join(match.group("label").split())
        number = int(match.group("number"))
        if number in numbers:
            continue
        labels.append(label)
        numbers.append(number)
    if len(labels) < MIN_SHOTS:
        return []
    return labels


def shot_pattern(labels: list[str]) -> re.Pattern[str] | None:
    """Regex, der genau diese Markierungen im erzeugten Prompt wiederfindet."""
    if not labels:
        return None
    return re.compile("|".join(re.escape(label) for label in labels), re.IGNORECASE)


def missing_shots(text: str, labels: list[str]) -> list[str]:
    """Welche vorgegebenen Shots stehen nicht im erzeugten Prompt?"""
    lowered = text.lower()
    missing = []
    for label in labels:
        # Toleriert abweichende Leerzeichen und Doppelpunkte.
        pattern = re.compile(re.escape(label).replace(r"\ ", r"\s*"), re.IGNORECASE)
        if not pattern.search(lowered):
            missing.append(label)
    return missing
