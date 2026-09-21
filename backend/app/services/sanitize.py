"""Nachbearbeitung der Modellausgabe.

Das Modell hält Profilregeln meistens ein, aber nicht immer. Diese Funktionen setzen
die harten Teile durch, statt sich auf Wohlverhalten zu verlassen.
"""

from __future__ import annotations

import re

#: Labels, die Modelle gern voranstellen ("**Prompt:**", "Main prompt:" ...).
LABEL_RE = re.compile(
    r"^\s*(?:\*\*|__|#+\s*)?"
    r"(?:main[ _-]?prompt|prompt|negative[ _-]?prompt|output|result|answer|ergebnis)"
    r"\s*(?:\*\*|__)?\s*[:：-]\s*(?:\*\*|__)?\s*",
    re.IGNORECASE,
)

FENCE_RE = re.compile(r"^```[a-z]*\s*|\s*```$", re.IGNORECASE)


def strip_decoration(text: str) -> str:
    """Entfernt Codezäune, vorangestellte Labels und umschließende Anführungszeichen."""
    cleaned = FENCE_RE.sub("", text.strip()).strip()
    previous = None
    while previous != cleaned:
        previous = cleaned
        cleaned = LABEL_RE.sub("", cleaned, count=1).strip()
    if len(cleaned) > 1 and cleaned[0] in '"“' and cleaned[-1] in '"”':
        cleaned = cleaned[1:-1].strip()
    return cleaned


def strip_banned_phrases(text: str, phrases: list[str]) -> tuple[str, list[str]]:
    """Entfernt verbotene Füllphrasen. Gibt den bereinigten Text und die Treffer zurück."""
    removed: list[str] = []
    cleaned = text
    for phrase in phrases:
        if not phrase.strip():
            continue
        pattern = re.compile(rf"(?<![\w-]){re.escape(phrase)}(?![\w-])", re.IGNORECASE)
        if pattern.search(cleaned):
            removed.append(phrase)
            cleaned = pattern.sub("", cleaned)
    if removed:
        cleaned = tidy_separators(cleaned)
    return cleaned, removed


def tidy_separators(text: str) -> str:
    """Räumt auf, was nach dem Entfernen von Begriffen übrig bleibt."""
    cleaned = re.sub(r"[ \t]{2,}", " ", text)
    cleaned = re.sub(r"\s+,", ",", cleaned)
    cleaned = re.sub(r"(,\s*){2,}", ", ", cleaned)
    cleaned = re.sub(r"\(\s*\)", "", cleaned)
    cleaned = re.sub(r"^[\s,]+", "", cleaned)
    cleaned = re.sub(r"[\s,]+$", "", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def enforce_max_chars(text: str, max_chars: int, grammar: str) -> tuple[str, bool]:
    """Kürzt an einer natürlichen Grenze. True, wenn gekürzt wurde."""
    if max_chars <= 0 or len(text) <= max_chars:
        return text, False
    window = text[:max_chars]
    separators = [", "] if grammar == "tags" else [". ", "! ", "? ", ", "]
    cut = -1
    for separator in separators:
        index = window.rfind(separator)
        if index > cut:
            # Satzzeichen gehoert noch zum Text, ein Komma am Ende nicht.
            cut = index + 1 if separator[0] in ".!?" else index
    if cut < max_chars * 0.6:
        cut = window.rfind(" ")
    trimmed = window[:cut] if cut > 0 else window
    return tidy_separators(trimmed), True


def normalise_tags(text: str) -> str:
    """Tag-Grammatik: kleinschreiben, Trenner vereinheitlichen, Dubletten raus."""
    parts = [part.strip().lower() for part in text.replace("\n", ",").split(",")]
    seen: dict[str, None] = {}
    for part in parts:
        if part:
            seen.setdefault(part, None)
    return ", ".join(seen)
