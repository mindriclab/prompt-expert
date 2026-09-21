import { useCallback, useEffect, useRef, useState } from "react";
import {
  clearLibrary,
  deleteLibraryEntry,
  exportLibrary,
  importLibrary,
  loadLibrary,
  loadLibraryEntry,
  loadLibraryStats,
  updateLibraryEntry,
} from "../lib/api";
import {
  MODE_SHORT,
  bundleText,
  entrySummary,
  exactTime,
  parseTags,
  plural,
  relativeTime,
} from "../lib/library";
import type {
  ComposeMode,
  ExportFormat,
  VideoSource,
  LibraryEntry,
  LibraryListItem,
  LibraryStats,
  Profile,
  Variant,
} from "../types/api";
import { FieldBlock } from "./FieldBlock";
import { Overlay } from "./Overlay";

interface Props {
  profiles: Profile[];
  /** Beim Öffnen direkt diesen Eintrag zeigen. */
  initialId: number | null;
  onClose: () => void;
  onReuse: (text: string) => void;
  /** Nach Löschen oder Ändern: die Kurzliste in der App mitziehen. */
  onChanged: () => void;
}

const PAGE = 40;

const FIELD_TITLES: Record<string, string> = {
  main_prompt: "Hauptprompt",
  negative_prompt: "Negativprompt",
  motion_prompt: "Bewegung",
  audio_prompt: "Audio",
  dialogue: "Dialog",
  camera_notes: "Kamera / Framing",
};

const FIELD_ORDER = [
  "main_prompt",
  "negative_prompt",
  "motion_prompt",
  "audio_prompt",
  "dialogue",
  "camera_notes",
] as const;

const SOURCE_SHORT: Record<VideoSource, string> = {
  startframe: "Startframe",
  references: "Referenzen",
};

const FORMAT_LABELS: Record<ExportFormat, string> = {
  txt: "Text (.txt)",
  json: "Sicherung (.json)",
  csv: "Tabelle (.csv)",
};

export function LibraryPanel({ profiles, initialId, onClose, onReuse, onChanged }: Props) {
  const [items, setItems] = useState<LibraryListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [stats, setStats] = useState<LibraryStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [query, setQuery] = useState("");
  const [favorite, setFavorite] = useState(false);
  const [mode, setMode] = useState<ComposeMode | "">("");
  const [videoSource, setVideoSource] = useState<VideoSource | "">("");
  const [profileId, setProfileId] = useState("");
  const [tag, setTag] = useState("");
  const [offset, setOffset] = useState(0);

  const [selectedId, setSelectedId] = useState<number | null>(initialId);
  const [entry, setEntry] = useState<LibraryEntry | null>(null);
  const [entryError, setEntryError] = useState<string | null>(null);
  const [variant, setVariant] = useState<Variant>("precise");
  const [tagDraft, setTagDraft] = useState("");
  const [busy, setBusy] = useState(false);

  const [format, setFormat] = useState<ExportFormat>("txt");
  const [confirmClear, setConfirmClear] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);
  const [importNote, setImportNote] = useState<string | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const page = await loadLibrary({
        query,
        favorite: favorite || undefined,
        mode: mode || undefined,
        video_source: videoSource || undefined,
        profile_id: profileId || undefined,
        tag: tag || undefined,
        limit: PAGE,
        offset,
      });
      setItems(page.items);
      setTotal(page.total);
      setStats(await loadLibraryStats().catch(() => null));
    } catch (failure) {
      setError((failure as Error).message);
      setItems([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [query, favorite, mode, videoSource, profileId, tag, offset]);

  // Strg+K soll direkt losgetippt werden koennen.
  useEffect(() => {
    searchRef.current?.focus();
  }, []);

  // Die Suche laeuft getippt, aber nicht bei jedem Anschlag.
  useEffect(() => {
    const timer = window.setTimeout(() => void refresh(), 220);
    return () => window.clearTimeout(timer);
  }, [refresh]);

  useEffect(() => {
    if (selectedId === null) {
      setEntry(null);
      return;
    }
    let active = true;
    setEntryError(null);
    (async () => {
      try {
        const loaded = await loadLibraryEntry(selectedId);
        if (!active) return;
        setEntry(loaded);
        setTagDraft(loaded.tags.join(", "));
        setVariant(loaded.bundles[0]?.variant ?? "precise");
      } catch (failure) {
        if (!active) return;
        setEntry(null);
        setEntryError((failure as Error).message);
      }
    })();
    return () => {
      active = false;
    };
  }, [selectedId]);

  useEffect(() => {
    if (!flash) return;
    const timer = window.setTimeout(() => setFlash(null), 2200);
    return () => window.clearTimeout(timer);
  }, [flash]);

  async function toggleFavorite() {
    if (!entry) return;
    setBusy(true);
    try {
      setEntry(await updateLibraryEntry(entry.id, { favorite: !entry.favorite }));
      await refresh();
      onChanged();
    } catch (failure) {
      setEntryError((failure as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function saveTags() {
    if (!entry) return;
    setBusy(true);
    try {
      const updated = await updateLibraryEntry(entry.id, { tags: parseTags(tagDraft) });
      setEntry(updated);
      setTagDraft(updated.tags.join(", "));
      setFlash("Tags gespeichert.");
      await refresh();
      onChanged();
    } catch (failure) {
      setEntryError((failure as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function removeEntry() {
    if (!entry) return;
    setBusy(true);
    try {
      await deleteLibraryEntry(entry.id);
      setConfirmDelete(false);
      setSelectedId(null);
      await refresh();
      onChanged();
    } catch (failure) {
      setEntryError((failure as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function removeAll() {
    setBusy(true);
    try {
      const { deleted } = await clearLibrary();
      setConfirmClear(false);
      setSelectedId(null);
      setFlash(`${plural(deleted, "Eintrag", "Einträge")} gelöscht.`);
      await refresh();
      onChanged();
    } catch (failure) {
      setError((failure as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function runImport(file: File) {
    setBusy(true);
    setError(null);
    try {
      const result = await importLibrary(file);
      setFlash(
        result.imported > 0
          ? `${plural(result.imported, "Eintrag", "Einträge")} importiert.`
          : "Nichts Neues importiert.",
      );
      if (result.note) setImportNote(result.note);
      await refresh();
      onChanged();
    } catch (failure) {
      setError((failure as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function runExport(ids: number[]) {
    setBusy(true);
    try {
      await exportLibrary(ids, format);
    } catch (failure) {
      setError((failure as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const filtered = Boolean(query || favorite || mode || videoSource || profileId || tag);
  const active = entry?.bundles.find((bundle) => bundle.variant === variant) ?? null;

  return (
    <Overlay
      title="Bibliothek"
      label="Bibliothek"
      onClose={onClose}
      size="wide"
      head={
        stats && (
          <span className="block-meta">
            {plural(stats.count, "Eintrag", "Einträge")} ·{" "}
            {plural(stats.favorites, "Favorit", "Favoriten")}
          </span>
        )
      }
    >
      <div className="lib-filters">
        <input
          ref={searchRef}
          type="search"
          className="lib-search"
          placeholder="Volltextsuche über Prompts, Briefing und Tags"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setOffset(0);
          }}
        />
        <button
          className="btn btn-small"
          aria-pressed={favorite}
          onClick={() => {
            setFavorite((on) => !on);
            setOffset(0);
          }}
        >
          ★ Favoriten
        </button>
        <select
          value={mode}
          onChange={(event) => {
            const next = event.target.value as ComposeMode | "";
            setMode(next);
            if (next !== "video") setVideoSource("");
            setOffset(0);
          }}
          aria-label="Modus"
        >
          <option value="">alle Modi</option>
          <option value="improve">Verbessern</option>
          <option value="image">Bild</option>
          <option value="video">Video</option>
        </select>
        {(mode === "video" || videoSource) && (
          <select
            value={videoSource}
            onChange={(event) => {
              setVideoSource(event.target.value as VideoSource | "");
              setOffset(0);
            }}
            aria-label="Bildquelle"
          >
            <option value="">beide Quellen</option>
            <option value="startframe">Startframe</option>
            <option value="references">Referenzen</option>
          </select>
        )}
        <select
          value={profileId}
          onChange={(event) => {
            setProfileId(event.target.value);
            setOffset(0);
          }}
          aria-label="Zielprofil"
        >
          <option value="">alle Profile</option>
          {profiles.map((profile) => (
            <option key={profile.id} value={profile.id}>
              {profile.label}
            </option>
          ))}
        </select>
        {filtered && (
          <button
            className="link-btn"
            onClick={() => {
              setQuery("");
              setFavorite(false);
              setMode("");
              setVideoSource("");
              setProfileId("");
              setTag("");
              setOffset(0);
            }}
          >
            Filter zurücksetzen
          </button>
        )}
      </div>

      {stats && stats.tags.length > 0 && (
        <div className="lib-tags">
          {stats.tags.map((entryTag) => (
            <button
              key={entryTag}
              className={`chip${tag === entryTag ? " on" : ""}`}
              onClick={() => {
                setTag(tag === entryTag ? "" : entryTag);
                setOffset(0);
              }}
            >
              {entryTag}
            </button>
          ))}
        </div>
      )}

      {error && (
        <div className="error-box">
          <strong>Das hat nicht geklappt</strong>
          <p>{error}</p>
        </div>
      )}

      {importNote && (
        <p className="note-warn">
          {importNote}
          <button className="link-btn" onClick={() => setImportNote(null)} style={{ marginLeft: 10 }}>
            ausblenden
          </button>
        </p>
      )}

      <div className="lib-split">
        <div className="lib-list">
          {loading && items.length === 0 && <p className="hint">wird geladen …</p>}
          {!loading && !error && items.length === 0 && (
            <p className="empty">
              {filtered
                ? "Kein Eintrag passt auf diese Filter."
                : "Noch nichts gespeichert. Jeder fertige Lauf landet hier von selbst."}
            </p>
          )}

          <ul className="lib-strip-list">
            {items.map((item) => (
              <li key={item.id}>
                <button
                  className={`lib-row${item.id === selectedId ? " current" : ""}`}
                  onClick={() => setSelectedId(item.id)}
                >
                  <span className="lib-row-title">
                    {item.favorite && <span className="star">★</span>}
                    <span className="lib-row-name">{item.title}</span>
                  </span>
                  <span className="lib-row-meta">
                    {MODE_SHORT[item.mode]}
                    {item.mode === "video" && ` (${SOURCE_SHORT[item.video_source]})`} ·{" "}
                    {item.profile_id} · {relativeTime(item.created_at)}
                    {item.tags.length > 0 && ` · ${item.tags.join(", ")}`}
                  </span>
                </button>
              </li>
            ))}
          </ul>

          {total > PAGE && (
            <div className="lib-paging">
              <button
                className="btn btn-small"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - PAGE))}
              >
                zurück
              </button>
              <span className="block-meta">
                {offset + 1}–{Math.min(offset + PAGE, total)} von {total}
              </span>
              <button
                className="btn btn-small"
                disabled={offset + PAGE >= total}
                onClick={() => setOffset(offset + PAGE)}
              >
                weiter
              </button>
            </div>
          )}
        </div>

        <div className="lib-detail">
          {entryError && (
            <div className="error-box">
              <strong>Das hat nicht geklappt</strong>
              <p>{entryError}</p>
            </div>
          )}

          {!entry && !entryError && (
            <p className="empty">Links einen Eintrag wählen.</p>
          )}

          {entry && (
            <>
              <div className="lib-detail-head">
                <div>
                  <p className="lib-detail-title">{entry.title}</p>
                  <p className="hint">
                    {exactTime(entry.created_at)} · {entrySummary(entry)}
                  </p>
                </div>
                <button
                  className={`btn btn-small${entry.favorite ? " btn-primary" : ""}`}
                  onClick={toggleFavorite}
                  disabled={busy}
                >
                  {entry.favorite ? "★ Favorit" : "☆ Favorit"}
                </button>
              </div>

              {entry.thumbs.length > 0 && (
                <div className="lib-thumbs">
                  {entry.thumbs.map((thumb) => (
                    <img key={thumb.position} src={thumb.url} alt={`Referenz ${thumb.position + 1}`} />
                  ))}
                </div>
              )}

              {entry.briefing && (
                <div className="block">
                  <div className="block-head">
                    <span className="block-title">Briefing</span>
                  </div>
                  <div className="block-body">{entry.briefing}</div>
                </div>
              )}

              {entry.input_prompt && (
                <div className="block">
                  <div className="block-head">
                    <span className="block-title">Ausgangsprompt</span>
                  </div>
                  <div className="block-body">{entry.input_prompt}</div>
                </div>
              )}

              {entry.bundles.length > 0 && (
                <div className="tabs">
                  {entry.bundles.map((bundle) => (
                    <button
                      key={bundle.variant}
                      role="tab"
                      aria-selected={bundle.variant === variant}
                      onClick={() => setVariant(bundle.variant)}
                    >
                      {bundle.variant_label || bundle.variant}
                    </button>
                  ))}
                </div>
              )}

              {active &&
                FIELD_ORDER.filter((field) => active[field]).map((field) => (
                  <FieldBlock
                    key={field}
                    title={FIELD_TITLES[field]}
                    text={active[field] as string}
                    meta={field === "main_prompt" ? `${active.char_count} Zeichen` : undefined}
                  />
                ))}

              {active && active.warnings.length > 0 && (
                <div className="panel">
                  <span className="block-title">Warnungen</span>
                  <ul className="list warn">
                    {active.warnings.map((warning, index) => (
                      <li key={index}>{warning}</li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="field" style={{ marginTop: 14 }}>
                <label className="field-label" htmlFor="lib-tags">
                  Tags
                </label>
                <div className="lib-tag-row">
                  <input
                    id="lib-tags"
                    type="text"
                    value={tagDraft}
                    placeholder="durch Komma getrennt, z. B. nacht, kundenprojekt"
                    disabled={busy}
                    onChange={(event) => setTagDraft(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") void saveTags();
                    }}
                  />
                  <button
                    className="btn btn-small"
                    onClick={saveTags}
                    disabled={busy || tagDraft === entry.tags.join(", ")}
                  >
                    Speichern
                  </button>
                </div>
              </div>

              <div className="actions" style={{ marginTop: 12 }}>
                <button
                  className="btn btn-small"
                  disabled={!active}
                  onClick={() => {
                    if (!active) return;
                    onReuse(active.main_prompt);
                    onClose();
                  }}
                >
                  Als Ausgangsprompt übernehmen
                </button>
                <button
                  className="btn btn-small"
                  disabled={!active || busy}
                  onClick={() => active && void navigator.clipboard.writeText(bundleText(active))}
                >
                  Alles kopieren
                </button>
                <button
                  className="btn btn-small"
                  disabled={busy}
                  onClick={() => void runExport([entry.id])}
                >
                  Diesen exportieren
                </button>
                {confirmDelete ? (
                  <>
                    <button className="btn btn-small" onClick={() => setConfirmDelete(false)}>
                      zurück
                    </button>
                    <button
                      className="btn btn-small btn-danger"
                      onClick={removeEntry}
                      disabled={busy}
                    >
                      wirklich löschen
                    </button>
                  </>
                ) : (
                  <button
                    className="btn btn-small btn-danger"
                    onClick={() => setConfirmDelete(true)}
                    disabled={busy}
                  >
                    Löschen
                  </button>
                )}
              </div>
            </>
          )}
        </div>
      </div>

      <div className="settings-footer">
        <select
          value={format}
          onChange={(event) => setFormat(event.target.value as ExportFormat)}
          aria-label="Exportformat"
          style={{ width: "auto" }}
        >
          {(Object.keys(FORMAT_LABELS) as ExportFormat[]).map((value) => (
            <option key={value} value={value}>
              {FORMAT_LABELS[value]}
            </option>
          ))}
        </select>
        <button
          className="btn"
          disabled={busy || items.length === 0}
          onClick={() => void runExport(items.map((item) => item.id))}
        >
          {filtered ? "Gefilterte exportieren" : "Alle exportieren"} ({items.length})
        </button>
        <input
          ref={fileRef}
          type="file"
          accept="application/json,.json"
          hidden
          onChange={(event) => {
            const file = event.target.files?.[0];
            event.target.value = "";
            if (file) void runImport(file);
          }}
        />
        <button className="btn" disabled={busy} onClick={() => fileRef.current?.click()}>
          Importieren
        </button>

        <span className="block-meta">
          {flash ??
            (stats
              ? `${Math.max(1, Math.round(stats.bytes_on_disk / 1024))} kB auf der Platte`
              : "")}
        </span>

        {confirmClear ? (
          <>
            <span className="block-meta">Die ganze Bibliothek löschen?</span>
            <button className="btn btn-small" onClick={() => setConfirmClear(false)}>
              zurück
            </button>
            <button className="btn btn-small btn-danger" onClick={removeAll} disabled={busy}>
              wirklich alles löschen
            </button>
          </>
        ) : (
          <button
            className="btn btn-danger"
            onClick={() => setConfirmClear(true)}
            disabled={busy || total === 0}
          >
            Alles löschen
          </button>
        )}
      </div>
    </Overlay>
  );
}
