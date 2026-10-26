# Zeitkontext und Prompt-Cache – lokale Optimierung nach 1.4.4-rc1

Stand der ursprünglichen lokalen Analyse: 26.10.2026. Grundlage ist der RC1-Commit
`38f2cdb898d35cbc512c110fbd41463fcb80c138`. Die folgende Bestandsaufnahme und lokale
Testbilanz wurden vor der RC2-CI erstellt. Die anschließende RC2-Abnahme und Veröffentlichung
erfolgen separat gemäß [RELEASE_1.4.4-rc2.md](RELEASE_1.4.4-rc2.md), ohne produktive Installation
oder fremde Codeänderungen. Manifest-/Paketversion bleibt 1.4.4.

## 1. Belegte Herkunft und Reihenfolge

| Text | Tatsächlicher Erzeuger | Mechanismus |
| --- | --- | --- |
| `Aktuelle Zeit (Europe/Zurich): …` | Yuvomi `llm.py`, beide Träger `async_get_tools` und `YuvomiAPI.async_get_api_instance` im RC | HA-UTC-Uhr → `ZoneInfo("Europe/Zurich")` → `isoformat()` einschließlich Mikrosekunden, an den API-Prompt angehängt. |
| `Current time is … Today's date is …` | Home Assistant 2026.10.2 | `helpers/llm.py:DATE_TIME_PROMPT`; `conversation/chat_log.py:ChatLog.async_provide_llm_data` rendert das Template, wenn kein angebotener Werkzeugname mit `GetDateTime` endet. |

Dies ist eine Codeprüfung, keine Zuordnung allein anhand des Wortlauts. Der englische
Fallback verwendet Home Assistants konfigurierte lokale Zeitzone, nicht die Yuvomi-Konstante.
Für diese Installation muss die HA-Zeitzone deshalb **Europe/Zurich** sein. Die Integration
ändert diese globale Einstellung nicht. Datum/Uhrzeit werden von HA weiterhin je Anfrage
ermittelt, nicht von Yuvomi zwischengespeichert.

Die geprüften HA-Quellen legen folgende Reihenfolge innerhalb der Systemnachricht fest:

1. Gerendertes Agentenprompt (`user_llm_prompt`, sonst HA-Standard).
2. `llm_api.api_prompt`: im Assist-Modus werden Provider nach Domain sortiert; bei mehreren
   APIs kommen deren zusammengeführte Fragmente hinzu. Hier lag die deutsche Yuvomi-Zeitzeile.
3. HA-Zeit-Fallback, falls kein tatsächlich vorhandenes `GetDateTime`-Werkzeug angeboten wird.
4. `user_extra_system_prompt` bzw. zusätzlicher gespeicherter Systemkontext.

Der lokale geprüfte Assist-Router-Code übergibt seinen gemeinsamen Prompt über
`extra_system_prompt` (`assist_router/conversation.py`, `prompts.py:compose`). Damit ist
für diesen Pfad erklärt, weshalb beide Zeitzeilen **vor** dem Familienprompt erscheinen.
Ein direkt als Agentenprompt gespeicherter Familienprompt hätte eine andere Position.
Der vollständige produktive Familienprompt und der vollständige gerenderte Modellinput
liegen für diese Analyse nicht vor; wortgetreue Dopplungen darin sind nicht nachgewiesen.

Im lokalen Local-OpenAI-Referenzcode ruft `conversation.py` die HA-Methode
`async_provide_llm_data` auf. `entity.py` serialisiert `chat_log.content` zu `messages`
und die Werkzeuge separat zu `tools`, nach Werkzeugnamen sortiert. Weitere konfigurierte
Content-Injection kann danach folgen. Dieser Referenzstand ist keine neue Überprüfung der
produktiv installierten Agentenversion. JSON-Feldreihenfolge belegt außerdem noch nicht
die Reihenfolge der **Tokens**: LM Studio/llama.cpp wendet anschließend das konkrete
Modell-Chat-Template an. Ob dieses Werkzeugdefinitionen vor oder innerhalb der Systemnachricht
platziert, muss am tatsächlichen Gemma-Template bzw. gerenderten Prompt geprüft werden.

Yuvomi kann seinen API-Prompt, seine Namen/Beschreibungen/Schemas und seine freigegebenen
Werkzeuge beeinflussen. Es kontrolliert nicht HA-Template-Fallback, Familien-/Agentenprompt,
fremde Provider, History, Chat-Template, Server-Caching oder Slot-Auswahl.

Quellen:

- [HA 2026.10.2 ChatLog](https://github.com/home-assistant/core/blob/2026.10.2/homeassistant/components/conversation/chat_log.py)
- [HA Zeit-Template und API-Zusammenführung](https://github.com/home-assistant/core/blob/2026.10.2/homeassistant/helpers/llm.py)
- [HA Assist-Provider-Aggregation](https://github.com/home-assistant/core/blob/2026.10.2/homeassistant/components/llm/__init__.py)
- [Yuvomi-Ausgangscode](https://github.com/BugsDan/ha-yuvomi-mcp/blob/v1.4.4-rc1/custom_components/yuvomi_mcp/llm.py)

## 2. Was Cache-Wiederverwendung begrenzt

Der llama.cpp-Server dokumentiert `cache_prompt` als Wiederverwendung eines gemeinsamen
Token-Präfixes. Eine wechselnde Zeitzeile beendet dieses gemeinsame Präfix spätestens am
ersten tatsächlich abweichenden Token. Bereits davor stehende identische Tokens können
weiterhin wiederverwendbar sein; nicht pauschal der gesamte Prompt ist verloren. Wiederverwendung
späterer Blöcke durch optionale KV-Verschiebung ist versions-/konfigurationsabhängig und
wird hier nicht vorausgesetzt. Ein identischer Textblock hinter einer Änderung ist kein
Beweis für einen wiederverwendeten KV-Block.

Weitere Einflussgrößen:

- Wechselnde Freigaben, Schemas, Beschreibungen oder kombinierte APIs verändern die Werkzeugdefinitionen.
  Yuvomi sortiert die Namen bereits; der geprüfte Local-OpenAI-Stand sortiert sie ebenfalls.
- Andere Provider, Reihenfolge ausgewählter APIs, wechselnde Entity-/Kalenderdaten,
  Jinja-Zeitfunktionen im Agenten-/Familienprompt und History können das Präfix verändern.
- Neue Conversation-ID bedeutet neue HA-History, aber nicht zwingend leeren Server-KV-Cache.
  Derselbe Text kann auf einem passenden warmen Slot profitieren; ein anderer Slot oder
  eine Räumung muss nicht dieselben Tokens verfügbar haben. Auch dieselbe Conversation-ID
  garantiert keinen Slot und keinen Cache-Treffer.
- Ein Modell-Reload ist eine Kaltstartbedingung. Für Warmmessungen zwischen identischen
  Anfragen gerade **nicht** erneut laden. Kontextgrenze, Parallelverkehr, Server-Neustart,
  Template- oder Modellwechsel können Wiederverwendung beschränken.

| Messwert | Aussage |
| --- | --- |
| Prompt-Tokens insgesamt | Größe des tokenisierten Inputs; allein keine Aussage über neu geleistete Auswertung. |
| Tatsächlich neu evaluierte Tokens | In dieser Anfrage vom Backend neu verarbeiteter Prompt-Anteil; aus entsprechend benannten Serverwerten bestimmen. |
| Wiederverwendete KV-Tokens | Bereits verfügbare, tatsächlich wiederverwendete Zustände; nur aus expliziten Backendwerten ableiten. |
| `graphs reused` | Wiederverwendung von Ausführungsgraphen; kein Nachweis wiederverwendeter Prompt-KV-Tokens. |
| TTFT / Prompt-Evaluationszeit | Laufzeitindikatoren mit Störeinflüssen, kein direkter Tokenzähler. |

Nicht ohne Prüfung `usage.prompt_tokens - timings.prompt_n` als Cache-Treffer berechnen:
Felddefinitionen, BOS-/Template-/Re-Evaluations- und Chunk-Grenzen unterscheiden sich je Build.
Der aktuelle Upstream dokumentiert beispielsweise `prompt_progress.total/cache/processed`,
doch LM Studios gebündelter Build muss diese Felder nicht anbieten.

[llama.cpp Server-Dokumentation](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
ist die technische Referenz; ihre aktuellen Defaults sind keine Aussage über den installierten LM-Studio-Build.

## 3. Umgesetzte sichere Änderung

- Die beiden Yuvomi-Träger verwenden denselben statischen Prompt-Builder in `prompts.py`.
  Eigener Uhrzugriff und hochpräziser Zeit-Suffix entfallen vollständig.
- Kurzer gemeinsamer Kern mit Ergebniswahrheit, unklaren Schreibausgängen, Bestätigung,
  Daten-/Anweisungsgrenze und Datumsregeln bleibt ständig verfügbar.
- Einkaufshinweise nur bei Einkaufswerkzeugen; Rezeptpflegehinweise nur bei Rezeptwerkzeugen;
  knapper Menühinweis nur bei Menüwerkzeugen. Die Auswahl hängt ausschließlich von Freigaben ab,
  nicht von Uhr, Anfrageinhalt oder einem zusätzlichen LLM-Aufruf.
- Der vollständige Planungsregelblock, Rezepte, Profile und Kalenderdaten bleiben wie bisher
  im explizit abgerufenen Planungskontext. Sie werden hier weder geladen noch permanent injiziert.
- Keine neuen Werkzeuge oder automatischen Freigaben; kein künstlich nach `GetDateTime`
  benanntes Dummy-Werkzeug zur Unterdrückung des HA-Fallbacks.
- Kalender, Aufgaben, Journal, Shopping, REST, Idempotenz, Zeitberechnungen und Validierungen
  werden nicht verändert. Bestehende Namen und Parameterschemas bleiben identisch.

### Einordnung des alten Regelblocks

| Inhalt | Absicherung / Entscheidung |
| --- | --- |
| Freigaben, Bestätigung, unbekannte Werkzeuge | Backend erzwungen; knappe Modellhinweise bleiben. |
| Idempotenz, unklare Ergebnisse, kein blinder Retry | Backend-Barrieren unverändert; Ergebnisinterpretation bleibt ausdrücklich im Kern. |
| Kategorien, Produktidentität, Mengen, Notizmodi | Backend und Werkzeugbeschreibungen; kompakte Einkaufshinweise erhalten, Dopplungen entfernt. |
| Zeitzone, fehlende Uhrzeit, DST-Rückfragen | Im Kern erhalten; Modell darf Datumsbezug nicht erfinden. Generische Event-Validierung prüft weiterhin RFC3339 mit Offset, nicht die semantische Richtigkeit jeder Modellaussage. |
| Rezeptbasis und Metadaten | Nur mit Rezeptwerkzeugen. Keine vollständigen Rezept-/Planungsdaten im Basisblock. |
| Planung, Anwesenheit, Portionen und harte Regeln | Kurzer Einstieg bei freigegebenen Menüwerkzeugen, Details im bestehenden Planungskontext. |
| Familienprompt-Dopplungen | Ohne vollständigen produktiven Text nicht belegt; keine fremden Promptänderungen. |

Die permanenten Hinweise dürfen kurz sein, weil das Backend weiterhin jede Aktion selbst
prüft. Verhalten des Sprachmodells (beispielsweise Rückfragen und korrekte Formulierungen)
ist durch Python-Tests allein dennoch nicht garantiert.

## 4. Alternativen und Empfehlung

| Variante | Zuverlässigkeit / Aufwand | Tokens und Cache |
| --- | --- | --- |
| Eigene Zeitzeile entfernen, HA-Fallback behalten (**umgesetzt**) | Keine neuen Werkzeugverträge; aktueller Datumsbezug bleibt. HA muss Europe/Zurich verwenden. | Doppelte Uhr entfällt, eigener Block stabil; HA-Zeit bleibt dynamisch vor dem Router-Familienprompt. |
| Echte, explizit auswählbare Zeitfunktion mit `GetDateTime`-Suffix | Unterstützte HA-Erkennung kann den Fallback entfallen lassen. Benötigt echtes lokales Werkzeug, Freigabe-/Widerrufsregeln, Tests und verlässliche Modellnutzung. | Stabiles Schema zusätzlich; Zeitresultat nur bei Bedarf, möglicher zusätzlicher Tool-Turn bei relativen Datumsaktionen. |
| Datum statt Sekunden bzw. minutengenauer Zeittext | Einfache Reduktion der Änderungsfrequenz, aber unzureichend für „jetzt“, Mitternacht und genaue Termine. | Begrenzt dynamisch; keine vollständige Lösung. Nicht umgesetzt. |
| Zeitkontext als letzte System-/User-Nachricht | Aktuelle Zeit bliebe nahe an der Anfrage und hinter stabilen Blöcken. Erfordert Host-/Agentenunterstützung; Prioritäten und vorhandenen HA-Fallback mitbedenken. | Längeres identisches Präfix möglich, aber tatsächliche Template-/Slot-Messung erforderlich. |
| Uhr einfrieren, HA-Prompt nachträglich umschreiben oder Fake-Werkzeug | Veraltete Datumsbasis bzw. Eingriff in fremde Infrastruktur. | Nicht vertretbar; nicht umgesetzt. |

**Konkreter nächster Vorschlag:** Falls die Restmessung den HA-Fallback als wesentliche
Grenze bestätigt, eine optionale echte Zeitfunktion innerhalb von Yuvomi separat freigeben.
Sie müsste aktuelle Zeit, Datum, IANA-Zeitzone und Offset lesen; keine Schreibrechte benötigen
und keine UTC-Offsets für beliebige künftige Daten erfinden. Auch aktuelle Zeitdaten reichen
nicht zur Auflösung einer mehrdeutigen Zeit am Zieltag. Bestehende Freigaben dürfen nicht
automatisch erweitert werden. Für Agents ohne Zeitfunktion bleibt der HA-Fallback zwingend.
Alternativ kann später der Agent den Familienprompt als primären statischen Agentenprompt
und dynamische Daten am Ende bereitstellen. Hier wurden weder Router noch Agent noch HA-Core geändert.

## 5. Reproduzierbarer struktureller Vergleich

Im Repository ausführen: `python tools/compare_prompt_structure.py`.
Das Skript liest den alten Prompt aus dem festgelegten RC-Commit und die neuen statischen
Textbausteine. Es braucht nur die Python-Standardbibliothek und ein lokales Git-Repository.

| Werkzeugumfang | Vorher UTF-8-Bytes | Nachher UTF-8-Bytes | Reduktion |
| --- | ---: | ---: | ---: |
| Nur Aufgaben/Kalender | 4255 | 1057 | 75,16 % |
| Bisherige Standardwerkzeuge mit Einkauf | 4255 | 2305 | 45,83 % |
| Standard plus Rezepte | 4255 | 2799 | 34,22 % |
| Standard plus Rezepte und Menüplanung | 4344 | 3019 | 30,50 % |

Verglichen wird **nur der statische Yuvomi-API-Prompt**, ohne die zusätzlich entfallene
deutsche Zeitzeile, unveränderte Werkzeuge, Familien-/Agentenprompt oder HA-Fallback.
Keine Tokenzählung, kein prozentualer Rückgang des gesamten Modellinputs und keine KV-Messung.
Die Werkzeugdefinitionen werden nicht verändert; daher gibt es dafür hier keine Einsparung.

Vom Benutzer gelieferte Referenzwerte für „hallo“: ohne APIs 2792, bisher Assist 6390,
optimiert Assist 6337, dediziert Yuvomi 5574 Prompt-Tokens. Diese Werte stammen aus früheren
Messungen und sind **keine Nachher-Messung dieser Änderung**; Cache-Zähler liegen nicht vor.

Aktualisierte Betreiberreferenz für den RC2-Vergleich: **3864 vollständige Prompt-Tokens**
bei „hallo“, Familienprompt v2.4 und **RC1**. Auch dies ist kein RC2-Messergebnis.

## 6. LM-Studio-Messablauf

1. Modell-/GGUF-Kennung, Quantisierung, LM-Studio-/llama.cpp-Build, Chat-Template,
   Kontextgröße, Slot-/Parallelitäts- und Cache-Einstellungen dokumentieren. Agenten-/Familienprompt,
   APIs, Freigaben, Locale und HA-Zeitzone unverändert lassen. Private Promptinhalte nicht veröffentlichen.
2. Baseline RC und lokale Optimierung getrennt in einer Testinstallation messen; keine
   produktive Installation durch diesen Auftrag. Für jeden Zustand Modell einmal neu laden.
3. **Kaltmessung:** neue Conversation, identische Eingabe „hallo“. Danach **Warmmessungen**:
   Modell geladen lassen, mindestens fünf neue Conversations mit „hallo“ nacheinander;
   genügend Zeitabstand, damit die HA-Sekundenzeile tatsächlich wechselt. Keine parallelen Clients.
4. **History-Fall separat:** fünf gleiche Eingaben in derselben Conversation, ohne Reload.
   Wachsende History gesondert ausweisen. Nicht als identische vollständige Requests bezeichnen.
5. **Slot-Fall separat:** sofern Logs Slot-IDs liefern, gleichen und anderen Slot vergleichen.
   Keine nicht unterstützten `id_slot`-/Cache-Parameter an LM Studio senden. Ohne Slot-Nachweis
   keine Zusicherung einer gleichen Slot-Zuordnung.
6. Je Request Zeitpunkt, Conversation-/Request-ID (lokal anonymisiert), Slot-ID wenn verfügbar,
   vollständige Prompt-Tokenzahl, explizit neu evaluierte und KV-wiederverwendete Tokens,
   Prompt-Evaluationszeit und TTFT erfassen. Rohfeldnamen/Einheiten erhalten. Nicht vorhandene
   Werte als „nicht verfügbar“ notieren. `graphs reused` separat erfassen.
7. Vollständige Namen, Beschreibungen und Parameterschemas je API-Konfiguration vergleichen;
   nach Möglichkeit kanonisches JSON hashen. Tatsächlich gerenderten Input prüfen, um Änderungen
   vor Werkzeugen/Systemprompt und verbliebene Zeitinjektion zu lokalisieren. Keine Secrets loggen.
8. Kalt-/Warmwerte getrennt tabellieren; Median und Spannweite der Wiederholungen angeben.
   Erst danach Tokenreduktion, Evaluationsreduktion und KV-Wiederverwendung getrennt bewerten.

Funktionale Stichproben in der Testinstallation: Einkauf mit Freitextmenge/Notiz, Kategorie
eines bestehenden Produkts, Wiederholung nach Timeout, „morgen“ über Mitternacht, Termin vor/nach
Zeitumstellung, Datum ohne Uhrzeit, ungültige und doppelte 02:30-Uhr-Zeiten, Menüabfrage „morgen“
sowie gezielte Tagesänderung und separate Wochenplanung. Keine zusätzlichen Zeit-Tool-Aufrufe
für gewöhnliche Einkaufsbefehle erwarten; neu eingeführt wurden keine.

## 7. Tests und Grenzen

- Neue Tests für stabile/bedingte Prompt-Zusammensetzung, Sicherheitsleitlinien,
  Europe/Zurich-Datumsgrenzen, Jahreswechsel, Sommer-/Winter-Offsets, Kalenderanwesenheit,
  DST-Lücke/Falte sowie aktuelle/nächste Planungsperiode.
- Echte HA-ChatLog-Regression vorbereitet: identische Assist-/Dedicated-Prompts, unveränderte
  Werkzeuge, erhaltene HA-Zeitzeile und nachgewiesene Position vor zusätzlichem Familienkontext.
- Lokal Python 3.12: **521 bestanden, 0 fehlgeschlagen, 2 Module übersprungen**, weil echtes HA
  hier nicht installiert ist. Diese beiden Module umfassen die echten HA-Laufzeittests;
  die neue ChatLog-Regression wurde lokal deshalb **nicht ausgeführt**.
- Erster Volltestlauf scheiterte bei fünf Temp-Verzeichnis-Fixtures an Windows-Sandbox-Rechten;
  vollständiger Wiederholungslauf mit frischem `--basetemp` im Workspace erfolgreich. Keine Tests deaktiviert.
- Ruff, Format- und Repository-Prüfung separat ausführen. Die grüne RC-CI gilt für den
  Ausgangscommit und ersetzt keine neue echte HA-2026.10.2-Abnahme dieser lokalen Änderungen.

Vor RC2-Veröffentlichung: echte HA-CI auf neuem Prüfstand. Anschließend bleiben
Gemma/LM-Studio-A/B und fachliche Sprachtests durch den Betreiber erforderlich.
Die spätere CI-Abnahme ersetzt nicht die hier ausdrücklich noch ausstehenden Modellmessungen.
