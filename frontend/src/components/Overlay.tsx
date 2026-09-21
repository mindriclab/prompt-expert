import { useEffect, useRef } from "react";
import type { ReactNode } from "react";

interface Props {
  title: string;
  label: string;
  onClose: () => void;
  children: ReactNode;
  /** Zusätzliche Bedienelemente in der Kopfzeile, links vom Schließen. */
  head?: ReactNode;
  size?: "narrow" | "default" | "wide";
}

/** Vollflächiges Overlay über der App. Esc schließt, der Arbeitsstand bleibt stehen. */
export function Overlay({ title, label, onClose, children, head, size = "default" }: Props) {
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") closeRef.current();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="overlay" role="dialog" aria-modal="true" aria-label={label}>
      <div className={`overlay-card ${size}`}>
        <header className="overlay-head">
          <strong>{title}</strong>
          <span className="actions">
            {head}
            <button className="link-btn" onClick={onClose}>
              schließen (Esc)
            </button>
          </span>
        </header>
        <div className="overlay-body">{children}</div>
      </div>
    </div>
  );
}
