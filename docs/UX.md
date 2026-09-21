# UX

## Aufbau
Drei Spalten ab 1100 px, Dark UI.

- **Links** — Modus (Verbessern / Bild / Video), Zielprofil, Prompt-Dichte, Seitenverhältnis, Ausgabesprache.
- **Mitte** — Briefing-Editor; in den Bildmodi darüber der Referenz-Strip mit Thumbnails, Rollen-Dropdown pro Bild und Drag-Reihenfolge.
- **Rechts** — Ergebnis in Tabs `Präzise` · `Cinematic` · `Experimentell`, darunter Bibliothek-Kurzliste.

Jedes Ausgabefeld ist ein eigener Block mit eigenem Copy-Button. Bei Bild und Edit sind das Hauptprompt, Negativprompt und Kamera. Bei Video ist es **ein** Block — Bewegung, Kameraweg, Ton und Dialog stehen darin, weil der Generator dort nur ein Eingabefeld hat. Der Negativprompt bleibt auch bei Video separat. Darunter Begründung und Warnungen, aufklappbar.

Aktionen unter dem Ergebnis: Kopieren · Exportieren · Neu generieren · Als Ausgangsprompt übernehmen · In Bibliothek merken (mit Tags).

## Einstellungen
Knopf *Einstellungen* in der Topbar, Overlay über der App, `Esc` schließt. Der Arbeitsstand in den
drei Spalten bleibt stehen. Inhalt: Modellserver mit Verbindungstest, Modellauswahl als
Dropdown mit Größe und Bildfähigkeit, Referenzbild-Limits, Standards und ein aufklappbarer
Block mit Temperatur, Kontextgröße und Timeouts.

Zwei Dinge dort halten sich an dieselbe Regel wie der Rest: nichts behaupten, was nicht
belegt ist. Ein Modell, dessen Fähigkeiten der Server nicht meldet, heißt *Bilder: unbekannt*
und bleibt wählbar; nur belegbar bildunfähige Modelle sind im Vision-Feld ausgegraut. Ein
eingetragenes, aber nicht installiertes Modell verschwindet nicht, sondern steht als
*nicht installiert* in der Liste, mit dem `ollama pull`-Befehl daneben.

Gespeicherte Standards gelten für den nächsten Start — was links eingestellt ist, hat der
Nutzer für diesen Durchlauf gewählt und bleibt stehen. Der Verbindungsstatus dagegen wird
sofort neu geprüft.

## Bibliothek
Unter dem Ergebnis stehen die letzten fünf Läufe als Kurzliste, der gerade erzeugte ist
markiert. Ein Knopf führt in die Vollansicht — ein Overlay wie die Einstellungen, mit
Volltextsuche, Filtern (Favoriten, Modus, Zielprofil, Tag-Chips), Liste links und Eintrag
rechts.

Gespeichert wird automatisch, ein Lauf je Eintrag: Briefing, Referenz-Vorschaubilder,
Analyse und alle Varianten zusammen. Im Eintrag lassen sich Varianten durchblättern, Felder
einzeln kopieren, Tags setzen, der Favorit umlegen, der Prompt als Ausgangsprompt übernehmen
und der Eintrag löschen. Löschen und Leeren verlangen beide eine zweite Bestätigung an
derselben Stelle — kein Browserdialog.

## Beispielablauf
1. Modus „Referenz → Videoprompt".
2. Charakterbild als `Subject`, Moodboard als `Style` ablegen.
3. Briefing: „Blick zur Kamera, leichter Wind, langsamer Dolly-in."
4. Zielprofil `ltx23_i2v`, Dichte `detailliert`, Sprache `Englisch`.
5. Ergebnis: Hauptprompt mit Ausgangsszene und Handlungsverlauf, Audio/Dialog-Block, Kamerahinweise, Kontinuitätsmerkmale in der Begründung.

## Statusleiste
Die Fußzeile zeigt dauerhaft, woran die App gerade hängt: Punkt, Modellname, belegter VRAM
und Latenz. Ein Klick darauf öffnet die Einstellungen. Ist der Modellserver aus, steht dort
der Grund statt einer Zahl; liegt das Modell nicht im VRAM, sagt sie, dass der erste Lauf
länger dauert — das ist ehrlicher, als es zu verschweigen.

Sie ersetzt den früheren Modell-Block in der linken Spalte. Der Modellname soll nicht an
zwei Stellen stehen, und die Einzelprüfungen des Verbindungstests haben ihren Platz in den
Einstellungen.

## Tastaturkürzel
| Taste | Wirkung |
|---|---|
| `Strg` + `Enter` | Lauf starten, auch aus dem Textfeld heraus |
| `Esc` | Laufenden Lauf abbrechen, oder ein offenes Fenster schließen |
| `Strg` + `K` | Bibliothek öffnen, Cursor steht in der Suche |
| `Strg` + `,` | Einstellungen öffnen |
| `1` `2` `3` | Zwischen den Varianten wechseln |
| `Alt` + `C` | Hauptprompt der offenen Variante kopieren |

Die Zifferntasten greifen nur, wenn der Cursor in keinem Eingabefeld steht. Kopiert wird mit
`Alt`+`C` und nicht mit `Strg`+`Shift`+`C`: letzteres fängt Chrome für den
DevTools-Inspektor ab, die Seite bekommt es nie zu sehen.

## Status statt Fortschrittsbalken
Ehrliche Stufen, keine erfundenen Prozente:
`Bilder werden vorbereitet` → `Referenzen werden analysiert` → `Prompt wird komponiert (1/3)` → `fertig`

Jede laufende Anfrage ist abbrechbar. Die UI bleibt bedienbar.

## Fehlertexte
- „Unter `{base_url}` antwortet kein Modellserver. Starte Ollama oder prüfe die Base URL in den Einstellungen."
- „Das Modell `{model}` ist nicht installiert. Wähle eines der gefundenen Modelle oder hol es mit `ollama pull {model}`."
- „`{model}` kann keine Bilder verarbeiten. Wähle für die Bildanalyse ein Vision-Modell."
- „Der Modellserver hat nach {sekunden}s nicht geantwortet. Modell zu groß für den freien VRAM oder Kontext zu lang."
- „Die Analyse kam nicht als gültiges JSON zurück. Kleinere Bildkante in den Einstellungen oder ein anderes Modell hilft meistens."
- „Diese Referenz wirkt nicht eindeutig erwachsen. Analyse abgebrochen."
- „Das Backend ist nicht erreichbar. Läuft start.bat noch?"
- „Das Backend hat nach {sekunden} s nicht geantwortet. Läuft der Modellserver noch, oder ist
  er mit einem anderen Lauf beschäftigt?"

Kein Fehler erreicht die Oberfläche unübersetzt: was zwischen Browser und Backend schiefgeht,
wird abgefangen und als deutscher Satz gezeigt, nie als „Failed to fetch". Und eine Ansicht,
die ihre Daten nicht laden konnte, sagt das — sie behauptet nicht, es sei nichts da.

## Ton
Knapp, sachlich, kein Marketing. Keine Hinweise darauf, was die App alles nicht darf — die Grenzen greifen im Zweifelsfall, sie müssen nicht dauernd erwähnt werden.
