# Setup

## Voraussetzungen
Auf diesem Rechner bereits vorhanden: Python 3.12.9, Node 22.20, Git, RTX 4090 (24 GB).
Fehlt noch: Ollama.

## 1. Ollama installieren
Download: https://ollama.com/download/windows — Installer ausführen, danach neues Terminal öffnen.

Prüfen:
```powershell
ollama --version
```

## 2. Modell ziehen
Ein Modell deckt Vision und Text ab:

```powershell
ollama pull orcarouter/Qwen3.8-27B-Uncensored:q4_K_M
```

16,5 GB Download. Tensor-level abliteriert, Vision-Tower unangetastet, Tools, 256K Kontext.

**Falls der Download bei ~98 % stehenbleibt:** Das passiert bei diesem Repository gelegentlich.
Fenster schließen bzw. `Strg+C`, denselben `ollama pull` erneut absetzen — der Teil-Download
bleibt erhalten und der Rest kommt beim zweiten Versuch durch.

Bei VRAM-Problemen (andere Anwendung belegt die GPU mit):
```powershell
ollama pull orcarouter/Qwen3.8-27B-Uncensored:iq4_xs
```
16 GB, spürbar mehr Luft für Kontext.

Alternativen, falls das Hauptmodell nicht überzeugt:
- `huihui_ai/gemma-4-abliterated:26b` — Vision und Audio, andere Schreibstimme
- `aha2025/llama-joycaption-beta-one-hf-llava` — spezialisierter unzensierter Bild-Captioner, kann nur beschreiben, nicht komponieren. Dann in der App unter *Einstellungen* als Vision-Modell wählen und ein Textmodell separat setzen.

Gezogene Modelle stehen in der App unter *Einstellungen* zur Auswahl, mit Größe,
Quantisierung und der Angabe, ob sie Bilder können. Ziehen selbst macht die App nicht —
dafür steht dort der passende `ollama pull`-Befehl zum Kopieren.

## 3. VRAM und Tempo — auf diesem Rechner gemessen
Ollama 0.34.2, RTX 4090, Modell `q4_K_M`:

| Wert | Messung |
|---|---|
| VRAM des Modells | 16,26 GB — vollständig auf der GPU, kein CPU-Offload |
| GPU-Auslastung gesamt | 19,4 GB von 24,5 GB (inkl. Desktop) |
| Kaltstart (erster Aufruf) | ~57 s |
| Warm | 49,6 Tokens/s, ~4 s für eine vollständige Antwort |
| Drei Varianten warm | ~20–25 s |

Umgebungsvariablen sind **nicht** nötig: Die App setzt `num_ctx`, `keep_alive: 30m` und
`think: false` bei jedem Aufruf selbst. `keep_alive` hält das Modell 30 Minuten geladen —
nur der allererste Aufruf nach einem Ollama-Neustart kostet die 57 s.

Wird der VRAM knapp, weil ComfyUI parallel läuft: `:iq4_xs` statt `:q4_K_M` ziehen.

## 4. Backend starten
```powershell
.\start.bat
```
Beim ersten Start wird `backend\.venv` angelegt und die Abhängigkeiten installiert. Danach läuft der Server auf http://127.0.0.1:8756 .

Manuell:
```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8756 --reload
```

## 5. Verbindung prüfen
```powershell
curl http://127.0.0.1:8756/api/health
curl -X POST http://127.0.0.1:8756/api/provider/test
```

Oder im Browser: http://127.0.0.1:8756/docs

## 6. Frontend

Das Backend liefert unter `/` das gebaute Frontend aus, sobald `frontend\dist` existiert.
Einmal bauen:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_frontend.ps1
```

Danach `start.bat` und http://127.0.0.1:8756 — fertig.

Zum Entwickeln mit Hot Reload stattdessen zwei Fenster:

```powershell
.\start.bat
powershell -ExecutionPolicy Bypass -File scripts\frontend.ps1
```

Vite läuft dann auf http://127.0.0.1:5173 und leitet `/api` an das Backend weiter.

## 7. Tests
```powershell
cd backend
.\.venv\Scripts\python -m pytest -q
```
Die Tests laufen ohne Ollama — alle Provider-Aufrufe sind gemockt.

## Wo liegen die Daten
`%APPDATA%\PromptExpert\`
- `settings.json` — Provider, Modelle, Standardprofil, Bildlimits
- `library.db` — Prompt-Bibliothek: ein Eintrag je Lauf, mit Tags und Favoriten
- `thumbs\` — Vorschaubilder der Referenzen, die zu Bibliothekseinträgen gehören
- `uploads\` — Referenzbilder der laufenden Sitzung, werden beim Start nach 24 Stunden
  aufgeräumt

Löschen dieses Ordners setzt die App vollständig zurück.
