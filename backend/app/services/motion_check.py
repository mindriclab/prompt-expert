"""Widerspruchsprüfung für Videoprompts.

Diese Prüfungen laufen auf dem fertigen Text, nicht auf dem Wunsch an das Modell.
Sie korrigieren nichts still, sondern melden - der Nutzer entscheidet.

Wichtig: Gegenläufige Kamerabewegungen sind über eine Zeitachse hinweg völlig legitim
(erst heranfahren, dann zurückziehen). Ein Widerspruch entsteht erst, wenn beides im
selben Zeitfenster steht. Deshalb wird immer je Zeitfenster geprüft.
"""

from __future__ import annotations

import re

from app.services.shots import SHOT_RE

#: [0-4 sec] oder [11+ sec]
BRACKET_RE = re.compile(r"\[\s*(\d+)\s*(?:-\s*(\d+)|\s*(\+))\s*sec\s*\]", re.IGNORECASE)

CAMERA_GROUPS: dict[str, tuple[str, ...]] = {
    "heran": (
        "push in",
        "pushes in",
        "pushing in",
        "dolly in",
        "dollies in",
        "zoom in",
        "zooms in",
        "track in",
        "moves closer",
        "moving closer",
        "closes the distance",
        "closing the distance",
    ),
    "weg": (
        "pull back",
        "pulls back",
        "pulling back",
        "dolly out",
        "dollies out",
        "zoom out",
        "zooms out",
        "track out",
        "pulls away",
        "pulling away",
        "moves back",
        "moving back",
        "moves away",
    ),
    "links": ("pan left", "pans left", "truck left", "orbit left", "orbits left", "moves left"),
    "rechts": (
        "pan right",
        "pans right",
        "truck right",
        "orbit right",
        "orbits right",
        "moves right",
    ),
}

CAMERA_STATIC = (
    "static shot",
    "locked-off",
    "locked off",
    "camera holds",
    "camera remains static",
    "camera is static",
    "camera stays static",
    "stationary camera",
    "camera does not move",
    "fixed camera",
)

CAMERA_MOVING = tuple(term for group in CAMERA_GROUPS.values() for term in group) + (
    "handheld drift",
    "crane up",
    "crane down",
    "tilt up",
    "tilt down",
    "tracking shot",
    "orbits",
)

SUBJECT_STILL = (
    "stands still",
    "standing still",
    "stands motionless",
    "motionless",
    "does not move",
    "remains still",
    "remains motionless",
    "static pose",
    "holds the pose",
    "frozen in place",
)

SUBJECT_LOCOMOTION = (
    "running",
    "runs toward",
    "runs across",
    "sprinting",
    "sprints",
    "jogging",
    "jogs",
    "walks briskly",
    "walking briskly",
    "striding",
    "strides",
    "dashes",
    "leaps",
)

OPPOSITES = (("heran", "weg"), ("links", "rechts"))


def _found(text: str, terms: tuple[str, ...]) -> list[str]:
    lowered = text.lower()
    return [term for term in terms if term in lowered]


def parse_brackets(text: str) -> list[tuple[int, int | None]]:
    """Alle Zeitfenster in Reihenfolge des Auftretens. ``None`` heißt offenes Ende."""
    windows: list[tuple[int, int | None]] = []
    for match in BRACKET_RE.finditer(text):
        start = int(match.group(1))
        end = int(match.group(2)) if match.group(2) else None
        windows.append((start, end))
    return windows


def split_segments(text: str) -> list[str]:
    """Text in Abschnitte zerlegen: an Zeitmarken oder Shot-Markierungen.

    Ohne beides gilt der ganze Text als ein Abschnitt. Das ist wichtig, weil
    gegenlaeufige Kamerabewegungen nur innerhalb eines Abschnitts ein Widerspruch sind.
    """
    matches = sorted(
        [*BRACKET_RE.finditer(text), *SHOT_RE.finditer(text)], key=lambda m: m.start()
    )
    if not matches:
        return [text]
    segments = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        segments.append(text[start:end])
    return segments


def check_camera(text: str) -> list[str]:
    """Gegenläufige oder unvereinbare Kameraangaben im selben Zeitfenster."""
    warnings: list[str] = []
    for index, segment in enumerate(split_segments(text), start=1):
        for first, second in OPPOSITES:
            hits_a = _found(segment, CAMERA_GROUPS[first])
            hits_b = _found(segment, CAMERA_GROUPS[second])
            if hits_a and hits_b:
                warnings.append(
                    f"Gegenläufige Kamerabewegung im selben Abschnitt {index}: "
                    f"'{hits_a[0]}' und '{hits_b[0]}'. Eine davon streichen oder in ein "
                    "eigenes Zeitfenster legen."
                )
        still = _found(segment, CAMERA_STATIC)
        moving = _found(segment, CAMERA_MOVING)
        if still and moving:
            warnings.append(
                f"Abschnitt {index} sagt gleichzeitig feste und bewegte Kamera: "
                f"'{still[0]}' und '{moving[0]}'."
            )
    return warnings


def check_subject_motion(text: str) -> list[str]:
    """Stillstand und Fortbewegung im selben Zeitfenster."""
    warnings: list[str] = []
    for index, segment in enumerate(split_segments(text), start=1):
        still = _found(segment, SUBJECT_STILL)
        moving = _found(segment, SUBJECT_LOCOMOTION)
        if still and moving:
            warnings.append(
                f"Abschnitt {index} beschreibt Stillstand und Fortbewegung zugleich: "
                f"'{still[0]}' und '{moving[0]}'."
            )
    return warnings


def check_timeline(text: str, clip_seconds: int | None) -> list[str]:
    """Reihenfolge, Überlappung, Lücken und Clip-Länge der Zeitfenster."""
    windows = parse_brackets(text)
    if not windows:
        return []

    warnings: list[str] = []
    if windows[0][0] != 0:
        warnings.append(
            f"Die Zeitachse beginnt bei {windows[0][0]} s statt bei 0 s."
        )

    previous_end: int | None = None
    for start, end in windows:
        if previous_end is not None:
            if start < previous_end:
                warnings.append(
                    f"Zeitfenster überlappen: [{start}…] beginnt vor dem Ende des "
                    f"vorherigen bei {previous_end} s."
                )
            elif start > previous_end:
                warnings.append(
                    f"Lücke auf der Zeitachse zwischen {previous_end} s und {start} s."
                )
        if end is not None and end <= start:
            warnings.append(f"Zeitfenster [{start}-{end} sec] endet nicht nach seinem Beginn.")
        previous_end = end if end is not None else previous_end

    if clip_seconds:
        last_start, last_end = windows[-1]
        longest = last_end if last_end is not None else last_start
        if longest > clip_seconds:
            warnings.append(
                f"Die Zeitachse reicht bis {longest} s, das Profil rechnet mit rund "
                f"{clip_seconds} s Cliplänge. Kürzen oder das Profil anpassen."
            )
    return warnings


def check_motion(text: str, clip_seconds: int | None = None) -> list[str]:
    """Alle Prüfungen auf einmal, ohne Dubletten."""
    warnings: list[str] = []
    findings = (
        *check_timeline(text, clip_seconds),
        *check_camera(text),
        *check_subject_motion(text),
    )
    for finding in findings:
        if finding not in warnings:
            warnings.append(finding)
    return warnings
