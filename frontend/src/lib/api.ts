import type {
  ApiError,
  AppSettings,
  AppStatus,
  ExportFormat,
  LibraryEntry,
  LibraryFilter,
  LibraryImportResult,
  LibraryPage,
  LibraryStats,
  ModelInfo,
  ModelSettings,
  ProviderSettings,
  RunningModels,
  ComposeRequest,
  ComposeResponse,
  ProfileList,
  PromptBundle,
  PromptCritique,
  ProviderTestResult,
  SceneSpec,
  StageEvent,
  StoredImage,
} from "../types/api";

export class ApiFailure extends Error {
  readonly code: string;
  /** Bei `validation_error` eine Liste aus `{field, reason}`. */
  readonly detail: unknown;
  constructor(error: ApiError) {
    super(error.message);
    this.code = error.code;
    this.detail = error.detail;
  }
}

/** Feldbezogene Validierungsfehler des Backends, z. B. `provider.base_url`. */
export function fieldErrors(failure: unknown): Record<string, string> {
  if (!(failure instanceof ApiFailure) || !Array.isArray(failure.detail)) return {};
  const map: Record<string, string> = {};
  for (const entry of failure.detail as { field?: string; reason?: string }[]) {
    if (entry.field) map[entry.field] = entry.reason ?? "ungültig";
  }
  return map;
}

/** Regelfall. Jeder Aufruf darf davon abweichen, keiner darf ohne auskommen. */
const DEFAULT_TIMEOUT_MS = 15_000;

/**
 * Übersetzt alles, was zwischen Browser und Backend schiefgehen kann, in einen
 * deutschen Satz. Ohne das steht bei abgestürztem Backend wörtlich
 * „Failed to fetch" in der Oberfläche.
 */
function asFailure(error: unknown, timeoutMs: number): ApiFailure {
  if (error instanceof ApiFailure) return error;
  const name = (error as Error)?.name;
  if (name === "TimeoutError") {
    return new ApiFailure({
      code: "provider_timeout",
      message:
        `Das Backend hat nach ${Math.round(timeoutMs / 1000)} s nicht geantwortet. ` +
        "Läuft der Modellserver noch, oder ist er mit einem anderen Lauf beschäftigt?",
    });
  }
  if (name === "AbortError") {
    return new ApiFailure({ code: "aborted", message: "Abgebrochen." });
  }
  return new ApiFailure({
    code: "backend_unreachable",
    message: "Das Backend ist nicht erreichbar. Läuft start.bat noch?",
  });
}

async function request(
  path: string,
  init: RequestInit,
  timeoutMs: number,
): Promise<Response> {
  try {
    return await fetch(path, { signal: AbortSignal.timeout(timeoutMs), ...init });
  } catch (error) {
    throw asFailure(error, timeoutMs);
  }
}

async function getJson<T>(
  path: string,
  init?: RequestInit,
  timeoutMs: number = DEFAULT_TIMEOUT_MS,
): Promise<T> {
  const response = await request(
    path,
    { headers: { "Content-Type": "application/json" }, ...init },
    timeoutMs,
  );
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const error = (body as { error?: ApiError } | null)?.error;
    throw new ApiFailure(
      error ?? { code: "internal_error", message: `Unerwarteter Fehler (HTTP ${response.status})` },
    );
  }
  return body as T;
}

export const loadProfiles = () => getJson<ProfileList>("/api/profiles");
export const loadSettings = () => getJson<AppSettings>("/api/settings");

/** Immer das vollstaendige Objekt - das Backend kennt kein Teil-Update. */
export const saveSettings = (settings: AppSettings) =>
  getJson<AppSettings>("/api/settings", { method: "PUT", body: JSON.stringify(settings) });

export const resetSettings = () =>
  getJson<AppSettings>("/api/settings/reset", { method: "POST" });

/** Ungespeicherte Werte mitschicken, damit die UI vor dem Speichern nachsehen kann. */
export interface ProviderOverride {
  provider?: ProviderSettings;
  models?: ModelSettings;
}

/** Modellliste und Fähigkeiten brauchen länger als ein Statusabruf. */
const PROBE_TIMEOUT_MS = 45_000;

export const testProvider = (override: ProviderOverride = {}) =>
  getJson<ProviderTestResult>(
    "/api/provider/test",
    { method: "POST", body: JSON.stringify({ ...override, probe: false }) },
    PROBE_TIMEOUT_MS,
  );

export const loadModels = (override: ProviderOverride = {}) =>
  getJson<ModelInfo[]>(
    "/api/provider/models",
    { method: "POST", body: JSON.stringify({ provider: override.provider ?? null }) },
    PROBE_TIMEOUT_MS,
  );

export const loadRunning = (override: ProviderOverride = {}) =>
  getJson<RunningModels>("/api/provider/running", {
    method: "POST",
    body: JSON.stringify({ provider: override.provider ?? null }),
  });

/** Für die Statusleiste. Kurzes Budget - sie wird gepollt. */
export const loadStatus = () =>
  getJson<AppStatus>("/api/provider/status", undefined, 10_000);

// -- Bibliothek -------------------------------------------------------------

function libraryQuery(filter: LibraryFilter): string {
  const params = new URLSearchParams();
  if (filter.query?.trim()) params.set("query", filter.query.trim());
  if (filter.favorite) params.set("favorite", "true");
  if (filter.mode) params.set("mode", filter.mode);
  if (filter.video_source) params.set("video_source", filter.video_source);
  if (filter.profile_id) params.set("profile_id", filter.profile_id);
  if (filter.tag) params.set("tag", filter.tag);
  if (filter.limit !== undefined) params.set("limit", String(filter.limit));
  if (filter.offset) params.set("offset", String(filter.offset));
  const query = params.toString();
  return query ? `?${query}` : "";
}

export const loadLibrary = (filter: LibraryFilter = {}) =>
  getJson<LibraryPage>(`/api/library${libraryQuery(filter)}`);

export const loadLibraryEntry = (id: number) => getJson<LibraryEntry>(`/api/library/${id}`);

export const loadLibraryStats = () => getJson<LibraryStats>("/api/library/stats");

export const updateLibraryEntry = (
  id: number,
  patch: { favorite?: boolean; tags?: string[] },
) =>
  getJson<LibraryEntry>(`/api/library/${id}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });

export const deleteLibraryEntry = (id: number) =>
  getJson<{ deleted: number }>(`/api/library/${id}`, { method: "DELETE" });

export const clearLibrary = () =>
  getJson<{ deleted: number }>("/api/library?confirm=true", { method: "DELETE" });

/** Eine JSON-Sicherung einlesen. Vorschaubilder sind darin nicht enthalten. */
export async function importLibrary(file: File): Promise<LibraryImportResult> {
  const form = new FormData();
  form.append("file", file);
  const response = await request("/api/library/import", { method: "POST", body: form }, 60_000);
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const error = (body as { error?: ApiError } | null)?.error;
    throw new ApiFailure(
      error ?? { code: "internal_error", message: "Der Import hat nicht geklappt." },
    );
  }
  return body as LibraryImportResult;
}

/**
 * Export als Download. Läuft über fetch statt über einen Link, damit ein
 * Fehler als Meldung ankommt und nicht als leere Datei.
 */
export async function exportLibrary(ids: number[], format: ExportFormat): Promise<void> {
  const response = await request(
    "/api/library/export",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids, format }),
    },
    60_000,
  );
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const error = (body as { error?: ApiError } | null)?.error;
    throw new ApiFailure(
      error ?? { code: "internal_error", message: "Der Export hat nicht geklappt." },
    );
  }
  const disposition = response.headers.get("content-disposition") ?? "";
  const match = /filename="([^"]+)"/.exec(disposition);
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = match?.[1] ?? `bibliothek.${format}`;
  anchor.click();
  URL.revokeObjectURL(url);
}

export async function uploadImage(file: File): Promise<StoredImage> {
  const form = new FormData();
  form.append("file", file);
  // Grosse Dateien plus Verkleinern - das darf laenger dauern als ein Statusabruf.
  const response = await request("/api/images", { method: "POST", body: form }, 120_000);
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const error = (body as { error?: ApiError } | null)?.error;
    throw new ApiFailure(
      error ?? { code: "image_rejected", message: "Das Bild konnte nicht gelesen werden." },
    );
  }
  return body as StoredImage;
}

export async function deleteImage(id: string): Promise<void> {
  await fetch(`/api/images/${id}`, { method: "DELETE" }).catch(() => undefined);
}

export interface ComposeHandlers {
  onStage: (stage: StageEvent) => void;
  onCritique: (critique: PromptCritique) => void;
  onScene: (scene: SceneSpec) => void;
  onBundle: (bundle: PromptBundle) => void;
  onResult: (result: ComposeResponse) => void;
  onError: (error: ApiError) => void;
}

/**
 * Startet die Komposition als Ereignisstrom. Der zurückgegebene AbortController
 * bricht sowohl die HTTP-Verbindung als auch den laufenden Modellaufruf ab.
 */
export async function composeStream(
  request: ComposeRequest,
  handlers: ComposeHandlers,
  signal: AbortSignal,
): Promise<void> {
  let response: Response;
  try {
    response = await fetch("/api/compose/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
      signal,
    });
  } catch (error) {
    if ((error as Error).name === "AbortError") return;
    handlers.onError({
      code: "provider_unreachable",
      message: "Das Backend ist nicht erreichbar. Läuft start.bat noch?",
    });
    return;
  }

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const error = (body as { error?: ApiError } | null)?.error;
    handlers.onError(
      error ?? { code: "internal_error", message: `Unerwarteter Fehler (HTTP ${response.status})` },
    );
    return;
  }

  const reader = response.body?.getReader();
  if (!reader) {
    handlers.onError({ code: "internal_error", message: "Der Ereignisstrom kam nicht an." });
    return;
  }

  const decoder = new TextDecoder();
  let buffer = "";

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let split = buffer.indexOf("\n\n");
      while (split !== -1) {
        dispatch(buffer.slice(0, split), handlers);
        buffer = buffer.slice(split + 2);
        split = buffer.indexOf("\n\n");
      }
    }
  } catch (error) {
    if ((error as Error).name !== "AbortError") {
      handlers.onError({
        code: "internal_error",
        message: "Die Verbindung zum Backend ist abgerissen.",
      });
    }
  }
}

function dispatch(block: string, handlers: ComposeHandlers): void {
  let name = "";
  let payload = "";
  for (const line of block.split("\n")) {
    if (line.startsWith("event: ")) name = line.slice(7).trim();
    else if (line.startsWith("data: ")) payload += line.slice(6);
  }
  if (!name || !payload) return;

  let data: unknown;
  try {
    data = JSON.parse(payload);
  } catch {
    return;
  }

  switch (name) {
    case "stage":
      handlers.onStage(data as StageEvent);
      break;
    case "critique":
      handlers.onCritique(data as PromptCritique);
      break;
    case "scene":
      handlers.onScene(data as SceneSpec);
      break;
    case "bundle":
      handlers.onBundle(data as PromptBundle);
      break;
    case "result":
      handlers.onResult(data as ComposeResponse);
      break;
    case "error":
      handlers.onError(data as ApiError);
      break;
  }
}

export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    // Die Zwischenablage-API verlangt Fokus und Erlaubnis. Der alte Weg über ein
    // verstecktes Feld greift auch dann noch - Kopieren ist hier der Hauptzweck.
    return legacyCopy(text);
  }
}

function legacyCopy(text: string): boolean {
  const field = document.createElement("textarea");
  field.value = text;
  field.setAttribute("readonly", "");
  field.style.position = "fixed";
  field.style.opacity = "0";
  document.body.appendChild(field);
  try {
    field.select();
    return document.execCommand("copy");
  } catch {
    return false;
  } finally {
    field.remove();
  }
}

export function downloadText(filename: string, text: string): void {
  const url = URL.createObjectURL(new Blob([text], { type: "text/plain;charset=utf-8" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
