/** Spiegelt die Erkennung im Backend, damit die UI sofort Rueckmeldung geben kann. */
const SHOT_RE = /(?:^|[\n\r;.\-–—]|\s)((?:shot|szene|scene|cut|take|einstellung)\s*#?\s*(\d{1,2}))/gi;

export function detectShots(text: string): string[] {
  if (!text) return [];
  const labels: string[] = [];
  const seen = new Set<number>();
  for (const match of text.matchAll(SHOT_RE)) {
    const number = Number(match[2]);
    if (seen.has(number)) continue;
    seen.add(number);
    labels.push(match[1].replace(/\s+/g, " ").trim());
  }
  return labels.length >= 2 ? labels : [];
}

/** Auswahl fuer die optionale Cliplaenge. null heisst: nicht angeben. */
export const CLIP_LENGTHS: (number | null)[] = [null, 3, 4, 5, 6, 8, 10, 12, 15, 20];
