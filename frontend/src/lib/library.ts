import type { ComposeMode, LibraryEntry, PromptBundle } from "../types/api";

export const MODE_SHORT: Record<ComposeMode, string> = {
  improve: "Verbessern",
  image: "Bild",
  video: "Video",
};

const FIELD_TITLES: [keyof PromptBundle, string][] = [
  ["main_prompt", "Hauptprompt"],
  ["negative_prompt", "Negativprompt"],
  ["motion_prompt", "Bewegung"],
  ["audio_prompt", "Audio"],
  ["dialogue", "Dialog"],
  ["camera_notes", "Kamera / Framing"],
];

/** „1 Eintrag" statt „1 Einträge". */
export function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`;
}

/** „vor 3 Minuten", „gestern", „12.09.2026" — je nach Abstand. */
export function relativeTime(iso: string): string {
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return iso;
  const seconds = Math.round((Date.now() - then.getTime()) / 1000);
  if (seconds < 90) return "gerade eben";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `vor ${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `vor ${hours} h`;
  if (hours < 48) return "gestern";
  return then.toLocaleDateString("de-DE", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

export function exactTime(iso: string): string {
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return iso;
  return then.toLocaleString("de-DE", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Der Text, der beim Kopieren eines Eintrags in der Zwischenablage landet. */
export function bundleText(bundle: PromptBundle): string {
  return FIELD_TITLES.filter(([field]) => bundle[field])
    .map(([field, title]) => `## ${title}\n${bundle[field] as string}`)
    .join("\n\n");
}

/** Tag-Eingabe „nacht, portrait" → ["nacht", "portrait"]. */
export function parseTags(value: string): string[] {
  return value
    .split(",")
    .map((tag) => tag.trim())
    .filter(Boolean);
}

export function entrySummary(entry: LibraryEntry): string {
  const parts = [
    MODE_SHORT[entry.mode],
    entry.profile_label,
    plural(entry.variant_count, "Variante", "Varianten"),
  ];
  if (entry.duration_ms) parts.push(`${(entry.duration_ms / 1000).toFixed(1)} s`);
  return parts.join(" · ");
}
