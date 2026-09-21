import type { AspectRatio } from "../types/api";

/** Reihenfolge für die Auswahl. "auto" heißt: nichts in den Prompt schreiben. */
export const ASPECT_RATIOS: AspectRatio[] = [
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
];

const NUMERIC = new Map<AspectRatio, number>(
  ASPECT_RATIOS.filter((ratio) => ratio !== "auto").map((ratio) => {
    const [width, height] = ratio.split(":").map(Number);
    return [ratio, width / height];
  }),
);

export function orientationOf(ratio: AspectRatio): string {
  if (ratio === "auto") return "";
  const [width, height] = ratio.split(":").map(Number);
  if (width === height) return "quadratisch";
  return width > height ? "quer" : "hoch";
}

/** Das nächstliegende Standardverhältnis zu einer Bildgröße. */
export function nearestRatio(width: number, height: number): AspectRatio {
  if (width <= 0 || height <= 0) return "auto";
  const actual = width / height;
  let best: AspectRatio = "auto";
  let distance = Number.POSITIVE_INFINITY;
  for (const [ratio, value] of NUMERIC) {
    const delta = Math.abs(value - actual);
    if (delta < distance) {
      distance = delta;
      best = ratio;
    }
  }
  return best;
}

export function ratioLabel(ratio: AspectRatio): string {
  if (ratio === "auto") return "automatisch";
  return `${ratio} (${orientationOf(ratio)})`;
}
