import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { LibraryPanel } from "./components/LibraryPanel";
import { LibraryStrip } from "./components/LibraryStrip";
import { ReferenceStrip } from "./components/ReferenceStrip";
import { ResultPanel } from "./components/ResultPanel";
import { ScenePanel } from "./components/ScenePanel";
import { SettingsPanel } from "./components/SettingsPanel";
import { ShortcutHelp } from "./components/ShortcutHelp";
import { StatusBar } from "./components/StatusBar";
import { StageIndicator, type StageLine } from "./components/StageIndicator";
import { ASPECT_RATIOS, nearestRatio, ratioLabel } from "./lib/aspect";
import { copyText, composeStream, loadLibrary, loadProfiles, loadSettings, loadStatus } from "./lib/api";
import { CLIP_LENGTHS, detectShots } from "./lib/shots";
import type {
  ApiError,
  AppStatus,
  AspectRatio,
  LibraryListItem,
  ComposeMode,
  Density,
  Intent,
  Language,
  Profile,
  PromptBundle,
  PromptCritique,
  ReferenceItem,
  SceneSpec,
  Variant,
  VideoSource,
} from "./types/api";

const ALL_VARIANTS: Variant[] = ["precise", "cinematic", "experimental"];

const DENSITY_LABELS: Record<Density, string> = {
  sparse: "knapp",
  balanced: "ausgewogen",
  detailed: "detailliert",
};

const KIND_LABELS: Record<string, string> = {
  image: "Bild",
  video: "Video",
  edit: "Edit",
};

const MODE_LABELS: Record<ComposeMode, string> = {
  improve: "Prompt verbessern",
  image: "Bild → Bild",
  video: "Bild → Video",
};

const VARIANT_LABELS: Record<string, Record<Variant, string>> = {
  default: { precise: "Präzise", cinematic: "Cinematic", experimental: "Experimentell" },
  reproduce: { precise: "Detailliert", cinematic: "Kompakt", experimental: "Anders formuliert" },
};

const DENSITY_FACTOR: Record<Density, number> = { sparse: 0.55, balanced: 1, detailed: 1.6 };

/** Takt der Statusleiste. Ein Aufruf kostet zwei kurze Anfragen an Ollama. */
const STATUS_INTERVAL_MS = 20_000;

export default function App() {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [profileId, setProfileId] = useState("");
  const [mode, setMode] = useState<ComposeMode>("improve");
  const [intent, setIntent] = useState<Intent>("reproduce");
  const [videoSource, setVideoSource] = useState<VideoSource>("startframe");
  const [density, setDensity] = useState<Density>("balanced");
  const [language, setLanguage] = useState<Language>("en");
  const [clipSeconds, setClipSeconds] = useState<number | null>(null);
  const [aspectRatio, setAspectRatio] = useState<AspectRatio>("auto");
  // Solange der Nutzer nichts gewaehlt hat, darf die Referenz das Verhaeltnis setzen.
  const [ratioTouched, setRatioTouched] = useState(false);

  const [inputPrompt, setInputPrompt] = useState("");
  const [briefing, setBriefing] = useState("");
  const [references, setReferences] = useState<ReferenceItem[]>([]);

  const [status, setStatus] = useState<AppStatus | null>(null);
  const [checking, setChecking] = useState(true);
  const [statusError, setStatusError] = useState<string | null>(null);

  const [running, setRunning] = useState(false);
  const [stages, setStages] = useState<StageLine[]>([]);
  const [critique, setCritique] = useState<PromptCritique | null>(null);
  const [scene, setScene] = useState<SceneSpec | null>(null);
  const [bundles, setBundles] = useState<PromptBundle[]>([]);
  const [activeVariant, setActiveVariant] = useState<Variant>("precise");
  const [error, setError] = useState<ApiError | null>(null);
  const [totalMs, setTotalMs] = useState<number | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);

  const [libraryEnabled, setLibraryEnabled] = useState(true);
  const [recent, setRecent] = useState<LibraryListItem[]>([]);
  const [libraryTotal, setLibraryTotal] = useState(0);
  const [recentFailed, setRecentFailed] = useState(false);
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [libraryFocus, setLibraryFocus] = useState<number | null>(null);
  const [lastSavedId, setLastSavedId] = useState<number | null>(null);
  const [libraryNote, setLibraryNote] = useState<string | null>(null);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const activeVariantRef = useRef<Variant>("precise");
  activeVariantRef.current = activeVariant;

  // Jeder Modus sieht nur die Profile, die dort etwas taugen.
  const usableProfiles = useMemo(() => {
    if (mode === "video") {
      return profiles.filter(
        (p) => p.kind === "video" && p.video_sources.includes(videoSource),
      );
    }
    if (mode === "image") return profiles.filter((p) => p.kind !== "video");
    return profiles;
  }, [profiles, mode, videoSource]);
  const profile = usableProfiles.find((entry) => entry.id === profileId) ?? null;
  const startframe = mode === "video" && videoSource === "startframe";
  const compact = mode === "video" ? startframe : mode === "image" && intent === "reproduce";
  const labels = VARIANT_LABELS[compact ? "reproduce" : "default"];
  const withReferences = mode === "image" || mode === "video";
  const maxReferences = startframe ? 1 : 6;
  const shots = mode === "video" ? detectShots(briefing) : [];

  useEffect(() => {
    if (usableProfiles.length > 0 && !usableProfiles.some((entry) => entry.id === profileId)) {
      setProfileId(usableProfiles[0].id);
    }
  }, [usableProfiles, profileId]);

  const refreshRecent = useCallback(async () => {
    try {
      const page = await loadLibrary({ limit: 5 });
      setRecent(page.items);
      setLibraryTotal(page.total);
      setRecentFailed(false);
    } catch {
      // Eine nicht erreichbare Bibliothek darf die Werkstatt nicht stoeren -
      // aber sie darf auch nicht so tun, als waere einfach nichts gespeichert.
      setRecent([]);
      setLibraryTotal(0);
      setRecentFailed(true);
    }
  }, []);

  const refreshStatus = useCallback(async (quiet = false) => {
    if (!quiet) setChecking(true);
    try {
      setStatus(await loadStatus());
      setStatusError(null);
    } catch (failure) {
      setStatus(null);
      setStatusError((failure as Error).message);
    } finally {
      setChecking(false);
    }
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const [list, settings] = await Promise.all([loadProfiles(), loadSettings()]);
        setProfiles(list.profiles);
        setProfileId(
          list.profiles.some((entry) => entry.id === settings.defaults.profile_id)
            ? settings.defaults.profile_id
            : (list.profiles[0]?.id ?? ""),
        );
        setDensity(settings.defaults.density);
        setLanguage(settings.defaults.language);
        setLibraryEnabled(settings.library.enabled);
      } catch (failure) {
        setError({
          code: "backend_unreachable",
          message: `Profile und Einstellungen konnten nicht geladen werden. ${
            (failure as Error).message
          }`,
        });
      }
      void refreshStatus();
      void refreshRecent();
    })();
  }, [refreshStatus, refreshRecent]);

  // Die Leiste soll stimmen, ohne dass jemand "prüfen" drückt. Im Hintergrund
  // pausiert der Takt - ein verstecktes Fenster muss nichts abfragen.
  useEffect(() => {
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") void refreshStatus(true);
    }, STATUS_INTERVAL_MS);
    function onVisible() {
      if (document.visibilityState === "visible") void refreshStatus(true);
    }
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [refreshStatus]);

  useEffect(() => {
    if (ratioTouched || !withReferences || references.length === 0) return;
    const first = references[0];
    const detected = nearestRatio(first.width, first.height);
    if (detected !== "auto") setAspectRatio(detected);
  }, [references, withReferences, ratioTouched]);

  useEffect(() => {
    if (startframe && references.length > 1) setReferences(references.slice(0, 1));
  }, [startframe, references]);

  useEffect(() => () => abortRef.current?.abort(), []);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 1600);
    return () => window.clearTimeout(timer);
  }, [toast]);

  function cancel() {
    abortRef.current?.abort();
    abortRef.current = null;
    setRunning(false);
    setStages((lines) => lines.filter((line) => line.state === "done"));
  }

  async function run() {
    if (!canRun) return;

    const controller = new AbortController();
    abortRef.current = controller;

    setRunning(true);
    setError(null);
    setCritique(null);
    setScene(null);
    setBundles([]);
    setTotalMs(null);
    setStages([]);
    setActiveVariant("precise");
    setLastSavedId(null);
    setLibraryNote(null);

    await composeStream(
      {
        mode,
        intent,
        video_source: videoSource,
        clip_seconds: mode === "video" ? clipSeconds : null,
        profile_id: profileId,
        density,
        language,
        aspect_ratio: aspectRatio,
        input_prompt: mode === "improve" ? inputPrompt.trim() : "",
        briefing: briefing.trim(),
        references: withReferences ? references.map(({ id, role }) => ({ id, role })) : [],
        variants: ALL_VARIANTS,
      },
      {
        onStage: (stage) =>
          setStages((lines) => [
            ...lines.map((line) => ({ ...line, state: "done" as const })),
            { key: `${stage.stage}-${stage.index}`, text: stage.message, state: "running" },
          ]),
        onCritique: setCritique,
        onScene: setScene,
        onBundle: (bundle) =>
          setBundles((current) => {
            const next = [...current.filter((e) => e.variant !== bundle.variant), bundle];
            return ALL_VARIANTS.flatMap((v) => next.filter((e) => e.variant === v));
          }),
        onResult: (result) => {
          setTotalMs(result.duration_ms);
          setStages((lines) => lines.map((line) => ({ ...line, state: "done" as const })));
          setRunning(false);
          abortRef.current = null;
          setLastSavedId(result.library_id);
          setLibraryNote(result.library_error);
          if (result.library_id !== null) void refreshRecent();
          // Nach einem Lauf liegt das Modell im VRAM - die Leiste soll das zeigen.
          void refreshStatus(true);
        },
        onError: (failure) => {
          setError(failure);
          setStages([]);
          setRunning(false);
          abortRef.current = null;
        },
      },
      controller.signal,
    );
  }

  const hasInput =
    mode === "improve"
      ? inputPrompt.trim().length > 0
      : references.length > 0 || briefing.trim().length > 0;
  const canRun = Boolean(profileId) && hasInput && !running;

  const targetChars = profile
    ? Math.min(
        Math.round(profile.length.target_chars * DENSITY_FACTOR[density]),
        profile.length.max_chars,
      )
    : 0;

  // Die Kuerzel brauchen immer den aktuellen Stand, sollen den Listener aber
  // nicht bei jedem Tastendruck neu anmelden.
  const live = useRef({
    run,
    cancel,
    canRun,
    running,
    bundles,
    overlayOpen: false,
  });
  live.current = {
    run,
    cancel,
    canRun,
    running,
    bundles,
    overlayOpen: settingsOpen || libraryOpen || shortcutsOpen,
  };

  useEffect(() => {
    function editable(target: EventTarget | null): boolean {
      const node = target as HTMLElement | null;
      if (!node) return false;
      return (
        node.isContentEditable ||
        ["INPUT", "TEXTAREA", "SELECT"].includes(node.tagName)
      );
    }

    async function onKey(event: KeyboardEvent) {
      const state = live.current;
      const mod = event.ctrlKey || event.metaKey;

      if (mod && event.key === "Enter") {
        event.preventDefault();
        if (state.canRun) void state.run();
        return;
      }

      if (event.key === "Escape") {
        // Offene Fenster schliesst das Overlay selbst - sonst wuerde ein Esc
        // gleichzeitig das Fenster schliessen und den Lauf abbrechen.
        if (!state.overlayOpen && state.running) state.cancel();
        return;
      }

      // Auf manchen Belegungen liefert die Taste mit Modifikator ein anderes
      // Zeichen - `code` beschreibt die physische Taste und traegt dann.
      const is = (key: string, code: string) =>
        event.key.toLowerCase() === key || event.code === code;

      if (mod && !event.shiftKey && is("k", "KeyK")) {
        event.preventDefault();
        setLibraryFocus(null);
        setLibraryOpen(true);
        return;
      }

      if (mod && is(",", "Comma")) {
        event.preventDefault();
        setSettingsOpen(true);
        return;
      }

      // Alt+C statt Strg+Shift+C: letzteres faengt Chrome fuer den
      // DevTools-Inspektor ab, die Seite sieht es gar nicht erst.
      if (event.altKey && !mod && !state.overlayOpen && is("c", "KeyC")) {
        event.preventDefault();
        const bundle = state.bundles.find((entry) => entry.variant === activeVariantRef.current);
        if (!bundle) return;
        const ok = await copyText(bundle.main_prompt);
        setToast(ok ? "Hauptprompt kopiert" : "Kopieren ging nicht");
        return;
      }

      if (!mod && !event.altKey && !state.overlayOpen && !editable(event.target)) {
        const index = ["1", "2", "3"].indexOf(event.key);
        if (index >= 0 && state.bundles.some((entry) => entry.variant === ALL_VARIANTS[index])) {
          event.preventDefault();
          setActiveVariant(ALL_VARIANTS[index]);
        }
      }
    }

    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          Prompt Expert<span>{MODE_LABELS[mode]}</span>
        </div>
        <div className="actions">
          {toast && <span className="copied">{toast}</span>}
          {totalMs !== null && !running && !toast && (
            <span className="block-meta">fertig in {(totalMs / 1000).toFixed(1)} s</span>
          )}
          <button
            className="btn"
            onClick={() => {
              setLibraryFocus(null);
              setLibraryOpen(true);
            }}
          >
            Bibliothek
          </button>
          <button className="btn" onClick={() => setSettingsOpen(true)} disabled={running}>
            Einstellungen
          </button>
          {running ? (
            <button className="btn btn-danger" onClick={cancel}>
              Abbrechen
            </button>
          ) : (
            <button className="btn btn-primary" onClick={run} disabled={!canRun}>
              {mode === "improve" ? "Prompt verbessern" : "Prompt erzeugen"}
            </button>
          )}
        </div>
      </header>

      <div className="columns">
        <aside className="column">
          <div className="section">
            <p className="section-title">Modus</p>
            <div className="segments">
              {(Object.keys(MODE_LABELS) as ComposeMode[]).map((value) => (
                <button
                  key={value}
                  aria-pressed={mode === value}
                  onClick={() => setMode(value)}
                  disabled={running}
                >
                  {MODE_LABELS[value]}
                </button>
              ))}
            </div>
          </div>

          {withReferences && (
            <div className="section">
              <p className="section-title">
                {mode === "video" ? "Was liefert das Bild" : "Was mit dem Bild geschehen soll"}
              </p>
              <div className="segments">
                {mode === "video" ? (
                  <>
                    <button
                      aria-pressed={videoSource === "startframe"}
                      onClick={() => setVideoSource("startframe")}
                      disabled={running}
                    >
                      Startframe
                    </button>
                    <button
                      aria-pressed={videoSource === "references"}
                      onClick={() => setVideoSource("references")}
                      disabled={running}
                    >
                      Referenzen
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      aria-pressed={intent === "reproduce"}
                      onClick={() => setIntent("reproduce")}
                      disabled={running}
                    >
                      Nachbauen
                    </button>
                    <button
                      aria-pressed={intent === "inspire"}
                      onClick={() => setIntent("inspire")}
                      disabled={running}
                    >
                      Als Vorlage
                    </button>
                  </>
                )}
              </div>
              <p className="hint">
                {mode === "video"
                  ? startframe
                    ? "Das Modell sieht den Frame schon. Der Prompt beschreibt deshalb nur, was passiert — keine Bildbeschreibung."
                    : "Kein Startframe. Die Bilder liefern Identität und Look, die Szene entsteht aus deinem Briefing."
                  : intent === "reproduce"
                    ? "Beschreibt das Bild so genau wie möglich, damit du nah an dasselbe Ergebnis kommst. Identisch wird es ohne den Originalseed nicht."
                    : "Nimmt Look, Stimmung und Merkmale des Bildes und baut daraus die Szene aus deinem Briefing."}
              </p>
            </div>
          )}

          <div className="section">
            <p className="section-title">Zielprofil</p>
            <div className="field">
              <select value={profileId} onChange={(e) => setProfileId(e.target.value)}>
                {usableProfiles.map((entry) => (
                  <option key={entry.id} value={entry.id}>
                    {KIND_LABELS[entry.kind] ?? entry.kind} · {entry.label}
                  </option>
                ))}
              </select>
              {profile && (
                <p className="hint">
                  {profile.target}
                  <br />
                  {profile.grammar === "tags" ? "Danbooru-Tags" : "Fließtext"} ·{" "}
                  {profile.negative_prompt.used ? "mit Negativprompt" : "ohne Negativprompt"}
                </p>
              )}
              {profile?.reference_slots && references.length > 1 && (
                <p className="hint">
                  Die Zuordnung (Image 1), (Image 2) … steht im fertigen Prompt.
                </p>
              )}
              {profile?.ui_note && <p className="note-warn">{profile.ui_note}</p>}
            </div>
          </div>

          <div className="section">
            <p className="section-title">Prompt-Dichte</p>
            <div className="segments">
              {(Object.keys(DENSITY_LABELS) as Density[]).map((value) => (
                <button
                  key={value}
                  aria-pressed={density === value}
                  onClick={() => setDensity(value)}
                  disabled={running}
                >
                  {DENSITY_LABELS[value]}
                </button>
              ))}
            </div>
            {profile && <p className="hint">Ziellänge: {targetChars} Zeichen</p>}
          </div>

          {mode === "video" && (
            <div className="section">
              <p className="section-title">Clip-Länge</p>
              <div className="field">
                <select
                  value={clipSeconds === null ? "" : String(clipSeconds)}
                  disabled={running}
                  onChange={(e) =>
                    setClipSeconds(e.target.value === "" ? null : Number(e.target.value))
                  }
                >
                  {CLIP_LENGTHS.map((value) => (
                    <option key={String(value)} value={value === null ? "" : String(value)}>
                      {value === null ? "nicht angeben" : `${value} Sekunden`}
                    </option>
                  ))}
                </select>
                <p className="hint">
                  {clipSeconds === null
                    ? "Die Länge stellst du im Generator ein. Sie taucht im Prompt nicht auf."
                    : "Steuert nur das Tempo und die Zeitmarken. Im Prompttext steht sie nie."}
                </p>
              </div>
            </div>
          )}

          <div className="section">
            <p className="section-title">Seitenverhältnis</p>
            <div className="field">
              <select
                value={aspectRatio}
                disabled={running}
                onChange={(e) => {
                  setRatioTouched(true);
                  setAspectRatio(e.target.value as AspectRatio);
                }}
              >
                {ASPECT_RATIOS.map((ratio) => (
                  <option key={ratio} value={ratio}>
                    {ratioLabel(ratio)}
                  </option>
                ))}
              </select>
              <p className="hint">
                {aspectRatio === "auto"
                  ? "Steht nicht im Prompt. Du setzt es im Zielsystem."
                  : profile?.aspect_ratio_in_prompt
                    ? "Wird wörtlich in den Prompt geschrieben."
                    : "Dieses Ziel nimmt es aus dem Workflow — der Prompt hält die Bildform nur inhaltlich ein."}
                {!ratioTouched && references.length > 0 && aspectRatio !== "auto" && (
                  <> Aus der ersten Referenz übernommen.</>
                )}
              </p>
            </div>
          </div>

          <div className="section">
            <p className="section-title">Ausgabesprache</p>
            <div className="segments">
              <button
                aria-pressed={language === "en"}
                onClick={() => setLanguage("en")}
                disabled={running}
              >
                Englisch
              </button>
              <button
                aria-pressed={language === "de"}
                onClick={() => setLanguage("de")}
                disabled={running}
              >
                Deutsch
              </button>
            </div>
            <p className="hint">Analyse und Begründung bleiben immer deutsch.</p>
          </div>

        </aside>

        <section className="column">
          {!withReferences ? (
            <div className="section">
              <p className="section-title">Vorhandener Prompt</p>
              <textarea
                rows={14}
                value={inputPrompt}
                placeholder="Den Prompt einfügen, der verbessert werden soll."
                onChange={(e) => setInputPrompt(e.target.value)}
                disabled={running}
              />
              <p className="hint">
                <span className="char-count">{inputPrompt.length}</span> Zeichen
              </p>
            </div>
          ) : (
            <div className="section">
              <p className="section-title">
                {startframe ? "Startframe" : "Referenzbilder"}
              </p>
              <ReferenceStrip
                max={maxReferences}
                items={references}
                onChange={setReferences}
                onError={(message) => setError({ code: "image_rejected", message })}
                disabled={running}
              />
            </div>
          )}

          <div className="section">
            <p className="section-title">
              {mode === "improve"
                ? "Was daran anders werden soll"
                : mode === "video"
                  ? "Was im Clip passieren soll"
                  : intent === "reproduce"
                    ? "Ergänzungen zur Analyse"
                    : "Was daraus entstehen soll"}
            </p>
            <textarea
              rows={mode === "improve" ? 5 : 7}
              value={briefing}
              placeholder={
                mode === "improve"
                  ? "Optional. Zum Beispiel: härteres Licht, echte Fotografie statt Render."
                  : mode === "video"
                    ? "Bewegung, Kameraweg, Ton. Zum Beispiel: Sie dreht den Kopf zur Kamera, leichter Wind, langsamer Dolly-in."
                    : intent === "reproduce"
                      ? "Optional. Was das Modell im Bild übersehen könnte, oder was dir besonders wichtig ist."
                      : "Die Szene, die entstehen soll. Ohne Referenzbild ist das die einzige Vorgabe."
              }
              onChange={(e) => setBriefing(e.target.value)}
              disabled={running}
            />
            {shots.length > 0 && (
              <p className="hint">
                {shots.length} Shots erkannt ({shots.join(", ")}) — diese Gliederung bleibt im
                Prompt erhalten.
              </p>
            )}
          </div>
        </section>

        <section className="column">
          {error && (
            <div className="error-box">
              <strong>
                {error.code === "age_gate" ? "Analyse abgebrochen" : "Das hat nicht geklappt"}
              </strong>
              <p>{error.message}</p>
            </div>
          )}

          {stages.length > 0 && running && <StageIndicator lines={stages} onCancel={cancel} />}

          {!running && bundles.length === 0 && !error && (
            <p className="empty">
              {mode === "improve" ? (
                <>
                  Prompt links einfügen, Zielprofil wählen, oben starten.
                  <br />
                  Es entstehen drei Fassungen plus eine Analyse des Ausgangsprompts.
                </>
              ) : mode === "video" ? (
                <>
                  {startframe ? "Startframe" : "Referenzen"} links ablegen, beschreiben was
                  passieren soll, oben starten.
                  <br />
                  Ergebnis ist ein Block zum Kopieren — Bewegung, Kamera und Ton stecken darin.
                </>
              ) : (
                <>
                  Bild links ablegen, Rolle setzen, oben starten.
                  <br />
                  Die Bilder bleiben auf diesem Rechner.
                </>
              )}
            </p>
          )}

          {scene && <ScenePanel scene={scene} />}

          {libraryNote && <p className="note-warn">{libraryNote}</p>}

          {(bundles.length > 0 || critique) && (
            <ResultPanel
              critique={critique}
              bundles={bundles}
              active={activeVariant}
              labels={labels}
              onSelect={setActiveVariant}
              onReuse={(text) => {
                setMode("improve");
                setInputPrompt(text);
              }}
              requestedVariants={ALL_VARIANTS}
            />
          )}

          <LibraryStrip
            items={recent}
            total={libraryTotal}
            currentId={lastSavedId}
            enabled={libraryEnabled || libraryTotal > 0 || recentFailed}
            failed={recentFailed}
            onOpen={(id) => {
              setLibraryFocus(id);
              setLibraryOpen(true);
            }}
            onOpenAll={() => {
              setLibraryFocus(null);
              setLibraryOpen(true);
            }}
          />
        </section>
      </div>

      {settingsOpen && (
        <SettingsPanel
          profiles={profiles}
          onClose={() => setSettingsOpen(false)}
          // Die laufende Sitzung behaelt ihre Auswahl - nur der Status wird neu geprueft.
          onSaved={(saved) => {
            setLibraryEnabled(saved.library.enabled);
            void refreshStatus();
            void refreshRecent();
          }}
        />
      )}

      {libraryOpen && (
        <LibraryPanel
          profiles={profiles}
          initialId={libraryFocus}
          onClose={() => setLibraryOpen(false)}
          onReuse={(text) => {
            setMode("improve");
            setInputPrompt(text);
          }}
          onChanged={() => void refreshRecent()}
        />
      )}

      {shortcutsOpen && <ShortcutHelp onClose={() => setShortcutsOpen(false)} />}

      <StatusBar
        status={status}
        error={statusError}
        checking={checking}
        onRefresh={() => void refreshStatus()}
        onOpenSettings={() => setSettingsOpen(true)}
        onShowShortcuts={() => setShortcutsOpen(true)}
      />
    </div>
  );
}
