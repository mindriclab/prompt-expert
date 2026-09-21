import { formatBytes } from "../lib/models";
import type { AppStatus } from "../types/api";

interface Props {
  status: AppStatus | null;
  error: string | null;
  checking: boolean;
  onRefresh: () => void;
  onOpenSettings: () => void;
  onShowShortcuts: () => void;
}

/**
 * Fußzeile als Statusleiste: immer sichtbar, immer aktuell. Sie ersetzt den
 * Modell-Block in der linken Spalte - der Modellname soll nicht an zwei Stellen
 * stehen, und die Einzelprüfungen haben ihren Platz in den Einstellungen.
 */
export function StatusBar({
  status,
  error,
  checking,
  onRefresh,
  onOpenSettings,
  onShowShortcuts,
}: Props) {
  const dot = error || (status && !status.reachable) ? "fail" : status ? "ok" : "warn";

  return (
    <footer className="footer statusbar">
      <span className="footer-brand">
        <img src="/mindric-lab.png" alt="mindric lab" />
        <span>© by mindric lab</span>
      </span>

      <button
        className="status-pill"
        onClick={onOpenSettings}
        title="Einstellungen öffnen"
      >
        <span className={`dot ${dot}`} />
        <span className="status-text">{describe(status, error, checking)}</span>
      </button>

      <span className="statusbar-right">
        <button className="link-btn" onClick={onRefresh} disabled={checking}>
          prüfen
        </button>
        <button className="link-btn" onClick={onShowShortcuts}>
          Tastaturkürzel
        </button>
        <span>lokal, ohne Cloud{status ? ` · v${status.version}` : ""}</span>
      </span>
    </footer>
  );
}

function describe(status: AppStatus | null, error: string | null, checking: boolean): string {
  if (error) return error;
  if (!status) return checking ? "Status wird geprüft" : "Status unbekannt";

  if (!status.reachable) {
    return status.error_message ?? `Unter ${status.base_url} antwortet kein Modellserver.`;
  }

  const parts = [status.text_model];
  if (status.text_model_loaded) {
    const vram = formatBytes(status.vram_bytes);
    parts.push(vram ? `${vram} im VRAM` : "im VRAM");
  } else if (status.provider_kind === "ollama") {
    // Ehrlich statt beruhigend: der erste Aufruf kostet dann die Ladezeit.
    parts.push("nicht geladen, erster Lauf dauert länger");
  }
  if (status.latency_ms !== null) parts.push(`${status.latency_ms} ms`);
  return parts.join(" · ");
}
