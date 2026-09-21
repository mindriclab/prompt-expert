"""Export der Bibliothek als ``.txt``, ``.json`` oder ``.csv``.

Drei Formate, drei Zwecke: ``txt`` zum Lesen und Weiterreichen, ``json`` als
vollständige Sicherung, ``csv`` für Tabellen. Nur ``json`` ist verlustfrei.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime

from app.models.compose import PromptBundle
from app.models.library import ExportFormat, LibraryEntry

MEDIA_TYPES: dict[ExportFormat, str] = {
    "txt": "text/plain; charset=utf-8",
    "json": "application/json; charset=utf-8",
    "csv": "text/csv; charset=utf-8",
}

MODE_LABELS = {"improve": "Prompt verbessern", "image": "Bild", "video": "Video"}

#: Reihenfolge wie in der Oberflaeche.
FIELDS: list[tuple[str, str]] = [
    ("main_prompt", "Hauptprompt"),
    ("negative_prompt", "Negativprompt"),
    ("motion_prompt", "Bewegung"),
    ("audio_prompt", "Audio"),
    ("dialogue", "Dialog"),
    ("camera_notes", "Kamera / Framing"),
]

CSV_COLUMNS = [
    "id",
    "erstellt",
    "modus",
    "profil",
    "sprache",
    "dichte",
    "favorit",
    "tags",
    "variante",
    "hauptprompt",
    "negativprompt",
    "kamera",
    "briefing",
    "ausgangsprompt",
    "modell",
]


def filename(fmt: ExportFormat, count: int) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M")
    scope = "bibliothek" if count != 1 else "prompt"
    return f"prompt-expert_{scope}_{stamp}.{fmt}"


def _local_time(iso: str) -> str:
    """Im Textexport liest sich Ortszeit besser. CSV und JSON behalten ISO."""
    try:
        return datetime.fromisoformat(iso).astimezone().strftime("%d.%m.%Y, %H:%M")
    except ValueError:
        return iso


def render(entries: list[LibraryEntry], fmt: ExportFormat) -> str:
    if fmt == "json":
        return _as_json(entries)
    if fmt == "csv":
        return _as_csv(entries)
    return _as_text(entries)


def _as_json(entries: list[LibraryEntry]) -> str:
    payload = {
        "exported_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "count": len(entries),
        "entries": [entry.model_dump() for entry in entries],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _as_csv(entries: list[LibraryEntry]) -> str:
    buffer = io.StringIO()
    # Excel unter Windows liest Semikolon zuverlaessig, Komma je nach Gebietsschema nicht.
    writer = csv.writer(buffer, delimiter=";", quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    # Ein Eintrag ohne Varianten soll trotzdem eine Zeile bekommen.
    empty = PromptBundle(variant="precise", profile_id="", main_prompt="")
    for entry in entries:
        for bundle in entry.bundles or [empty]:
            writer.writerow(
                [
                    entry.id,
                    entry.created_at,
                    MODE_LABELS.get(entry.mode, entry.mode),
                    entry.profile_id,
                    entry.language,
                    entry.density,
                    "ja" if entry.favorite else "nein",
                    ", ".join(entry.tags),
                    bundle.variant_label or bundle.variant,
                    bundle.main_prompt,
                    bundle.negative_prompt or "",
                    bundle.camera_notes or "",
                    entry.briefing,
                    entry.input_prompt,
                    entry.model,
                ]
            )
    return buffer.getvalue()


def _as_text(entries: list[LibraryEntry]) -> str:
    blocks: list[str] = []
    for entry in entries:
        lines = [
            "=" * 70,
            f"#{entry.id} · {_local_time(entry.created_at)} · "
            f"{MODE_LABELS.get(entry.mode, entry.mode)}",
            f"Profil: {entry.profile_label} ({entry.profile_id}) · "
            f"Sprache: {entry.language} · Dichte: {entry.density}",
        ]
        if entry.tags:
            lines.append(f"Tags: {', '.join(entry.tags)}")
        if entry.favorite:
            lines.append("Favorit: ja")
        if entry.briefing:
            lines.append(f"\nBriefing:\n{entry.briefing}")
        if entry.input_prompt:
            lines.append(f"\nAusgangsprompt:\n{entry.input_prompt}")

        for bundle in entry.bundles:
            lines.append(f"\n--- {bundle.variant_label or bundle.variant} ---")
            for field, title in FIELDS:
                value = getattr(bundle, field, None)
                if value:
                    lines.append(f"\n## {title}\n{value}")
            if bundle.warnings:
                lines.append("\n## Warnungen")
                lines += [f"- {warning}" for warning in bundle.warnings]
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) + "\n" if blocks else "Keine Einträge.\n"
