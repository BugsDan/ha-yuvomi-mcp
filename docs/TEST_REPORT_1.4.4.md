# Implementierung und lokale Prüfungen 1.4.4

> Nachtrag GitHub-CI-Abnahme vom 26.10.2026: echte HA-2026.10.2-Laufzeitprüfung **526 bestanden, 0 fehlgeschlagen, 0 übersprungen**; alle fünf CI-Jobs erfolgreich. [CI-Nachweise, Korrekturen und Grenzen](CI_ACCEPTANCE_1.4.4.md). Die folgenden lokalen Angaben dokumentieren den vorausgehenden Entwicklungsstand; die dort offene HA-/HACS-/hassfest-Abnahme wurde inzwischen in GitHub durchgeführt.


Stand: 26.10.2026, lokale Prüfversion. Details zur Einrichtung und A/B/C-Messung: [SETUP_1.4.4.md](SETUP_1.4.4.md).

## Implementierter Umfang

- Konservative Beschreibungs-Overlays mit Vertragsvergleich für bekannte lokale/Remote-Werkzeuge; unbekannte/veränderte Schemas bleiben erhalten. Alter gemeinsamer Basisprompt bei den neun bisherigen Werkzeugen unverändert.
- Eigene auswählbare HA-LLM-API, Lifecycle-Registrierung/Abmeldung, explizite reversible Expositionsmodi. Gleiche Runtime/Allowlist/Bestätigung/Journal; alte API-Toolinstanzen verlieren nach Moduswechsel ihre Berechtigung über den bisherigen Träger.
- Drei neue opt-in Werkzeuge: get_menu_planning_context, save_menu_plan, get_menu_plan. Kein sync_menu_plan_shopping und keine generische Schreibbrücke.
- Lazy geladener atomarer Planungsstore (Schema 1), HA-Optionseditor mit validierten strukturierten Feldern, Familien-/Kalender-/Zeit-/Periodenregeln. Keine Rezept-, Vorrats- oder tatsächliche Resten-Datenbank.
- Gemma wählt IDs und Verteilung; Backend berechnet Portionen/Skalierung, prüft Regeln und aktuelle Quellen und schreibt über apply-plan. Bestehende Slots bei Erstplanung geschützt; eindeutige Tagesänderung genau ein Slot, freie Notizen erhalten.
- Zusatzportionen als Quell-/Zielzuordnung in Yuvomi-Notizen; Zutaten nur am Kochtag, kein Rezept-Fallback beim Aufwärmeintrag. Zielbedarfe nicht doppelt zuordnen, maximal zwei lokale Kalendertage, Verträglichkeit und Wiederaufwärmbarkeit prüfen.
- Persistente meals-Ausführungsbelege im erhaltenen Journal Schema 2, Serialisierung, POST-Idempotenz, Replays, Timeout-/Teilantwort-/Neustartbarrieren und nur lesende administrative Reconciliation.
- Zentrale agentenunabhängige Planungskomponenten und Planungsprompt; kein Hintergrunddienst, keine Router-/Conversation-Manipulation.

## Nachvollziehbare Etappen

1. Beschreibungsoptimierung und bestehende Shopping-/Recipe-/Runtime-Regression: **110 Tests bestanden**.
2. API-Träger und Integration der neuen Module: bestehende Suite inklusive Beschreibungsregression **453 bestanden, 1 HA-Modul übersprungen** (Windows/Python 3.12).
3. Planungskonfiguration, Datenzugriffe und Basissicherheit: **33 neue Menütests bestanden**.
4. Ergänzte Tagesersetzung, Journal-/Timeout- und Kalenderfälle: **42 Menütests bestanden**.
5. Abschliessende gesamte Suite und Paket-/Metadatenprüfung: siehe nachfolgenden finalen Prüfabschnitt. Keine Tests deaktiviert; zwei bestehende Optionsmenü-Erwartungen wurden um die tatsächlich neuen Seiten erweitert, ihre Produktkatalog-Ausschlussprüfung bleibt erhalten.

Das bestehende pytest-Tempverzeichnis war im Windows-Sandboxprofil nicht beschreibbar; Tests verwenden deshalb ein ignoriertes --basetemp innerhalb des Projektverzeichnisses. tzdata 2026.5 ergänzt die lokale Windows-Testumgebung und ist Testabhängigkeit; HA liefert seine Zeitzonendaten selbst. Keine produktiven Python-Pakete verändert.

## Struktur- und Modellmessung

Die tatsächlich erzeugten **neun** bisherigen Werkzeugdefinitionen inklusive vollständiger Schemas: **11026 → 7467 kanonische UTF-8-Bytes, 32,3 % weniger**. Alle 16 bekannten Baseline-Parameterverträge sind nach Entfernen ausschliesslich der Beschreibungstexte identisch. Die frühere 13er-Referenz bleibt bei 26,4 % Strukturreduktion; beide Angaben sind keine Modellmessungen. Einzel-/Sammelwerkzeug besitzen weiter dieselben Artikelparameter und vollständige category-Hinweise einschliesslich NEW-Emphase.

Betreiberwerte: Assist mit neun Werkzeugen **6390**, Assist deaktiviert **2792** vollständige Prompt-Tokens. Die Differenz **3598** umfasst sämtliche Assist-Beiträge und ist keine vorausgesagte API-Einsparung. B (optimierte Assist-Beschreibungen) und C (dedizierte Yuvomi-API) noch **nicht gemessen**. Reproduzierbare Snapshots in [AB_TOOL_DEFINITIONS_1.4.4.json](AB_TOOL_DEFINITIONS_1.4.4.json).

## Bewusste Grenzen und Freigabepunkte

- **Kein getrenntes Einkaufs-Schreibwerkzeug:** Der geprüfte Meals-Transfer kennt zwar on_shopping_list-Flags und Rezept-Fallback, belegt aber keine sichere Pantry-/Produktidentität, Packungsgrössen-Konversion oder dauerhafte Beitrags-/Differenzsynchronisation über Planänderungen. Die vorhandene Einkaufslogik addiert/replaced und ist dafür kein Ersatz. Ohne belastbaren Pantry-Vertrag und eigene dauerhafte Sync-Belege wäre eine Teilumsetzung unsicher. Planung führt niemals Einkaufs-/Vorratsschreiben aus.
- Vollständige Wochenplanung setzt ausdrücklich neue separate Planungs-Conversation voraus. Kurze Menüabfragen laden keinen Planungskontext. Tagesänderung mit exaktem Rezept liefert nur diese Variante; ohne konkretes Rezept kann der Auswahlkontext grösser werden. Keine automatische Isolation; echte Kontexttrennung vor Produktivfreigabe prüfen.
- Familien-/Kalenderdaten werden in validierten HA-Objektfeldern gepflegt, kein vollständiger klickweiser Profilassistent. Neue Konfigurationen brauchen bewusst eingegebene Profile; persönliche Daten werden nicht geraten.
- Unterschiedliche Gerichte für verschiedene Personen im selben Mahlzeitslot sowie nicht gemeinsam autorisierte Abhängigkeiten werden sicher zurückgewiesen/klärbar gemeldet. Neue Aufwärmziele ausserhalb der autorisierten Periode werden nicht heimlich geschrieben. Vorhandene eindeutig dokumentierte Quellen können lesend berücksichtigt werden. Tatsächliche Resten bleiben unüberwacht.
- Rezeptmengen müssen skalierbar sein; keine geratene Packungsumrechnung oder Rundung wiederholter Dezimalbrüche. Unbekannte Zeiten unter Tageslimit führen zu Rückfrage/Fehler. Allgemeines Resten bleibt ohne realen Restenbeweis möglich.
- Vollständige ursprüngliche Alexa-Request-ID ist im bisherigen Toolkontext nicht garantiert. Stabile aktive Kontexte, Journal und konservativer kurzfristiger Intent-Schutz verhindern getestete Retries; keine globale Exactly-once-Garantie über neue Anfragen, Journalverdrängung und fremde Clients. prepared/unknown wird niemals automatisch erneut ausgeführt.
- Das ausdrücklich akzeptierte Konkurrenzfenster zwischen erneutem Lesen und Slot-Ersetzung bleibt. Erstplanung verwendet skip_occupied. Fehlende/geskippte Teilantworten blockieren weitere Schreibaktionen und behaupten keinen vollständigen Erfolg.
- HA 2026.10.2 verlangt Python >=3.14.2; lokal vorhanden sind Windows/Python 3.12, kein nutzbares WSL und kein Docker. Echte HA-Laufzeittests, HACS-Action und hassfest können hier nicht vollständig ausgeführt werden. Vorhandene echte HA-Tests wurden um Carrier-/Registry-/Merge-/Optionsfälle ergänzt, werden lokal weiterhin durch denselben vorhandenen importorskip übersprungen. Originalquellverträge und lokale Agentenreferenz wurden geprüft; kein Ersatz durch simuliertes „HA bestanden“. Linux-/HA-CI oder Testinstanz ist vor Freigabe erforderlich, wurde wegen Push-Verbot nicht gestartet.
- Keine reale Gemma-Werkzeugwahl, LM-Studio-Nachmessung oder produktive GUI-Abnahme durchgeführt. Eigene API im tatsächlich installierten Local-OpenAI-Agenten auswählen und Reload/Reversibilität prüfen.

## Noch erforderliche manuelle Abnahme

1. In Test-HA API-Auswahl/Reversibilität und unveränderte Freigaben prüfen; Menü-/Rezeptwerkzeuge bleiben zunächst aus.
2. A/B/C wie SETUP dokumentiert mit identischem Modell/Systemprompt und den neun Tools messen; Gemma-Regression für Mengen, Kategorien, Notizen, Aufgaben und Termine.
3. Planung bewusst konfigurieren, die drei Tools aktivieren. Ganze Woche in separater Conversation; gespeicherte belegte Tage unverändert, kurze Rückmeldung.
4. Exakte Tagesänderung/Variante via Alexa und reine Menüabfrage prüfen. Ganze Rezeptbasis unverändert; richtige Zutaten/Portionen in GUI-Details und sichere Aufwärm-Transferdarstellung.
5. Kalender mit echten Benutzerechten, Reload/Neustart, Timeout- und Reconciliation-Fälle in Testumgebung prüfen.

Keine automatische Installation oder Veröffentlichung. Bestehender unveröffentlichter 1.4.2-Draft, Tags und GitHub werden nicht verändert.

## Finaler lokaler Prüfstatus

- Vollständige Suite: **502 bestanden, 1 übersprungen** (ein bestehendes HA-Testmodul wegen nicht installiertem HA); davon **49 neue Menütests** und **1 Beschreibungstest**. Die zusätzlichen echten HA-Carrier-/Options-/Registry-/Merge-Tests sind vorhanden, lokal aber nicht ausgeführt.
- Ruff check: erfolgreich. Ruff format --check: erfolgreich.
- Repository-/Metadaten-/HACS-Layout-/Publikationsprüfung mit Prüfreferenz v1.4.4: **0 Befunde**; es wurde dafür kein Tag erstellt.
- tools/check_ha_api.py: originale HA-2026.10.2-Verträge erfolgreich geprüft, einschliesslich unveränderter Toolplattform-/Schema-/Call-Signaturen. Zusätzlich Originalquellen für Registry, MergedAPI, Local-OpenAI-Mehrfachauswahl und Calendar-Service-Aufruf geprüft. Das ist keine HA-Laufzeitausführung.
- Lokale Installations-/Source-ZIPs werden ausschliesslich aus der Publikations-Allowlist gebaut; Paket-/Layout-/Bytegleichheit ist Teil der bestehenden Regressionstests. Keine .storage-, Token-, lokalen Settings-, Cache- oder Analyseverzeichnisse im Paket.
- git diff --check: erfolgreich; bestehender Git-HEAD und Index bleiben unverändert. Kein Commit/Push/Tag/Release/Deployment.

Testaufruf: `python -m pytest -q --basetemp .test-tmp-planning-analysis/tests-last-races`. Die Nummer v1.4.4 in Prüfparametern ist lediglich Versionsvalidierung, keine Git-Operation. Echte HACS-/hassfest-Ausführung und HA-2026.10.2-Laufzeitabnahme bleiben offen wie oben beschrieben.

Zusätzliche Abschlussregression: Änderungen der Konfigurationsrevision während der Kontextbeschaffung oder nach dem dauerhaften prepared-Beleg werden erneut erkannt; alte Regeln können nicht mit einer neuen Revision beschriftet oder danach unbemerkt geschrieben werden. Beide Fälle sind durch eigene Tests abgedeckt.
