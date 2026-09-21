# Zielprofile

Profile sind JSON-Dateien in `backend/app/profiles/`. Ein neues Zielmodell = eine neue Datei, kein Codeeingriff.

## Schema
| Feld | Typ | Bedeutung |
|---|---|---|
| `id` | string | Dateiname ohne `.json`, eindeutig |
| `label` | string | Anzeige in der UI |
| `kind` | `image` \| `video` \| `edit` | bestimmt verfügbare Modi |
| `grammar` | `prose` \| `tags` | Fließtext oder kommagetrennte Danbooru-Tags |
| `language` | `en` \| `de` | Standard-Ausgabesprache, in der UI überschreibbar |
| `fields` | string[] | welche Ausgabefelder das Profil befüllt |
| `negative_prompt.used` | bool | ob ein Negativprompt erzeugt wird |
| `negative_prompt.style` | `tags` \| `prose` | Format des Negativprompts |
| `negative_prompt.base` | string[] | immer enthaltene Grundbegriffe |
| `length.target_chars` | int | Längenziel bei Dichte „ausgewogen" |
| `length.max_chars` | int | harte Obergrenze |
| `explicit_vocabulary` | `anatomical` \| `suggestive` \| `none` | Wortwahl-Stufe für explizite Inhalte |
| `rules.must` | string[] | Pflichtvorgaben an den Composer |
| `rules.avoid` | string[] | Verbote |
| `preferred_terms` | string[] | Vokabular, das das Zielmodell versteht |
| `banned_phrases` | string[] | Füllphrasen, die herausgefiltert werden |
| `notes_for_model` | string | Freitext, wird wörtlich in den Composer-Prompt gehängt |
| `ui_note` | string | Hinweis, den die UI beim Profil anzeigt (z. B. Inhaltsfilter des Zielsystems) |
| `aspect_ratio_in_prompt` | bool | Schreibt das Zielsystem das Seitenverhältnis in den Prompt, oder kommt es aus dem Workflow? |
| `reference_slots` | bool | Versteht das Zielsystem Zuordnungen wie `(Image 1)` bei mehreren Referenzen? |
| `video_sources` | string[] | `startframe`, `references` oder beides. Pflicht bei Videoprofilen |

`length.target_chars` wird von der Dichte skaliert: knapp ×0.55, ausgewogen ×1.0, detailliert ×1.6 — begrenzt durch `max_chars`.

## Mitgelieferte Profile
| id | Ziel | Grammatik | Besonderheit |
|---|---|---|---|
| `flux_image` | FLUX / Krea, ComfyUI | prose | kein Negativprompt, natürliche Sätze, konkrete Bildentscheidungen |
| `sdxl_tags` | SDXL / Pony / Illustrious | tags | Danbooru-Tags, starker Negativprompt, Gewichtungen `(term:1.2)` |
| `wan22_i2v` | WAN 2.2 Image-to-Video | prose | Negativprompt genutzt, ein Block, eine durchgehende Kamerabewegung |
| `ltx23_i2v` | LTX 2.3 Image-to-Video | prose | **Zeitmarken** `[0-4 sec]` … `[11+ sec]`, Dialog in Anführungszeichen mit Stimmfarbe, Audio auf derselben Zeitachse, Negativprompt gegen ungewollte Tonspuren |
| `minimax_video` | MiniMax | prose | knapper Shot-Aufbau, wenige klare Bewegungen |
| `seedream_image` | Seedream 4.5 / 5 | prose | Subjekt + Handlung + Umgebung, kurze Stilwörter, Bildtext in Anführungszeichen, Rollen bei mehreren Referenzen |
| `gpt_image` | GPT-Image 2.5 (`-sunburst`, `-flare`) | prose | Anweisungssätze, Medium zuerst, präziser Bildaufbau. **Einziges Profil ohne explizite Sprache** — OpenAI filtert |
| `edit_instruct` | Identity-Edit / HeadSwap / Qwen-Edit | prose | Anweisungsform „ändere X zu Y", benennt explizit, was unverändert bleibt |

`explicit_vocabulary` wird nicht nachträglich gefiltert, sondern im Composer-Prompt durchgesetzt: `anatomical` erlaubt volle anatomische Sprache, `suggestive` nur Angedeutetes, `none` verlangt einen nicht expliziten Prompt und eine Warnung im Ergebnis, falls dafür Inhalte weggelassen werden mussten.

`ltx23_i2v` folgt einem Referenzprompt aus der eigenen Sammlung, der auf diesem Setup
nachweislich funktioniert:
ungetimte Beschreibung des Ausgangsbildes, danach die Handlung in Zeitfenstern
`[0-4 sec]`, `[4-6 sec]`, `[6-11 sec]`, `[11+ sec]` — das letzte offen. In jedem Fenster
jede bewegte Körperpartie, jede Kompositionsänderung und die ausgelöste Reaktion, bei
explizitem Material mit voller anatomischer Terminologie. Ton und Dialog sitzen im Fenster,
in dem sie passieren.

Die Begleitnotiz des Workflows verbietet Zeitmarken — der funktionierende Prompt benutzt
sie. Wir folgen der Praxis, nicht der Notiz.

`main_prompt` ist der vollständige Block zum Kopieren — Bewegung, Kameraweg, Ton und
Dialog stehen darin. Es gibt bei Videoprofilen keine Einzelfelder dafür; der Generator hat
nur ein Prompt-Feld. Einzig der Negativprompt bleibt getrennt, weil er im Generator ein
eigenes Feld ist.

## Zwei Dinge werden erzwungen, nicht erbeten

Das Modell hält Profilregeln meistens ein, aber nicht immer. Zwei Angaben sind zu wichtig,
um sie dem Zufall zu überlassen — sie werden nach dem Modellaufruf geprüft und notfalls
selbst gesetzt:

**Seitenverhältnis.** Bei `aspect_ratio_in_prompt: true` wird geprüft, ob das gewählte
Verhältnis im Hauptprompt steht. Fehlt es, hängt das Backend `Portrait 4:5 aspect ratio.`
an. Bei `false` bekommt das Modell die Anweisung, es *nicht* zu schreiben, sondern die
Bildform nur inhaltlich einzuhalten — dort setzt der Workflow das Format.

**Referenz-Zuordnung.** Bei `reference_slots: true` und mehreren Referenzen muss jede
Referenz ihren `(Image N)`-Marker im Prompt tragen. Fehlt einer, ergänzt das Backend einen
Zusatz `Reference use: subject from (Image 1), style from (Image 2)` und setzt eine Warnung,
damit erkennbar bleibt, dass die Zuordnung maschinell angehängt wurde.

## Startframe oder Referenzen

Videoziele bekommen Bildmaterial auf zwei grundverschiedene Arten, und der Prompt muss
entsprechend anders aussehen:

**`startframe`** — das Bild ist der erste Frame. Das Modell sieht ihn bereits. Der Prompt
beschreibt deshalb **ausschließlich die Handlung**: Bewegung, Kameraweg, Ablauf, Ton. Eine
Bildbeschreibung wäre hier schädlich, weil sie das Modell dazu bringt, die Szene neu zu
rendern statt sie zu animieren. Personen werden nur so knapp benannt, wie es nötig ist, um
zu klären wer was tut — bei einer einzelnen Person gar nicht. Auch die Einstellungsgröße
gehört nicht hinein; sie steht schon im Frame. Nur der Kameraweg wird beschrieben.

**`references`** — es gibt keinen Startframe. Die Bilder liefern Identität und Look, die
Szene muss gebaut werden. Hier wird beschrieben, und bei Profilen mit `reference_slots`
trägt jede Referenz ihren `(Image N)`-Marker.

Mitgeliefert: `wan22_i2v` nur `startframe`; `ltx23_i2v` und `minimax_video` beides.

## Cliplänge

Die Cliplänge gehört **nicht** ins Profil und **nie** in den Prompttext. Sie ist eine
Einstellung im Generator, die pro Clip wechselt. In der UI gibt es dafür ein optionales
Feld:

- **nicht angeben** (Standard): keine Längenvorgabe, keine Längenprüfung, kein Wort dazu im
  Prompt.
- **gesetzt**: steuert nur das Tempo der beschriebenen Handlung und begrenzt die Zeitmarken
  bei LTX. Im Prompttext taucht sie trotzdem nicht auf — der Composer wird ausdrücklich
  angewiesen, sie zu verschweigen.

## Shot-Gliederung

Enthält das Briefing eine eigene Gliederung, bleibt sie erhalten. Erkannt werden
`Shot 1`, `Szene 2`, `Scene 3`, `Cut 1`, `Take 2`, `Einstellung 1` — jeweils mit Nummer, ab
zwei Markierungen. Der Composer bekommt dann die Vorgabe, genau diese Struktur, Reihenfolge
und Beschriftung zu übernehmen; fehlt danach ein Shot im Ergebnis, erscheint eine Warnung.

Ohne Gliederung entsteht ein durchgehender Clip wie bisher.

## Widerspruchsprüfung bei Videoprofilen

Bei `kind: video` prüft das Backend den fertigen Text auf Widersprüche und meldet sie als
Warnung — es korrigiert nichts still:

- **Zeitachse**: beginnt bei 0 s, keine Überlappung, keine Lücke — und nicht länger als die
  eingestellte Cliplänge, falls eine gesetzt ist.
- **Kamera**: gegenläufige Bewegungen (heran und weg, links und rechts) oder feste und
  bewegte Kamera im selben Abschnitt.
- **Subjekt**: Stillstand und Fortbewegung im selben Abschnitt.
- **Shots**: fehlt ein im Briefing vorgegebener Shot im Ergebnis.

Entscheidend ist *im selben Abschnitt*. Erst heranfahren und dann zurückziehen ist völlig
normal und wird nicht gemeldet — deshalb zerlegt die Prüfung den Text zuerst an den
Zeitmarken **und an den Shot-Markierungen**. Ohne beides gilt der ganze Text als ein
Abschnitt.

## Neues Profil anlegen
1. JSON in `backend/app/profiles/` ablegen.
2. Backend neu starten (oder `POST /api/profiles/reload`).
3. `GET /api/profiles` prüfen — ungültige Profile erscheinen mit Fehlergrund statt still zu verschwinden.
