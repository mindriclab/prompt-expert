import { useEffect, useId, useState } from "react";
import { copyText } from "../lib/api";
import { matchModel, modelMeta, optionLabel } from "../lib/models";
import type { ModelInfo } from "../types/api";

interface Props {
  label: string;
  value: string;
  models: ModelInfo[];
  /** False, solange keine Liste geladen werden konnte - dann ist nichts "fehlend". */
  listAvailable: boolean;
  /** Vision-Feld: belegbar bildunfaehige Modelle werden ausgegraut, nicht versteckt. */
  requireVision?: boolean;
  /** Nur bei Ollama ist `ollama pull` der richtige Rat. */
  showPull?: boolean;
  hint?: string;
  error?: string;
  disabled?: boolean;
  onChange: (value: string) => void;
}

export function ModelSelect({
  label,
  value,
  models,
  listAvailable,
  requireVision = false,
  showPull = true,
  hint,
  error,
  disabled,
  onChange,
}: Props) {
  const fieldId = useId();
  const [typing, setTyping] = useState(false);
  const [copied, setCopied] = useState(false);

  const installed = matchModel(models, value);
  const missing = listAvailable && value.trim().length > 0 && installed === null;

  useEffect(() => {
    if (!copied) return;
    const timer = window.setTimeout(() => setCopied(false), 1500);
    return () => window.clearTimeout(timer);
  }, [copied]);

  const pullCommand = `ollama pull ${value.trim()}`;

  return (
    <div className="field">
      <div className="field-head">
        <label className="field-label" htmlFor={fieldId}>
          {label}
        </label>
        <button className="link-btn" onClick={() => setTyping((on) => !on)} disabled={disabled}>
          {typing ? "aus der Liste" : "eintippen"}
        </button>
      </div>

      {typing ? (
        <input
          id={fieldId}
          type="text"
          value={value}
          spellCheck={false}
          disabled={disabled}
          onChange={(event) => onChange(event.target.value)}
        />
      ) : (
        <select
          id={fieldId}
          // Bei toleranter Zuordnung (`:latest`) muss der exakte Listenname stehen,
          // sonst zeigt das Dropdown ins Leere.
          value={installed ? installed.name : value}
          disabled={disabled}
          onChange={(event) => onChange(event.target.value)}
        >
          {installed === null && value.trim().length > 0 && (
            <option value={value}>
              {value}
              {missing ? " — nicht installiert" : ""}
            </option>
          )}
          {models.map((model) => (
            <option
              key={model.name}
              value={model.name}
              disabled={requireVision && model.supports_vision === false}
            >
              {optionLabel(model, requireVision)}
            </option>
          ))}
        </select>
      )}

      {installed && <p className="hint">{modelMeta(installed)}</p>}

      {missing && showPull && (
        <div className="pull-hint">
          <code>{pullCommand}</code>
          <button
            className="btn btn-small"
            onClick={async () => setCopied(await copyText(pullCommand))}
          >
            {copied ? "kopiert" : "kopieren"}
          </button>
        </div>
      )}
      {missing && !showPull && (
        <p className="note-warn">Dieser Server meldet das Modell nicht.</p>
      )}

      {!listAvailable && (
        <p className="hint">Keine Modellliste — der Server antwortet gerade nicht.</p>
      )}
      {requireVision && installed?.supports_vision === null && (
        <p className="note-warn">
          Der Server meldet für dieses Modell keine Fähigkeiten. Ob es Bilder kann, zeigt erst
          die Analyse.
        </p>
      )}
      {requireVision && installed?.supports_vision === false && (
        <p className="note-warn">Dieses Modell kann keine Bilder. Die Bildmodi laufen damit nicht.</p>
      )}

      {hint && <p className="hint">{hint}</p>}
      {error && <p className="field-error">{error}</p>}
    </div>
  );
}
