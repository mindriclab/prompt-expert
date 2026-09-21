import { Overlay } from "./Overlay";

interface Props {
  onClose: () => void;
}

const SHORTCUTS: [string, string][] = [
  ["Strg + Enter", "Lauf starten — auch aus dem Textfeld heraus"],
  ["Esc", "Laufenden Lauf abbrechen, oder ein offenes Fenster schließen"],
  ["Strg + K", "Bibliothek öffnen, Cursor steht in der Suche"],
  ["Strg + ,", "Einstellungen öffnen"],
  ["1 · 2 · 3", "Zwischen den Varianten wechseln"],
  ["Alt + C", "Hauptprompt der offenen Variante kopieren"],
];

export function ShortcutHelp({ onClose }: Props) {
  return (
    <Overlay title="Tastaturkürzel" label="Tastaturkürzel" onClose={onClose} size="narrow">
      <dl className="shortcuts">
        {SHORTCUTS.map(([keys, what]) => (
          <div key={keys}>
            <dt>
              {keys.split(" · ").map((key) => (
                <kbd key={key}>{key}</kbd>
              ))}
            </dt>
            <dd>{what}</dd>
          </div>
        ))}
      </dl>
      <p className="hint">
        Die Zifferntasten greifen nur, wenn der Cursor in keinem Eingabefeld steht.
        Kopiert wird mit <kbd>Alt</kbd> + <kbd>C</kbd> statt mit Strg + Shift + C —
        letzteres fängt der Browser für seine Entwicklerwerkzeuge ab.
      </p>
    </Overlay>
  );
}
