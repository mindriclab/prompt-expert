export type Density = "sparse" | "balanced" | "detailed";
export type Language = "de" | "en";
export type Variant = "precise" | "cinematic" | "experimental";
export type ComposeMode = "improve" | "image" | "video";
export type Intent = "reproduce" | "inspire";
export type VideoSource = "startframe" | "references";
export type Role = "subject" | "style" | "composition" | "wardrobe" | "environment";
export type AspectRatio =
  | "auto"
  | "1:1"
  | "4:5"
  | "5:4"
  | "2:3"
  | "3:2"
  | "3:4"
  | "4:3"
  | "9:16"
  | "16:9"
  | "21:9";
export type Grammar = "prose" | "tags";
export type ProfileKind = "image" | "video" | "edit";

export interface Profile {
  id: string;
  label: string;
  target: string;
  kind: ProfileKind;
  grammar: Grammar;
  language: Language;
  fields: string[];
  negative_prompt: { used: boolean; style: Grammar; base: string[] };
  length: { target_chars: number; max_chars: number };
  explicit_vocabulary: string;
  preferred_terms: string[];
  banned_phrases: string[];
  notes_for_model: string;
  ui_note: string;
  aspect_ratio_in_prompt: boolean;
  reference_slots: boolean;
  video_sources: VideoSource[];
}

export interface ProfileList {
  profiles: Profile[];
  invalid: { file: string; error: string }[];
}

export type ProviderKind = "ollama" | "openai_compat";

export interface ProviderSettings {
  kind: ProviderKind;
  base_url: string;
  api_key: string | null;
  connect_timeout_s: number;
  request_timeout_s: number;
}

export interface ModelSettings {
  text_model: string;
  vision_model: string;
  temperature: number;
  max_tokens: number;
  num_ctx: number;
  disable_thinking: boolean;
}

export interface ImageSettings {
  max_edge: number;
  jpeg_quality: number;
  max_images: number;
  max_upload_mb: number;
}

export interface DefaultsSettings {
  profile_id: string;
  language: Language;
  density: Density;
}

export interface LibrarySettings {
  enabled: boolean;
  store_thumbnails: boolean;
  max_entries: number;
}

/**
 * Spiegelt `app/models/settings.py` vollstaendig. Muss es auch: das Backend
 * verbietet unbekannte Felder und speichert immer das ganze Objekt - ein
 * verkuerzter Typ wuerde beim Speichern stillschweigend Felder loeschen.
 */
export interface AppSettings {
  schema_version: number;
  provider: ProviderSettings;
  models: ModelSettings;
  images: ImageSettings;
  defaults: DefaultsSettings;
  library: LibrarySettings;
}

export interface ModelInfo {
  name: string;
  size_bytes: number | null;
  parameter_size: string | null;
  quantization: string | null;
  families: string[];
  capabilities: string[];
  /** true/false nur wenn belegt, null heisst unbekannt. */
  supports_vision: boolean | null;
  modified_at: string | null;
}

export interface RunningModel {
  name: string;
  size_bytes: number | null;
  size_vram_bytes: number | null;
  expires_at: string | null;
}

export interface RunningModels {
  supported: boolean;
  models: RunningModel[];
  note: string | null;
}

export interface ProviderCheck {
  id: string;
  label: string;
  status: "ok" | "warn" | "fail" | "skipped";
  message: string;
}

export interface ProviderTestResult {
  ok: boolean;
  kind: string;
  base_url: string;
  latency_ms: number | null;
  server_version: string | null;
  text_model: string;
  vision_model: string;
  models: ModelInfo[];
  checks: ProviderCheck[];
}

/** Kompakter Zustand für die Statusleiste. Wird gepollt. */
export interface AppStatus {
  version: string;
  provider_kind: string;
  base_url: string;
  reachable: boolean;
  latency_ms: number | null;
  server_version: string | null;
  error_code: string | null;
  error_message: string | null;
  text_model: string;
  vision_model: string;
  loaded: RunningModel[];
  vram_bytes: number | null;
  text_model_loaded: boolean;
  library_enabled: boolean;
}

export interface StoredImage {
  id: string;
  original_name: string;
  width: number;
  height: number;
  bytes: number;
  thumb_url: string;
}

export interface Reference {
  id: string;
  role: Role;
}

/** Ein Referenzbild im UI-Zustand: Metadaten plus zugewiesene Rolle. */
export interface ReferenceItem extends StoredImage {
  role: Role;
}

export interface SubjectSpec {
  role: string;
  appearance: string;
  build: string;
  hair: string;
  face: string;
  wardrobe: string;
  pose: string;
  expression: string;
  explicit_detail: string;
  continuity_features: string[];
}

export interface SceneSpec {
  subjects: SubjectSpec[];
  scene: { setting: string; time_of_day: string; atmosphere: string; props: string[] };
  visual: {
    style: string;
    composition: string;
    lighting: string;
    palette: string[];
    materials: string[];
  };
  camera: { shot: string; lens: string; angle: string; focus: string; depth_of_field: string };
  uncertainties: string[];
  age_gate: { clearly_adult: boolean; reason: string };
}

export interface PromptCritique {
  summary: string;
  strengths: string[];
  weaknesses: string[];
  missing: string[];
}

export interface PromptBundle {
  variant: Variant;
  variant_label: string;
  profile_id: string;
  main_prompt: string;
  negative_prompt: string | null;
  motion_prompt: string | null;
  audio_prompt: string | null;
  dialogue: string | null;
  camera_notes: string | null;
  rationale: string[];
  warnings: string[];
  char_count: number;
  duration_ms: number | null;
}

export interface ComposeResponse {
  mode: ComposeMode;
  intent: Intent;
  profile_id: string;
  profile_label: string;
  language: Language;
  density: Density;
  model: string;
  vision_model: string | null;
  video_source: VideoSource;
  clip_seconds: number | null;
  shots: string[];
  aspect_ratio: AspectRatio;
  critique: PromptCritique | null;
  scene: SceneSpec | null;
  bundles: PromptBundle[];
  duration_ms: number;
  /** Kennung des Bibliothekseintrags. null heißt: nicht gespeichert. */
  library_id: number | null;
  library_error: string | null;
}

export type ExportFormat = "txt" | "json" | "csv";

export interface LibraryThumb {
  position: number;
  role: Role;
  url: string;
}

/** Schlanke Zeile für Liste und Suche — ohne die Prompttexte. */
export interface LibraryListItem {
  id: number;
  created_at: string;
  title: string;
  mode: ComposeMode;
  /** Nur bei `mode === "video"` aussagekräftig. */
  video_source: VideoSource;
  profile_id: string;
  profile_label: string;
  language: Language;
  density: Density;
  favorite: boolean;
  tags: string[];
  variant_count: number;
  char_count: number;
  duration_ms: number;
  thumbs: LibraryThumb[];
}

/** Ein vollständiger Lauf, so wie er gespeichert wurde. */
export interface LibraryEntry extends LibraryListItem {
  intent: Intent;
  aspect_ratio: AspectRatio;
  clip_seconds: number | null;
  model: string;
  vision_model: string | null;
  input_prompt: string;
  briefing: string;
  shots: string[];
  critique: PromptCritique | null;
  scene: SceneSpec | null;
  bundles: PromptBundle[];
}

export interface LibraryPage {
  items: LibraryListItem[];
  total: number;
  offset: number;
  limit: number;
}

export interface LibraryStats {
  count: number;
  favorites: number;
  tags: string[];
  bytes_on_disk: number;
}

export interface LibraryImportResult {
  imported: number;
  skipped: number;
  note: string | null;
}

export interface LibraryFilter {
  query?: string;
  favorite?: boolean;
  mode?: ComposeMode;
  video_source?: VideoSource;
  profile_id?: string;
  tag?: string;
  limit?: number;
  offset?: number;
}

export interface ComposeRequest {
  mode: ComposeMode;
  intent: Intent;
  video_source: VideoSource;
  clip_seconds: number | null;
  profile_id: string;
  density: Density;
  language: Language;
  aspect_ratio: AspectRatio;
  input_prompt: string;
  briefing: string;
  references: Reference[];
  variants: Variant[];
}

export interface ApiError {
  code: string;
  message: string;
  detail?: unknown;
}

export interface StageEvent {
  stage: "critique" | "analyse" | "compose";
  message: string;
  index: number;
  total: number;
  variant?: Variant;
}
