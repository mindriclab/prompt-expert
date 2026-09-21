# Meilensteine

## M1 — Backend-Scaffold, Settings, Provider-Test  ✅ umgesetzt
**Inhalt:** FastAPI-App auf `127.0.0.1:8756`, Settings-Persistenz, Provider-Abstraktion mit OpenAI-kompatiblem Adapter und Ollama-Erweiterung, Verbindungs-/Modelltest, Profil-Loader, einheitliches Fehlerformat, Tests.

**Akzeptanzkriterien**
- `start.bat` legt venv an, installiert, startet; `GET /api/health` liefert 200 mit Version, Datenverzeichnis, Profilanzahl.
- `GET /api/settings` liefert Defaults; `PUT /api/settings` validiert und persistiert nach `%APPDATA%\PromptExpert\settings.json`; ungültige Werte → 422 im Fehlerformat.
- `POST /api/provider/test` unterscheidet nachweislich: Server nicht erreichbar, Timeout, Modell nicht installiert, Modell ohne Vision, alles in Ordnung — jeweils mit deutschem, handlungsleitendem Text.
- `GET /api/provider/models` listet installierte Modelle mit Vision-Fähigkeit und Größe.
- `GET /api/profiles` listet 6 gültige Profile; ein defektes Profil taucht mit Fehlergrund auf, statt zu verschwinden.
- `pytest` läuft grün ohne laufendes Ollama.

**Verifiziert am 20.09.2026** gegen Ollama 0.34.2 mit `orcarouter/Qwen3.8-27B-Uncensored:q4_K_M`:
46 Tests grün, ruff sauber, alle sechs Prüfungen des Verbindungstests grün inkl. echter
Generierung, Vision-Fähigkeit vom Server bestätigt, keine Verweigerung bei explizitem Material.

## M2 — Modus „Prompt verbessern" (vertikaler Durchstich)  ✅ umgesetzt
Backend: `POST /api/compose` (blockierend) und `POST /api/compose/stream` (SSE), Analyse-Phase plus eine Komposition je Variante, JSON-Schema-Zwang mit einem Reparaturversuch, Profil-Durchsetzung nach dem Modellaufruf, Abbruch bei Verbindungsabriss.
Frontend: Vite + React + TypeScript, Dark UI, drei Spalten, Ergebnis-Tabs, Copy je Feld, Verbindungsstatus, Statusstufen, Abbrechen.

**Akzeptanzkriterien**
- Ein realer Prompt geht in drei nachvollziehbar unterschiedliche Versionen plus Schwächenanalyse über.
- Die Varianten unterscheiden sich belegbar: eigener Auftrag im Prompt und gestaffelte Temperatur (präzise < cinematic < experimentell).
- Die Dichte verändert das Längenziel sichtbar (knapp ×0.55, ausgewogen ×1.0, detailliert ×1.6, gedeckelt durch `max_chars`).
- Profilregeln werden nach dem Modellaufruf durchgesetzt, nicht nur erbeten: Füllphrasen raus, Negativprompt-Grundbegriffe ergänzt, Tag-Grammatik normalisiert, Längenmaximum erzwungen — jeweils mit Warnung.
- Nutzertext steht zwischen Markern und wird als Daten deklariert; eingeschmuggelte Marker werden entfernt.
- Abbruch beendet den laufenden Modellaufruf serverseitig.

**Verifiziert am 20.09.2026**: 92 Tests grün, ruff sauber, Frontend baut fehlerfrei.
Echter Durchlauf gegen `orcarouter/Qwen3.8-27B-Uncensored:q4_K_M`: 43 s für Analyse plus drei
Varianten, 7–12 s je Variante. Abbruch im Browser erzeugt serverseitig
`Komposition vom Client abgebrochen`.

## M3 — Bild → Prompt  ✅ umgesetzt
Upload (1–6, Drag & Drop, Rollen, Neuordnen, Entfernen), Pillow-Vorverarbeitung, Vision-Analyse
zu `SceneSpec` mit JSON-Schema, Age-Gate, SceneSpec-Anzeige in der UI, Komposition aus dem
SceneSpec ohne erneuten Bildaufruf.

**Zwei Absichten**, umschaltbar in der UI:
- **Nachbauen** — das vorhandene Bild so genau wie möglich als Prompt beschreiben. Die drei
  Varianten heißen hier `Detailliert` / `Kompakt` / `Anders formuliert`, weil eine kreative
  Abweichung beim Nachbauen ein Fehler wäre.
- **Als Vorlage** — Look, Stimmung und Merkmale übernehmen, die Szene kommt aus dem Briefing.
  Varianten bleiben `Präzise` / `Cinematic` / `Experimentell`.

**Akzeptanzkriterien**
- Bis zu sechs Referenzen mit Rollen (`subject`, `style`, `composition`, `wardrobe`,
  `environment`) gehen in genau einen Vision-Aufruf; die Rollenzuordnung steht in der
  Reihenfolge der Bilder im Prompt.
- Varianten entstehen aus demselben SceneSpec — eine Bildanalyse je Durchlauf, nicht vier.
- Vorverarbeitung erzwingt Format-Whitelist, Größenlimit und längste Kante aus den Settings
  und entfernt EXIF durch Neukodierung.
- Age-Gate bricht vor jeder Komposition ab, wenn eine Referenz nicht eindeutig erwachsen wirkt.
- Bild-Kennungen sind Zufallshex, Pfadtraversal ist blockiert.
- Ohne Referenzbild wird der Bildmodus zum reinen Text-zu-Bildprompt.

**Verifiziert am 20.09.2026**: 131 Tests grün, ruff sauber, Frontend baut fehlerfrei.
Echter Durchlauf mit eigenem Foto (7,4 MB PNG, verarbeitet zu 1024×1280 und 162 kB):
Analyse plus drei Varianten in 36–77 s, EXIF entfernt, Age-Gate passiert, unklare Tageszeit
als Warnung statt als erfundene Tatsache.

## Zwischenrunde — aus der Auswertung der eigenen Prompt-Sammlung  ✅ umgesetzt
Auslöser: schwankende Ergebnisse bei Seedream auf Wavespeed. Die Auswertung der eigenen
Prompt-Sammlung und der vorhandenen ComfyUI-Workflows zeigte drei Lücken in der App:

- **Seitenverhältnis** kam im Prompt überhaupt nicht vor, obwohl die eigenen funktionierenden
  Prompts es konsequent nennen. Jetzt eigene Auswahl, im Bildmodus aus der ersten Referenz
  vorbelegt, und je nach Profil entweder im Prompt erzwungen oder ausdrücklich dem Workflow
  überlassen.
- **Referenz-Zuordnung** `(Image 1)`, `(Image 2)` fehlte im fertigen Prompt. Ohne sie weiß
  ein Multi-Referenz-Zielsystem nicht, was woher kommt — der wahrscheinlichste Grund für
  Ausreißer. Jetzt Pflicht bei `reference_slots`-Profilen, inklusive der Formulierung
  „using the style of (Image 3) exclusively" gegen Identitätsvermischung.
- **`ltx23_i2v` hatte keinen Negativprompt.** Das funktionierende Referenz-Setup nutzt
  einen langen, der vor allem ungewollte Tonspuren unterdrückt (`music`, `podcast`,
  `newscast`, `non-english`). Übernommen.

Zusätzlich: `seedream_image` an den echten Prompts kalibriert (Längenziel von 620 auf 420
Zeichen, kurze deklarative Sätze, explizite Anatomie direkt benannt, Shot-Size am Ende),
und die bewährten Formulierungen gegen Maßstabsdrift in `wan22_i2v`, `flux_image` und
`gpt_image` übernommen.

**Entschieden:** LTX 2.3 fährt mit Zeitmarken. Die Begleitnotiz des Workflows verbietet
sie, der funktionierende Referenzprompt benutzt `[0-4 sec]`. Maßgeblich ist, was in der
Praxis läuft. `ltx23_i2v` bildet jetzt genau
diese Struktur ab: ungetimtes Ausgangsbild, danach Zeitfenster bis `[11+ sec]`, Ton und
Dialog im jeweiligen Fenster.

**Verifiziert am 20.09.2026**: 149 Tests grün. Echter Durchlauf mit zwei Referenzen auf
`seedream_image`: beide Marker gesetzt, Stilreferenz mit „exclusively", 4:5 im Prompt.

## M4 — Bild → Video  ✅ umgesetzt
Dritter Modus `video` mit zwei Bildquellen statt der Bild-Absicht:

- **Startframe** (Standardfall, z. B. MiniMax H3 I2V) — das Bild ist der erste Frame. Der
  Prompt beschreibt **nur die Handlung**. Varianten `Detailliert` / `Kompakt` /
  `Anders formuliert` unterscheiden sich in der Menge an Bewegungsdetail, nie an Aussehen.
- **Referenzen** (z. B. MiniMax 3Img, LTX LikenessGuide) — kein Startframe. Die Bilder
  liefern Identität, die Szene wird gebaut. Varianten wie sonst, plus `(Image N)`-Marker.

**Akzeptanzkriterien**
- Im Startframe-Modus enthält `main_prompt` keine Bildbeschreibung. Das Verbot steht im
  Prompt-Kopf **und** in der Schlussanweisung, weil Modelle das Ende stärker gewichten.
- `camera_notes` führt im Startframe-Modus nur den Kameraweg, nicht die Einstellungsgröße.
- Subjekte werden minimal verankert: bei einer Person gar nicht, bei mehreren mit zwei bis
  drei Wörtern.
- Ein Startframe ist genau ein Bild; mehrere werden mit klarer Meldung abgelehnt.
- Die Profilauswahl zeigt nur Ziele, die die gewählte Quelle können.
- Die Referenz-Zuordnung greift **nur** im Referenz-Modus — kein `(Image 1)` im
  Startframe-Prompt.
- Die Vision-Phase fordert im Startframe-Modus kurze Anker und Bewegungshinweise an, im
  Referenz-Modus eine vollständige Beschreibung.
- Widersprüche werden deterministisch geprüft und gemeldet, nicht still korrigiert:
  Zeitachse, gegenläufige Kamera, Stillstand plus Fortbewegung — jeweils je Abschnitt
  (Zeitfenster oder Shot), damit legitime Abfolgen keine Fehlalarme auslösen.
- Bildprofile werden nicht auf Bewegung geprüft.
- Videoprofile liefern **einen** Block: Bewegung, Kameraweg, Ton und Dialog stehen in
  `main_prompt`, nicht in Einzelfeldern. Nur der Negativprompt bleibt getrennt.
- Die Cliplänge ist eine optionale Nutzereinstellung und steht nie im Prompttext.
- Eine Shot-Gliederung im Briefing bleibt in Struktur, Reihenfolge und Beschriftung
  erhalten; fehlende Shots im Ergebnis erzeugen eine Warnung.

**Verifiziert am 20.09.2026**: 197 Tests grün, ruff sauber, Frontend baut fehlerfrei.
Echte Durchläufe mit eigenem Bildmaterial:
`minimax_video` / Startframe → 371 Zeichen reine Handlung, Kamera nur als Weg, keine
Slot-Reste, und das Modell hält die 6 Sekunden von selbst ein.
`ltx23_i2v` / Referenzen → volle Szene mit `(Image 1)`, `(Image 2) exclusively`,
lückenlosen Zeitmarken `[0-4]`–`[11+]` und Soundscape.

**Zwei Korrekturen nach Tests mit echtem Material:**
1. Der Videomodus hatte zuerst die Bild-Absicht (*Nachbauen* / *Als Vorlage*) übernommen.
   Falsche Achse — *Nachbauen* erzeugte eine Bildbeschreibung, obwohl das Modell den Frame
   schon hat. Ersetzt durch *Startframe* / *Referenzen*.
2. Die Ausgabe war in Hauptprompt, Bewegung und Kamera zerlegt, teils redundant, und die
   Cliplänge stand als Satz im Prompt. Beides falsch: der Generator hat ein Prompt-Feld,
   und die Länge stellt der Nutzer dort selbst ein.

## M5 — Modellauswahl in der App  ✅ umgesetzt
Settings-Ansicht als Overlay über der App (Knopf *Einstellungen* in der Topbar, `Esc`
schließt). Kein
Router, keine neue Abhängigkeit — der Arbeitsstand in den drei Spalten bleibt beim Öffnen
unangetastet.

**Inhalt**
- Modellserver: Provider, Base URL, API-Key (verdeckt, mit Aufdecken), „Verbindung testen"
  mit den Einzelprüfungen aus `POST /api/provider/test`.
- Modellauswahl als Dropdown mit Größe, Parameterzahl, Quantisierung und Bildfähigkeit.
  Modelle ohne Vision sind im Vision-Feld ausgegraut, nicht versteckt. Ein „eintippen"-Schalter
  bleibt als Ausweg für Namen, die der Server noch nicht kennt.
- Nicht installierte Modelle bleiben in der Liste, sind als *nicht installiert* markiert und
  bringen den `ollama pull`-Befehl zum Kopieren mit.
- Referenzbild-Limits, Standards (Profil, Sprache, Dichte) und ein aufklappbarer Block mit
  Temperatur, `num_ctx`, `max_tokens` und den beiden Timeouts.
- Anzeige, welches Modell gerade im VRAM liegt, samt Belegung.

**Drei Entscheidungen**
1. **Kein Modell-Pull aus der App.** `/api/pull` hätte einen eigenen Streaming-Pfad in der
   Provider-Schicht gebraucht — `_request()` schließt den Client, bevor es die Antwort
   zurückgibt. Dazu kommt der in `SETUP.md` dokumentierte Hänger bei ~98 %, der sich in
   einem eingebetteten Fortschrittsbalken schlecht erklären lässt. Es bleibt beim
   Kopierbefehl.
2. **Der `library`-Block steht nicht in der Ansicht.** Bis M6 liegt nichts dahinter, und ein
   Schalter ohne Wirkung ist eine Attrappe.
3. **Standards greifen beim nächsten Start.** Was in der linken Spalte eingestellt ist, hat
   der Nutzer für diesen Durchlauf bewusst gewählt und wird vom Speichern nicht überschrieben.
   Der Verbindungsstatus dagegen wird sofort neu geprüft.

**Vier Dinge mussten dafür geradegezogen werden**
- **Der Frontend-Typ `AppSettings` war verkürzt** — er kannte `images`, `library`, `api_key`,
  `temperature`, `num_ctx` und die Timeouts gar nicht. Das Backend verbietet unbekannte Felder
  und speichert immer das ganze Objekt: das erste Speichern aus der Ansicht hätte diese Felder
  stillschweigend auf Defaults zurückgesetzt. Der Typ spiegelt jetzt `settings.py` 1:1.
- **`enrich_capabilities` war bei 12 Modellen gedeckelt.** Alles darüber hinaus hätte nur auf
  Namensraten beruht — genau die Grundlage, auf der die Ansicht ausgraut. Limit jetzt 60 mit
  begrenzter Nebenläufigkeit, und ausgegraut wird ausschließlich bei belegtem `false`.
  `null` heißt *unbekannt* und wird auch so benannt.
- **`GET /api/provider/running` war untypisiert** (`list[dict]`) und warf 400, wenn der Provider
  kein Ollama ist. Fehlender VRAM-Status ist aber Abwesenheit, kein Fehler. Jetzt
  `{supported, models[], note}` mit 200 in beiden Fällen.
- **Validierungsfehler kamen roh auf Englisch** („Input should be greater than or equal to
  384"). Vor M5 hat sie nie jemand gesehen; am Feld in einer deutschen Oberfläche geht das
  nicht. `errors.py` übersetzt die gängigen Pydantic-Arten, eigene Validatoren behalten ihren
  Text ohne das vorangestellte `Value error, `.

**Akzeptanzkriterien**
- Modellwechsel ohne Textfeld und ohne Neustart.
- Die Auswahl macht erkennbar, welches Modell für die Bildanalyse taugt — und wo sie es
  nicht weiß.
- `POST /api/provider/models` und `POST /api/provider/running` nehmen einen Provider-Override
  entgegen, damit die Ansicht nachsehen kann, bevor gespeichert wird.
- Labels sind mit ihren Feldern verknüpft; jedes Feld hat einen zugänglichen Namen.

**Verifiziert am 20.09.2026**: 206 Tests grün, ruff sauber, Frontend baut fehlerfrei.
Echter Durchlauf gegen Ollama 0.34.2: Modellliste mit belegter Fähigkeit
(`capabilities: completion, vision, tools, thinking`), VRAM-Anzeige 17,5 GB.
Textmodell in der Ansicht auf ein nicht installiertes `llama3.1:8b` gestellt und gespeichert
→ Statusanzeige links springt ohne Neustart auf „nicht einsatzbereit", der nächste Lauf
bricht mit `model_not_found` ab. Über das Dropdown zurückgestellt → voller Lauf mit drei
Varianten in 92 s. Speichern und Wiederlesen lässt `library` und alle Modellparameter
unangetastet; `max_edge: 100` wird mit „Mindestens 384." am Feld abgelehnt.

## M6 — Bibliothek  ✅ umgesetzt
SQLite im Datenverzeichnis (`library.db`), automatisches Speichern, Volltextsuche, Tags,
Favoriten, Referenz-Thumbnails, „als Ausgangsprompt übernehmen", Export als `.txt` / `.json`
/ `.csv`, Einzel- und Komplettlöschung.

**Drei Entscheidungen**
1. **Automatisch speichern, abschaltbar.** Jeder abgeschlossene Lauf landet von selbst in der
   Bibliothek — ob ein Prompt etwas taugt, zeigt sich meist erst im Generator, also nach dem
   Schließen der App. Wer das nicht will, schaltet es in den Einstellungen ab; vorhandene
   Einträge bleiben durchsuchbar.
2. **Ein Eintrag ist ein Lauf, keine Variante.** Briefing, Referenzen, Analyse und alle drei
   Varianten gehören zusammen. Die Suche findet den Lauf, die Variante wählt man darin. Bei
   automatischem Speichern hält das die Liste auf einem Drittel der Länge.
3. **Kurzliste rechts, Vollansicht als Overlay.** Unter dem Ergebnis stehen die letzten fünf
   Läufe, ein Knopf führt in die Vollansicht mit Suche, Filtern, Tags, Sammelexport und
   Löschen — dasselbe Muster wie die Einstellungen.

**Ohne FTS5.** Bei einigen tausend Einträgen auf einem lokalen Rechner ist `LIKE` sofort
fertig. FTS5 hätte Trigger, eine zweite Tabelle und eine Abhängigkeit davon gebracht, mit
welchen Optionen das SQLite der jeweiligen Python-Installation gebaut wurde. Durchsucht wird
eine vorberechnete Spalte aus Briefing, Ausgangsprompt, allen Varianten und Profilnamen,
Tags über ihre eigene Tabelle.

**Thumbnails werden kopiert, nicht verwiesen.** Die Uploads räumt der Start nach 24 Stunden
weg; ein Bibliothekseintrag soll das überleben. Die Kopien liegen in `thumbs\` und
verschwinden mit ihrem Eintrag.

**Akzeptanzkriterien**
- Ein drei Wochen alter Prompt lässt sich über Volltextsuche finden, wiederverwenden und
  als Paket exportieren.
- Ein Fehler beim Speichern wirft kein Ergebnis weg, auf das der Nutzer eine Minute
  gewartet hat — er steht als Hinweis am Ergebnis (`library_error`).
- Die Obergrenze räumt die ältesten Einträge weg, **nie** Favoriten.
- Das Leeren der ganzen Bibliothek verlangt eine ausdrückliche Bestätigung.
- Tags werden normalisiert: klein, getrimmt, ohne Dubletten, höchstens zwölf.

**Nachgetragen am 21.09.2026**: Import einer `.json`-Sicherung (`POST /api/library/import`)
mit Dublettenschutz über Zeitpunkt, Modus, Profil und Kurzzeile — Vorschaubilder stecken
nicht in einer Sicherung und fehlen danach entsprechend. Dazu ein Filter nach Bildquelle
(Startframe / Referenzen) im Videomodus; `video_source` steht jetzt auch in der Listenzeile.

**Verifiziert am 21.09.2026**: 242 Tests grün (26 davon für die Bibliothek), ruff sauber,
Frontend baut fehlerfrei. Echte Läufe gegen `orcarouter/Qwen3.8-27B-Uncensored:q4_K_M`:
vier Läufe automatisch abgelegt, Volltextsuche nach `convertible` findet genau einen,
Tag-Filter und Favoriten-Filter greifen, alle drei Exportformate liefern Dateien mit
korrektem `Content-Disposition`, CSV mit einer Zeile je Variante. „Als Ausgangsprompt
übernehmen" schaltet in den Verbessern-Modus und füllt das Feld, Löschen mit Bestätigung
entfernt Eintrag und Vorschaubild.

## M7 — Härtung  ✅ umgesetzt
Timeouts und Abbruch auf allen Pfaden, deutsche Fehlerpfade im Frontend, Statusleiste mit
geladenem Modell und VRAM, Tastaturkürzel, README-Durchlauf von Null auf lauffähig.

**Vier Lücken, die der Audit gefunden hat**
1. **Kein `fetch` außer dem Kompositionsstrom hatte Timeout oder Abbruch.** Hing das Backend,
   drehte sich „prüft …" endlos. Jeder Aufruf hat jetzt ein Budget: 15 s im Regelfall, 45 s
   für Modellliste und Verbindungstest, 60 s für den Export, 120 s für einen Upload.
2. **Netzwerkfehler kamen roh durch.** `getJson` warf bei abgestürztem Backend einen
   `TypeError`; in der Oberfläche stand dann wörtlich „Failed to fetch". Alles, was zwischen
   Browser und Backend schiefgehen kann, wird jetzt in einen deutschen Satz übersetzt.
3. **Der Bild-Upload blockierte den Event-Loop.** `upload_image` war `async def`, die
   Pillow-Arbeit lief synchron darin — während ein großes Bild verkleinert wurde, stand der
   ganze Server, auch ein laufender SSE-Strom. Jetzt über `asyncio.to_thread`.
4. **`enrich_capabilities` war unbegrenzt.** 60 Modelle × 20 s Lesetimeout bei 6 parallel —
   im schlechtesten Fall über drei Minuten. Jetzt 20 s Gesamtbudget; was bis dahin nicht
   beantwortet ist, bleibt „unbekannt".

**Statusleiste.** Die Fußzeile zeigt dauerhaft Punkt, Modellname, belegten VRAM und Latenz;
ein Klick führt in die Einstellungen. Der Modell-Block in der linken Spalte ist dafür
entfallen — der Modellname soll nicht an zwei Stellen stehen, und die Einzelprüfungen haben
ihren Platz in den Einstellungen. Gespeist wird sie von `GET /api/provider/status`: zwei
kurze Anfragen, kein Modelllisten-Abruf, Antwort auch dann, wenn der Modellserver schweigt.
Takt 20 s, im versteckten Fenster pausiert er, und das Zugriffslog blendet genau diesen
Pfad aus, damit die Konsole lesbar bleibt.

**Tastaturkürzel.** `Strg+Enter` startet (auch aus dem Textfeld), `Esc` bricht ab oder
schließt das offene Fenster, `Strg+K` öffnet die Bibliothek mit Cursor in der Suche,
`Strg+,` die Einstellungen, `1`/`2`/`3` wechseln die Variante, `Alt+C` kopiert den
Hauptprompt. Eine Übersicht hängt in der Statusleiste.

**Entschieden: `Alt+C` statt `Strg+Shift+C`.** Letzteres fängt Chrome für den
DevTools-Inspektor ab — die Seite sieht es gar nicht erst. Ein Kürzel zu dokumentieren, das
beim Nutzer nicht ankommt, wäre schlechter als ein ungewohntes, das funktioniert.

**Akzeptanzkriterien**
- Kein Weg zum Modellserver ohne Obergrenze; keine Anzeige, die ewig „wird geprüft" sagt.
- Eine abwesende Bibliothek behauptet nicht, sie sei leer.
- Die Statusleiste antwortet auch bei ausgeschaltetem Ollama, mit dem Grund.
- Der README-Schnellstart führt auf einem Rechner ohne `.venv`, ohne `node_modules` und
  ohne `dist` zu einer laufenden App.

**Verifiziert am 21.09.2026**: 254 Tests grün (12 davon neu für die Härtung), ruff sauber,
Frontend baut fehlerfrei. Im Browser durchgespielt: alle sechs Kürzel greifen, `Esc` beendet
den laufenden Modellaufruf auch serverseitig (`Komposition vom Client abgebrochen`), `Alt+C`
kopiert die offene Variante. Bei gestopptem Backend zeigen Statusleiste, Einstellungen und
Bibliothek denselben deutschen Satz statt „Failed to fetch". Der Durchlauf von Null —
`build_frontend.ps1`, frisches venv, Start — ergab eine laufende App mit acht Profilen und
ausgeliefertem Frontend.

**Ein Test, der zweimal umgebaut werden musste.** Die Prüfung, ob der Upload den Event-Loop
blockiert, war anfangs wertlos: `TestClient` fährt die App in einem eigenen Loop, und von
innen lässt sich eine Blockade ohnehin nicht stoppen — solange der Loop steht, kommt auch
der Test nicht zum Messen. Jetzt läuft sie über `ASGITransport` und misst die Parallelität:
vier Uploads à 0,4 s brauchen zusammen 0,56 s statt 1,62 s. Gegengeprüft, indem die alte
Fassung wieder eingesetzt wurde — der Test fällt dann.

## M8 — Veröffentlichung auf GitHub  ✅ umgesetzt
Öffentliches Repository unter `mIndrIc/prompt-expert`, Apache License 2.0.

**Entschieden: Apache-2.0, nicht MIT.** Genauso freizügig, aber Abschnitt 6 gewährt
ausdrücklich **keine** Markenrechte. Die App liefert das Wortlogo mit und trägt „© by
mindric lab" in der Fußzeile — der Code soll frei sein, die Marke nicht. MIT schweigt dazu.
Eine `NOTICE`-Datei nennt Name, Logo und Fußzeilenhinweis einzeln als ausgenommen und bittet
Forks, eigene Kennzeichen zu setzen. AGPL wäre hier ins Leere gelaufen: ein lokales
Ein-Nutzer-Werkzeug wird niemand als Dienst betreiben, der Reichweitenverlust wäre real.

**Datenschutz-Durchgang vor dem ersten Commit**
- `.gitignore` deckte schon `*.db`, `dist/`, `.venv/`, `node_modules/` und `*.log` ab;
  ergänzt um `*.tsbuildinfo`.
- Kein API-Schlüssel, kein Nutzerpfad und keine Mailadresse im Code — geprüft über das
  ganze Repo.
- **Zwei Funde in der Doku**: `PROFILE.md` und diese Datei nannten absolute Pfade der
  privaten Prompt-Sammlung und eine Quelle beim Namen. Beides durch neutrale Formulierungen
  ersetzt; die Aussage bleibt, die Herkunft ist nicht mehr öffentlich.
- Das Datenverzeichnis liegt ohnehin unter `%APPDATA%`, nie im Repo. Keine Referenzbilder,
  keine Prompt-Sammlung.

**README für Fremde.** Neu geschrieben: wofür das Werkzeug gut ist (Zielprofile statt einem
Prompt für alles), was es ausdrücklich **nicht** ist, Voraussetzungen, Schnellstart, die
drei Modi, Bibliothek, Modellauswahl, Tastaturkürzel, die Architektur in drei Sätzen und
die Lizenzlage. Dazu vier Screenshots in `screenshots/`, aufgenommen in 3200×2000 über das
DevTools-Protokoll gegen die laufende App — keine Montagen.

**Verifiziert am 21.09.2026**: 262 Tests grün, ruff sauber, Frontend baut fehlerfrei.

## Nicht geplant
ComfyUI-/Wavespeed-Anbindung, Bild- oder Videogenerierung, Cloud-Provider, Accounts, Binary-Packaging.

## Entschiedene Kleinigkeiten
- **Einstellungsgröße im Startframe-Prompt** (`Medium shot.`, `Wide shot.`): bleibt drin. Sie steht zwar schon im Frame, stört laut Praxistest aber nicht und stabilisiert manche I2V-Modelle.
- **Name und Marke**: Die App heißt *Prompt Expert*. Das Wortlogo liegt unter `frontend/public/mindric-lab.png`, der Hinweis „© by mindric lab" steht in der Fußzeile der App und auf der Statusseite des Backends.
- **Browserstart**: `start.bat` setzt `PE_OPEN_BROWSER=1`, das Backend öffnet den Browser selbst, sobald es wirklich antwortet. Tests und der Dev-Server tun das bewusst nicht.
- **Datenverzeichnis**: heißt jetzt `%APPDATA%\PromptExpert`. Ein Ordner aus der Zeit davor wird einmalig übernommen; bleibt trotzdem einer liegen, meldet das Backend es beim Start.
