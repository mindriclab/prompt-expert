import { useCallback, useEffect, useId, useState } from "react";
import {
  fieldErrors,
  loadModels,
  loadRunning,
  loadSettings,
  resetSettings,
  saveSettings,
  testProvider,
} from "../lib/api";
import { formatBytes } from "../lib/models";
import type {
  AppSettings,
  Density,
  Language,
  ModelInfo,
  Profile,
  ProviderCheck,
  ProviderKind,
  RunningModels,
} from "../types/api";
import { CheckList } from "./CheckList";
import { ModelSelect } from "./ModelSelect";
import { Overlay } from "./Overlay";

interface Props {
  profiles: Profile[];
  onClose: () => void;
  /** App aktualisiert damit den Verbindungsstatus in der linken Spalte. */
  onSaved: (settings: AppSettings) => void;
}

const DENSITY_LABELS: Record<Density, string> = {
  sparse: "knapp",
  balanced: "ausgewogen",
  detailed: "detailliert",
};

const PROVIDER_LABELS: Record<ProviderKind, string> = {
  ollama: "Ollama",
  openai_compat: "OpenAI-kompatibel",
};

export function SettingsPanel({ profiles, onClose, onSaved }: Props) {
  const [draft, setDraft] = useState<AppSettings | null>(null);
  const [stored, setStored] = useState<AppSettings | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [models, setModels] = useState<ModelInfo[]>([]);
  const [listAvailable, setListAvailable] = useState(false);
  const [listError, setListError] = useState<string | null>(null);
  const [stale, setStale] = useState(false);
  const [running, setRunning] = useState<RunningModels | null>(null);

  const [checks, setChecks] = useState<ProviderCheck[]>([]);
  const [testing, setTesting] = useState(false);

  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saveError, setSaveError] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);
  const [advanced, setAdvanced] = useState(false);
  const [confirmClose, setConfirmClose] = useState(false);
  const [revealKey, setRevealKey] = useState(false);

  const baseUrlId = useId();
  const apiKeyId = useId();
  const profileId = useId();

  const dirty =
    draft !== null && stored !== null && JSON.stringify(draft) !== JSON.stringify(stored);

  const refreshList = useCallback(async (settings: AppSettings) => {
    setListError(null);
    const [list, vram] = await Promise.allSettled([
      loadModels({ provider: settings.provider }),
      loadRunning({ provider: settings.provider }),
    ]);
    if (list.status === "fulfilled") {
      setModels(list.value);
      setListAvailable(true);
      setStale(false);
    } else {
      setModels([]);
      setListAvailable(false);
      setListError((list.reason as Error).message);
    }
    setRunning(vram.status === "fulfilled" ? vram.value : null);
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const settings = await loadSettings();
        setDraft(settings);
        setStored(settings);
        void refreshList(settings);
      } catch {
        setLoadError("Die Einstellungen konnten nicht geladen werden. Läuft start.bat noch?");
      }
    })();
  }, [refreshList]);

  useEffect(() => {
    if (!flash) return;
    const timer = window.setTimeout(() => setFlash(null), 2500);
    return () => window.clearTimeout(timer);
  }, [flash]);

  function patch(update: Partial<AppSettings>) {
    setDraft((current) => (current ? { ...current, ...update } : current));
    setSaveError(null);
  }

  async function runTest() {
    if (!draft) return;
    setTesting(true);
    try {
      const result = await testProvider({ provider: draft.provider, models: draft.models });
      setChecks(result.checks);
      setModels(result.models);
      setListAvailable(result.models.length > 0);
      setListError(null);
      setStale(false);
      setRunning(await loadRunning({ provider: draft.provider }).catch(() => null));
    } catch (failure) {
      setChecks([
        { id: "backend", label: "Backend", status: "fail", message: (failure as Error).message },
      ]);
    } finally {
      setTesting(false);
    }
  }

  async function save() {
    if (!draft) return;
    setBusy(true);
    setErrors({});
    setSaveError(null);
    try {
      const next = await saveSettings(draft);
      setDraft(next);
      setStored(next);
      setFlash("Gespeichert.");
      onSaved(next);
      void refreshList(next);
    } catch (failure) {
      const fields = fieldErrors(failure);
      setErrors(fields);
      setSaveError(
        Object.keys(fields).length > 0
          ? "Einzelne Werte sind nicht gültig — sie sind oben rot markiert."
          : (failure as Error).message,
      );
    } finally {
      setBusy(false);
    }
  }

  async function reset() {
    setBusy(true);
    try {
      const next = await resetSettings();
      setDraft(next);
      setStored(next);
      setErrors({});
      setSaveError(null);
      setFlash("Auf Auslieferungszustand zurückgesetzt.");
      onSaved(next);
      void refreshList(next);
    } catch (failure) {
      setSaveError((failure as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function requestClose() {
    if (dirty) setConfirmClose(true);
    else onClose();
  }

  if (loadError) {
    return (
      <Overlay title="Einstellungen" label="Einstellungen" onClose={onClose}>
        <div className="error-box">
          <strong>Das hat nicht geklappt</strong>
          <p>{loadError}</p>
        </div>
      </Overlay>
    );
  }

  if (!draft) {
    return (
      <Overlay title="Einstellungen" label="Einstellungen" onClose={onClose}>
        <p className="empty">Einstellungen werden geladen …</p>
      </Overlay>
    );
  }

  const isOllama = draft.provider.kind === "ollama";

  return (
    <Overlay title="Einstellungen" label="Einstellungen" onClose={requestClose}>
      <div className="settings-grid">
        <section className="section">
          <p className="section-title">Modellserver</p>
          <div className="segments">
            {(Object.keys(PROVIDER_LABELS) as ProviderKind[]).map((kind) => (
              <button
                key={kind}
                aria-pressed={draft.provider.kind === kind}
                disabled={busy}
                onClick={() => {
                  patch({ provider: { ...draft.provider, kind } });
                  setStale(true);
                }}
              >
                {PROVIDER_LABELS[kind]}
              </button>
            ))}
          </div>

          <div className="field">
            <label className="field-label" htmlFor={baseUrlId}>
              Base URL
            </label>
            <input
              id={baseUrlId}
              type="text"
              spellCheck={false}
              value={draft.provider.base_url}
              disabled={busy}
              onChange={(event) => {
                patch({ provider: { ...draft.provider, base_url: event.target.value } });
                setStale(true);
              }}
            />
            <p className="hint">
              {isOllama
                ? "Ollama läuft üblicherweise auf http://127.0.0.1:11434."
                : "Adresse des Servers, ohne /v1 — LM Studio, llama.cpp, KoboldCpp, vLLM."}
            </p>
            {errors["provider.base_url"] && (
              <p className="field-error">{errors["provider.base_url"]}</p>
            )}
          </div>

          <div className="field">
            <div className="field-head">
              <label className="field-label" htmlFor={apiKeyId}>
                API-Key
              </label>
              <button className="link-btn" onClick={() => setRevealKey((on) => !on)}>
                {revealKey ? "verbergen" : "anzeigen"}
              </button>
            </div>
            <input
              id={apiKeyId}
              type={revealKey ? "text" : "password"}
              spellCheck={false}
              autoComplete="off"
              value={draft.provider.api_key ?? ""}
              disabled={busy}
              onChange={(event) =>
                patch({ provider: { ...draft.provider, api_key: event.target.value || null } })
              }
            />
            <p className="hint">
              Nur nötig, wenn der Server einen verlangt. Bleibt auf diesem Rechner.
            </p>
          </div>

          <div className="settings-actions">
            <button className="btn" onClick={runTest} disabled={testing || busy}>
              {testing ? "prüft …" : "Verbindung testen"}
            </button>
            {stale && (
              <span className="block-meta">Server geändert — testen für die neue Liste.</span>
            )}
          </div>
          <CheckList checks={checks} />
        </section>

        <section className="section">
          <p className="section-title">Modelle</p>
          <ModelSelect
            label="Textmodell"
            value={draft.models.text_model}
            models={models}
            listAvailable={listAvailable}
            showPull={isOllama}
            disabled={busy}
            error={errors["models.text_model"]}
            onChange={(text_model) => patch({ models: { ...draft.models, text_model } })}
          />
          <ModelSelect
            label="Vision-Modell"
            value={draft.models.vision_model}
            models={models}
            listAvailable={listAvailable}
            requireVision
            showPull={isOllama}
            disabled={busy}
            error={errors["models.vision_model"]}
            hint="Für Bild → Prompt und Bild → Video. Darf dasselbe Modell sein."
            onChange={(vision_model) => patch({ models: { ...draft.models, vision_model } })}
          />
          {listError && <p className="note-warn">{listError}</p>}
          {draft.models.text_model !== draft.models.vision_model && (
            <p className="hint">
              Zwei verschiedene Modelle kosten in den Bildmodi einen Modellwechsel im VRAM.
            </p>
          )}

          <div className="vram">
            <p className="field-label">Im VRAM</p>
            {running === null && <p className="hint">Nicht abgefragt.</p>}
            {running && !running.supported && <p className="hint">{running.note}</p>}
            {running?.supported && running.models.length === 0 && (
              <p className="hint">
                Gerade kein Modell geladen. Der erste Aufruf dauert dann deutlich länger.
              </p>
            )}
            {running?.supported &&
              running.models.map((entry) => (
                <p className="vram-row" key={entry.name}>
                  <span className="dot ok" />
                  {entry.name}
                  {entry.size_vram_bytes !== null && (
                    <> · {formatBytes(entry.size_vram_bytes)} VRAM</>
                  )}
                </p>
              ))}
          </div>
        </section>

        <section className="section">
          <p className="section-title">Referenzbilder</p>
          <NumberField
            label="Längste Kante (px)"
            value={draft.images.max_edge}
            min={384}
            max={2048}
            step={64}
            disabled={busy}
            error={errors["images.max_edge"]}
            hint="Kleiner heißt schneller und weniger Kontext. 1024–1280 reicht meistens."
            onChange={(max_edge) => patch({ images: { ...draft.images, max_edge } })}
          />
          <NumberField
            label="JPEG-Qualität"
            value={draft.images.jpeg_quality}
            min={50}
            max={100}
            step={5}
            disabled={busy}
            error={errors["images.jpeg_quality"]}
            onChange={(jpeg_quality) => patch({ images: { ...draft.images, jpeg_quality } })}
          />
          <NumberField
            label="Referenzen je Durchlauf"
            value={draft.images.max_images}
            min={1}
            max={6}
            step={1}
            disabled={busy}
            error={errors["images.max_images"]}
            onChange={(max_images) => patch({ images: { ...draft.images, max_images } })}
          />
          <NumberField
            label="Maximale Dateigröße (MB)"
            value={draft.images.max_upload_mb}
            min={1}
            max={100}
            step={1}
            disabled={busy}
            error={errors["images.max_upload_mb"]}
            onChange={(max_upload_mb) => patch({ images: { ...draft.images, max_upload_mb } })}
          />
        </section>

        <section className="section">
          <p className="section-title">Standards</p>
          <div className="field">
            <label className="field-label" htmlFor={profileId}>
              Zielprofil
            </label>
            <select
              id={profileId}
              value={draft.defaults.profile_id}
              disabled={busy}
              onChange={(event) =>
                patch({ defaults: { ...draft.defaults, profile_id: event.target.value } })
              }
            >
              {profiles.map((profile) => (
                <option key={profile.id} value={profile.id}>
                  {profile.label}
                </option>
              ))}
            </select>
            {errors["defaults.profile_id"] && (
              <p className="field-error">{errors["defaults.profile_id"]}</p>
            )}
          </div>

          <div className="field">
            <label className="field-label">Ausgabesprache</label>
            <div className="segments">
              {(["en", "de"] as Language[]).map((language) => (
                <button
                  key={language}
                  aria-pressed={draft.defaults.language === language}
                  disabled={busy}
                  onClick={() => patch({ defaults: { ...draft.defaults, language } })}
                >
                  {language === "en" ? "Englisch" : "Deutsch"}
                </button>
              ))}
            </div>
          </div>

          <div className="field">
            <label className="field-label">Prompt-Dichte</label>
            <div className="segments">
              {(Object.keys(DENSITY_LABELS) as Density[]).map((density) => (
                <button
                  key={density}
                  aria-pressed={draft.defaults.density === density}
                  disabled={busy}
                  onClick={() => patch({ defaults: { ...draft.defaults, density } })}
                >
                  {DENSITY_LABELS[density]}
                </button>
              ))}
            </div>
          </div>
          <p className="hint">
            Standards gelten für den nächsten Start. Was in der linken Spalte eingestellt ist,
            bleibt so lange stehen.
          </p>
        </section>

        <section className="section">
          <p className="section-title">Bibliothek</p>
          <div className="field">
            <label className="check">
              <input
                type="checkbox"
                checked={draft.library.enabled}
                disabled={busy}
                onChange={(event) =>
                  patch({ library: { ...draft.library, enabled: event.target.checked } })
                }
              />
              Jeden fertigen Lauf automatisch speichern
            </label>
            <p className="hint">
              Aus heißt: nichts Neues wird abgelegt. Was schon drin ist, bleibt und lässt sich
              weiter durchsuchen.
            </p>
          </div>

          <div className="field">
            <label className="check">
              <input
                type="checkbox"
                checked={draft.library.store_thumbnails}
                disabled={busy || !draft.library.enabled}
                onChange={(event) =>
                  patch({
                    library: { ...draft.library, store_thumbnails: event.target.checked },
                  })
                }
              />
              Vorschaubilder der Referenzen mitspeichern
            </label>
            <p className="hint">
              Kopien im Datenverzeichnis, etwa 20 kB je Bild. Ohne sie bleibt der Eintrag,
              aber ohne Bild.
            </p>
          </div>

          <NumberField
            label="Obergrenze"
            value={draft.library.max_entries}
            min={100}
            max={100000}
            step={100}
            disabled={busy}
            error={errors["library.max_entries"]}
            hint="Darüber fallen die ältesten Einträge weg. Favoriten nie."
            onChange={(max_entries) => patch({ library: { ...draft.library, max_entries } })}
          />
        </section>

        <section className="section settings-wide">
          <p className="section-title">
            Modellparameter
            <button className="link-btn" onClick={() => setAdvanced((on) => !on)}>
              {advanced ? "einklappen" : "ausklappen"}
            </button>
          </p>
          {advanced ? (
            <div className="settings-row">
              <NumberField
                label="Temperatur (Basis)"
                value={draft.models.temperature}
                min={0}
                max={2}
                step={0.05}
                disabled={busy}
                error={errors["models.temperature"]}
                hint="Die Varianten versetzen diesen Wert: präzise darunter, experimentell darüber."
                onChange={(temperature) => patch({ models: { ...draft.models, temperature } })}
              />
              <NumberField
                label="Kontextfenster (num_ctx)"
                value={draft.models.num_ctx}
                min={2048}
                max={262144}
                step={2048}
                disabled={busy}
                error={errors["models.num_ctx"]}
                hint="Größer kostet VRAM. Bei Timeouts zuerst hier heruntergehen."
                onChange={(num_ctx) => patch({ models: { ...draft.models, num_ctx } })}
              />
              <NumberField
                label="Antwortlänge (max_tokens)"
                value={draft.models.max_tokens}
                min={256}
                max={32768}
                step={256}
                disabled={busy}
                error={errors["models.max_tokens"]}
                onChange={(max_tokens) => patch({ models: { ...draft.models, max_tokens } })}
              />
              <NumberField
                label="Verbindungs-Timeout (s)"
                value={draft.provider.connect_timeout_s}
                min={1}
                max={60}
                step={1}
                disabled={busy}
                error={errors["provider.connect_timeout_s"]}
                onChange={(connect_timeout_s) =>
                  patch({ provider: { ...draft.provider, connect_timeout_s } })
                }
              />
              <NumberField
                label="Antwort-Timeout (s)"
                value={draft.provider.request_timeout_s}
                min={10}
                max={1800}
                step={10}
                disabled={busy}
                error={errors["provider.request_timeout_s"]}
                hint="Gilt je Modellaufruf. Der erste Aufruf nach einem Ollama-Neustart dauert am längsten."
                onChange={(request_timeout_s) =>
                  patch({ provider: { ...draft.provider, request_timeout_s } })
                }
              />
              <div className="field">
                <label className="field-label">Denkschritte</label>
                <label className="check">
                  <input
                    type="checkbox"
                    checked={draft.models.disable_thinking}
                    disabled={busy}
                    onChange={(event) =>
                      patch({
                        models: { ...draft.models, disable_thinking: event.target.checked },
                      })
                    }
                  />
                  abschalten (think: false)
                </label>
                <p className="hint">
                  Aus ist richtig: die Pipeline erzwingt JSON, sichtbare Denkschritte stören dabei.
                </p>
              </div>
            </div>
          ) : (
            <p className="hint">
              Temperatur {draft.models.temperature.toLocaleString("de-DE")} · Kontext{" "}
              {draft.models.num_ctx.toLocaleString("de-DE")} · Antwort-Timeout{" "}
              {draft.provider.request_timeout_s} s
            </p>
          )}
        </section>
      </div>

      {saveError && (
        <div className="error-box">
          <strong>Nicht gespeichert</strong>
          <p>{saveError}</p>
        </div>
      )}

      {confirmClose && (
        <div className="confirm-bar">
          <span>Ungespeicherte Änderungen verwerfen?</span>
          <button className="btn btn-small" onClick={() => setConfirmClose(false)}>
            zurück
          </button>
          <button className="btn btn-small btn-danger" onClick={onClose}>
            verwerfen
          </button>
        </div>
      )}

      <div className="settings-footer">
        <button className="btn" onClick={reset} disabled={busy}>
          Zurücksetzen
        </button>
        <span className="block-meta">
          {flash ?? (dirty ? "Ungespeicherte Änderungen" : "Alles gespeichert")}
        </span>
        <button className="btn" onClick={requestClose} disabled={busy}>
          Schließen
        </button>
        <button className="btn btn-primary" onClick={save} disabled={busy || !dirty}>
          {busy ? "speichert …" : "Speichern"}
        </button>
      </div>
    </Overlay>
  );
}

interface NumberProps {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  hint?: string;
  error?: string;
  disabled?: boolean;
  onChange: (value: number) => void;
}

/**
 * Haelt den Rohtext selbst, damit Zwischenstaende wie "0." beim Tippen nicht
 * sofort auf eine Zahl zurechtgebogen werden.
 */
function NumberField({
  label,
  value,
  min,
  max,
  step,
  hint,
  error,
  disabled,
  onChange,
}: NumberProps) {
  const fieldId = useId();
  const [raw, setRaw] = useState(String(value));

  useEffect(() => {
    setRaw((current) => (Number(current) === value ? current : String(value)));
  }, [value]);

  return (
    <div className="field">
      <label className="field-label" htmlFor={fieldId}>
        {label}
      </label>
      <input
        id={fieldId}
        type="number"
        value={raw}
        min={min}
        max={max}
        step={step}
        disabled={disabled}
        onChange={(event) => {
          setRaw(event.target.value);
          const parsed = Number(event.target.value);
          if (event.target.value !== "" && Number.isFinite(parsed)) onChange(parsed);
        }}
      />
      {hint && <p className="hint">{hint}</p>}
      {error && <p className="field-error">{error}</p>}
    </div>
  );
}
