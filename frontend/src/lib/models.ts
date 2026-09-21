import type { ModelInfo } from "../types/api";

/**
 * Findet ein Modell, auch wenn der `:latest`-Tag fehlt - dieselbe Toleranz wie
 * `match_model` im Backend. Ohne sie gilt ein installiertes Modell als fehlend.
 */
export function matchModel(models: ModelInfo[], wanted: string): ModelInfo | null {
  const needle = wanted.trim().toLowerCase();
  if (!needle) return null;
  for (const probe of [needle, `${needle}:latest`]) {
    const hit = models.find((model) => model.name.toLowerCase() === probe);
    if (hit) return hit;
  }
  return null;
}

export function formatBytes(bytes: number | null): string | null {
  if (bytes === null || bytes <= 0) return null;
  const gb = bytes / 1_000_000_000;
  if (gb >= 1) return `${gb.toLocaleString("de-DE", { maximumFractionDigits: 1 })} GB`;
  return `${Math.round(bytes / 1_000_000).toLocaleString("de-DE")} MB`;
}

/** Drei Zustaende, nicht zwei: `null` heisst unbekannt und wird auch so gesagt. */
export function visionLabel(supports: boolean | null): string {
  if (supports === true) return "Bilder: ja";
  if (supports === false) return "Bilder: nein";
  return "Bilder: unbekannt";
}

/** Kurzzeile unter der Auswahl: "32B · Q4_K_M · 18,6 GB · Bilder: ja". */
export function modelMeta(model: ModelInfo): string {
  return [
    model.parameter_size,
    model.quantization,
    formatBytes(model.size_bytes),
    visionLabel(model.supports_vision),
  ]
    .filter(Boolean)
    .join(" · ");
}

/** Beschriftung im Dropdown. Nicht-Vision-Modelle bleiben sichtbar, nur gesperrt. */
export function optionLabel(model: ModelInfo, requireVision: boolean): string {
  const parts = [model.parameter_size, formatBytes(model.size_bytes)].filter(Boolean);
  if (requireVision && model.supports_vision === false) parts.push("keine Bilder");
  if (requireVision && model.supports_vision === null) parts.push("Bilder unbekannt");
  return parts.length > 0 ? `${model.name} — ${parts.join(", ")}` : model.name;
}
