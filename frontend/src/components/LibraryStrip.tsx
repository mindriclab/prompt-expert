import { MODE_SHORT, relativeTime } from "../lib/library";
import type { LibraryListItem } from "../types/api";

interface Props {
  items: LibraryListItem[];
  total: number;
  /** Der Lauf, der gerade erzeugt wurde - bekommt eine Markierung. */
  currentId: number | null;
  enabled: boolean;
  /** Gesetzt, wenn die Liste gar nicht geladen werden konnte. */
  failed: boolean;
  onOpen: (id: number) => void;
  onOpenAll: () => void;
}

/**
 * Die letzten Läufe unter dem Ergebnis. Bewusst knapp: sie soll daran erinnern,
 * dass etwas da ist, nicht die Vollansicht ersetzen.
 */
export function LibraryStrip({
  items,
  total,
  currentId,
  enabled,
  failed,
  onOpen,
  onOpenAll,
}: Props) {
  if (!enabled) return null;

  return (
    <div className="panel lib-strip">
      <div className="lib-strip-head">
        <span className="block-title">Bibliothek</span>
        <button className="link-btn" onClick={onOpenAll}>
          {total > items.length ? `alle ${total} anzeigen` : "öffnen"}
        </button>
      </div>

      {items.length === 0 ? (
        <p className={failed ? "note-warn" : "hint"}>
          {failed
            ? "Die Bibliothek ist gerade nicht erreichbar."
            : "Noch nichts gespeichert. Jeder fertige Lauf landet hier von selbst."}
        </p>
      ) : (
        <ul className="lib-strip-list">
          {items.map((item) => (
            <li key={item.id}>
              <button
                className={`lib-row${item.id === currentId ? " current" : ""}`}
                onClick={() => onOpen(item.id)}
                title={item.title}
              >
                <span className="lib-row-title">
                  {item.favorite && <span className="star">★</span>}
                  <span className="lib-row-name">{item.title}</span>
                </span>
                <span className="lib-row-meta">
                  {MODE_SHORT[item.mode]} · {item.profile_id} · {relativeTime(item.created_at)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
