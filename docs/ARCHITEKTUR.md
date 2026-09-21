# Architektur

## Leitidee
Zwei getrennte Modellaufgaben schlagen einen großen „Mach-mir-einen-Prompt"-Aufruf:

1. **Analyse** — beschreibend. Bild(er) + Briefing → streng validiertes `SceneSpec`-JSON.
2. **Komposition** — kreativ. `SceneSpec` + Absicht + Zielprofil → `PromptBundle`.

Fehler, Widersprüche und Prompt-Stil lassen sich dadurch getrennt kontrollieren. Die Komposition sieht das Rohbild nie, nur das SceneSpec — das hält sie schnell und macht Varianten ohne erneute Bildanalyse möglich.

## Datenfluss
```
Upload → Vorverarbeitung (Resize, EXIF weg) → Vision-Aufruf → SceneSpec
       → Composer (3x, je Variante) → PromptBundle → UI → Bibliothek
```
Varianten und Dichte-Änderungen laufen nur über Phase 2. Eine Bildanalyse pro Upload-Set genügt.

## Ein Modell statt zwei
Vision- und Textmodell getrennt zu halten kostet auf 24 GB entweder Modellwechsel-Latenz (20–40 s) oder VRAM. `orcarouter/Qwen3.8-27B-Uncensored` hat einen unangetasteten Vision-Tower und deckt beide Phasen ab. Die Architektur erlaubt trotzdem getrennte Modelle: Settings kennen `vision_model` und `text_model` separat, standardmäßig identisch belegt.

## Provider-Schicht
Genau **ein** Protokoll, genau **ein** produktiver Adapter:

```python
class ModelProvider(Protocol):
    async def health(self) -> ProviderHealth: ...
    async def list_models(self) -> list[ModelInfo]: ...
    async def complete(self, req: CompletionRequest) -> CompletionResult: ...
```

`OpenAICompatProvider` spricht `/v1/chat/completions` und deckt damit Ollama, LM Studio, llama.cpp-server, KoboldCpp und vLLM ab. `OllamaProvider` erbt davon und nutzt zusätzlich `/api/tags` (verlässliche Modellliste inkl. Familien/Fähigkeiten), `/api/show` (Fähigkeiten je Modell) und `/api/ps` (was gerade im VRAM liegt).

`ModelInfo.supports_vision` ist dreiwertig: `true`/`false` nur, wenn `/api/show` es belegt
oder der Name eindeutig ist, sonst `null` für *unbekannt*. Die UI darf `null` nicht als
`false` behandeln — ein Namensraten ist keine Tatsache.

Die Routen `/provider/models` und `/provider/running` gibt es je als `GET` (gespeicherte
Settings) und als `POST` mit optionalem Provider-Override, damit die Settings-Ansicht einen
Server prüfen kann, der noch nicht gespeichert ist. `/provider/running` antwortet auch ohne
Ollama mit 200 und `supported: false` — fehlender VRAM-Status ist Abwesenheit, kein Fehler.

Bilder gehen als `image_url` mit `data:`-URI in die Message — der OpenAI-Vision-Standard, den alle genannten Server sprechen.

Strukturierte Ausgabe über `response_format = {"type": "json_schema", ...}`. Kann ein Server das nicht, fällt der Adapter auf `json_object` und danach auf reines Prompting zurück; die Pydantic-Validierung bleibt in jedem Fall die Wahrheit.

## Verträge
### SceneSpec (Auszug)
```json
{
  "subjects": [{
    "role": "subject",
    "appearance": "", "build": "", "hair": "", "face": "",
    "wardrobe": "", "pose": "", "expression": "",
    "explicit_detail": "",
    "continuity_features": []
  }],
  "scene": {"setting": "", "time_of_day": "", "atmosphere": "", "props": []},
  "visual": {"style": "", "composition": "", "lighting": "", "palette": [], "materials": []},
  "camera": {"shot": "", "lens": "", "angle": "", "focus": "", "depth_of_field": ""},
  "motion": {"subject_motion": "", "camera_motion": "", "beats": [], "physics_notes": ""},
  "audio": {"ambience": "", "foley": [], "dialogue": []},
  "uncertainties": [],
  "age_gate": {"clearly_adult": true, "reason": ""}
}
```

### PromptBundle (Auszug)
```json
{
  "variant": "precise",
  "profile_id": "ltx23_i2v",
  "main_prompt": "",
  "negative_prompt": null,
  "motion_prompt": null,
  "audio_prompt": null,
  "dialogue": null,
  "camera_notes": null,
  "rationale": [],
  "warnings": []
}
```

## Härtung
Jeder Weg zum Modellserver hat eine Obergrenze, und zwar auf beiden Seiten. Im Backend
setzt `_timeout()` Connect, Read, Write und Pool aus den Settings; Sammelabfragen bekommen
zusätzlich ein Gesamtbudget (`enrich_capabilities`: 20 s, Statusabruf: 8 s je Anfrage).
Im Frontend trägt jeder `fetch` ein `AbortSignal.timeout` — 15 s im Regelfall, mehr für
Modellliste, Export und Upload. Abbruch läuft über den `AbortController` des
Kompositionsstroms; der Serverpfad bricht den laufenden Modellaufruf mit ab.

Blockierende Arbeit gehört nicht in den Event-Loop: der Bild-Upload (Pillow) und das
Ablegen in der Bibliothek (`sqlite3`) laufen über `asyncio.to_thread`, die Bibliotheksrouten
sind synchron deklariert und landen damit in Starlettes Threadpool.

`GET /api/provider/status` speist die Statusleiste: Erreichbarkeit plus VRAM-Stand, ohne
Modellliste und ohne Fähigkeitsabfrage. Sie antwortet **immer** mit 200 — ein schweigender
Modellserver ist ein Zustand, den die Leiste anzeigen soll, kein Fehler, der sie leer lässt.
Das Zugriffslog blendet genau diesen Pfad aus, sonst steht er im Sekundentakt in der Konsole.

## Bibliothek
SQLite über die stdlib, eine Datei im Datenverzeichnis (`library.db`), WAL-Journal,
kurzlebige Verbindungen je Aufruf. Die Bibliotheksrouten sind bewusst synchron (`def`) —
FastAPI schiebt sie in den Threadpool, und `sqlite3` blockiert.

**Ein Eintrag ist ein Lauf.** Prompttexte und alles Filterbare stehen in eigenen Spalten,
alles Strukturierte (Varianten, Analyse, SceneSpec) als JSON in `payload`. Das hält die
Suche einfach und das Schema stabil, auch wenn die Pipeline später weitere Felder liefert.

**Keine FTS5.** `search_text` ist eine vorberechnete, kleingeschriebene Spalte aus Briefing,
Ausgangsprompt, allen Varianten und dem Profilnamen; gesucht wird mit `LIKE`. Bei einigen
tausend Einträgen ist das sofort fertig und bindet die App nicht daran, ob das SQLite der
jeweiligen Python-Installation FTS5 mitbringt. Tags liegen in einer eigenen Tabelle und
werden mit derselben Anfrage über ein `IN (SELECT …)` mitgesucht — so muss beim Ändern eines
Tags nichts neu berechnet werden.

Das Speichern hängt in `app/api/compose.py`, nicht im Composer: der Dienst bleibt rein, und
beide Routen (JSON und SSE) gehen durch dieselbe Stelle. Ein Fehler dort wird am Ergebnis
vermerkt (`library_error`), nie geworfen — ein Lauf, auf den der Nutzer eine Minute gewartet
hat, darf nicht an der Datenbank scheitern.

## Fehlerformat
Jeder Fehler verlässt das Backend als:
```json
{"error": {"code": "provider_unreachable", "message": "<deutsch, handlungsleitend>", "detail": null}}
```
Codes: `provider_unreachable`, `provider_timeout`, `provider_error`, `model_not_found`, `model_no_vision`, `invalid_model_output`, `validation_error`, `age_gate`, `profile_not_found`, `image_rejected`, `not_found`, `internal_error`. HTTP-Status passend (502/504/404/422/400/500).

Bei `validation_error` steht in `detail` je Feld ein Eintrag `{field, reason}` — `reason` ist
deutsch, auch wenn er aus Pydantic stammt. Die Settings-Ansicht schreibt ihn direkt ans Feld.

## Bewusst nicht enthalten
Kein LangChain/LangGraph, keine Vektordatenbank, kein Nutzerkonto, kein Docker-Zwang, kein Electron, kein PyInstaller, keine ComfyUI- oder Wavespeed-Anbindung. Single-User-Creator-Tool, kein SaaS.

## Sicherheit im lokalen Kontext
- Server bindet auf `127.0.0.1`, nicht `0.0.0.0`.
- Uploads: Whitelist (JPEG/PNG/WebP), Größenlimit, Pillow-Re-Encode (entfernt EXIF und exotische Container), längste Kante nach Settings.
- Nutzertext, Dateinamen und Bildinhalte werden im Prompt als Datenblock zwischen Markern übergeben, mit expliziter Anweisung, darin enthaltene Instruktionen nicht auszuführen.
- Logs enthalten nie Bilddaten und nie vollständige Nutzerprompts auf INFO-Level.
