# Werkzeugkontext und Beschreibungsoptimierung 1.4.4

> Umsetzung vom 26.10.2026: Lokale Implementierung ausdrücklich freigegeben; eigene LLM-API jetzt enthalten. Ältere „nur Analyse“-/„später freigeben“-Passagen unten dokumentieren den vorausgehenden Entscheidungsstand. Verbindlicher tatsächlicher Umfang, Grenzen, Konfiguration und neue Referenzmessungen: [SETUP_1.4.4.md](SETUP_1.4.4.md), [TEST_REPORT_1.4.4.md](TEST_REPORT_1.4.4.md). Kein Push/Tag/Release oder produktiver Eingriff.


**Nur Analyse und Entwurf.** Kein Produktionscode, keine bestehenden Schemas oder Freigaben geändert. Die maßgebliche echte Tokenmessung erfolgt durch den Betreiber in den LM-Studio-Serverlogs mit dem tatsächlich verwendeten Gemma 4 12B. Diese Analyse benötigt keine weitere Tokenizer-Installation.

## 1. Produktive Referenz und Messumfang

**Betreiberangabe vom 25.10.2026: 6604 vollständige Prompt-Tokens** bei neuer Conversation mit „hallo“, produktivem Gemma 4 12B über LM Studio. Ursprünglich ungefähr 9800; die bisherige Verringerung stammt aus Systemprompt-Optimierung, angepasster/reduzierter Werkzeugexposition und Entfernung sämtlicher für Assist freigegebener HA-Entitäten. Smart-Home-Steuerung erfolgt direkt über Alexa. Die Eingriffanteile lassen sich aus diesen zwei Gesamtzahlen nicht einzeln bestimmen.

Diese 6604 sind **nicht ausschließlich Yuvomi-Tokens** und keine Messung unseres lokalen 1.4.3-Snapshots allein. Die nachfolgende Beschreibungsoptimierung ist noch nicht implementiert. Insbesondere sind **26,4 % Strukturreduktion keine bereits realisierte produktive Tokenersparnis**. Eine neue echte Messung folgt erst nach freigegebener Implementierung bei gleichem Systemprompt, Modellkonfiguration und identischen Werkzeugfreigaben.

### Vollständiges Inventar

Aus dem lokalen 1.4.3-Runtime-Aufbau wurden die tatsächlich wirksamen lokalen Einkaufs-/Rezeptschemas sowie die unveränderten offiziellen Yuvomi-2.79.0-Serverdefinitionen zusammengeführt. Parameterschemas sind mit der vorhandenen probatio-Version als OpenAPI 3.1 exportiert. Gemessen werden vollständige OpenAI-kompatible function-Definitionen: **Name inklusive yuvomi_mcp__-Präfix, Beschreibung und sämtliche Parameterschemas**. Keine Messung nur der Beschreibungstexte.

Die konkreten freigegebenen Werkzeuge der produktiven HA-Installation wurden nicht abgefragt. Reproduzierbare Profile statt erfundener aktiver Konfiguration:

- **6 Standardwerkzeuge:** list_shopping_items, add_shopping_item, list_tasks, create_task, list_upcoming_events, create_event.
- **9 mit Einkaufserweiterungen:** zusätzlich list_shopping_categories, suggest_shopping_items, add_shopping_items.
- **13 kuratierte:** zusätzlich list_recipes, get_recipe, create_recipe, update_recipe. Diese vier bleiben standardmäßig deaktiviert, bis sie ausdrücklich freigegeben werden.
- **16 potenziell exponierbare:** zusätzlich list_api_operations, get_api_operation, call_api_operation. Keine Empfehlung zur Freigabe; auch die generischen Leser behalten die bestehende Bestätigung unbekannter Werkzeuge.

Yuvomi kann abhängig von Tokenrechten weniger Serverwerkzeuge liefern; zukünftige/unbekannte Servertools sind nicht durch den geprüften Snapshot abgedeckt und dürfen nicht ohne Validierung umgeschrieben werden. Lokale Einkaufsdefinitionen haben wie heute Vorrang vor gleichnamigen Serverdefinitionen. Keine Funktion und kein ausgewähltes Werkzeug wird für bessere Messwerte verborgen.

Vollständige Vorher-/Nachher-Artefakte:

- [TOOL_DEFINITIONS_CURRENT_1.4.3.json](TOOL_DEFINITIONS_CURRENT_1.4.3.json)
- [TOOL_DEFINITIONS_DRAFT_1.4.4.json](TOOL_DEFINITIONS_DRAFT_1.4.4.json)
- [TOKEN_MEASUREMENT_1.4.4.json](TOKEN_MEASUREMENT_1.4.4.json): absolute Werte, Profile, Einzeldefinitionen, Prompttexte und Quellenhashes.
- [PROMPT_DRAFT_1.4.4.md](PROMPT_DRAFT_1.4.4.md): separater, noch nicht aktiver Kurzprompt.

## 2. Struktureller Vergleich ohne Tokenizer

Beide Varianten werden identisch serialisiert: UTF-8-JSON, sortierte Objektschlüssel, ensure_ascii=false, ohne zusätzliche Leerzeichen. Die kompletten Parameterverträge sind nach Entfernung **ausschließlich der Beschreibungstexte** strukturell identisch: gleiche Namen, Parameter, Datentypen, required, enum, Formate, Min-/Maxwerte und additionalProperties. Eine echte Schema-Property mit dem Namen description bleibt erhalten; nur description-Werte vom Typ string werden als Annotation behandelt.

| Profil | Ganze Definitionen vorher (UTF-8 Bytes) | Entwurf | Einsparung |
| --- | ---: | ---: | ---: |
| 6 Standard | 6714 | 4753 | 29.2 % |
| 9 Einkauf | 11026 | 7467 | 32.3 % |
| 13 kuratierte | 16778 | 12348 | 26.4 % |
| 16 einschließlich Brücke | 18675 | 14083 | 24.6 % |

Das sind Byte-/Strukturwerte, keine Gemma-Tokenzahlen. Neue Menüwerkzeuge sind nicht in diese Einsparung hineingerechnet: drei geplante Definitionen benötigen zusätzlich **2620 Bytes**, mit dem getrennten Sync-Entwurf **3237 Bytes**. Ihre Schemas stehen in [MENU_TOOL_CONTRACT_DRAFT_1.4.4.json](MENU_TOOL_CONTRACT_DRAFT_1.4.4.json). Die tatsächliche neue Gesamtlast hängt von expliziten Freigaben ab. Neue Werkzeuge dürfen die Einsparung teilweise aufbrauchen; eine pauschale 50-%-Zusage wäre falsch.

## 3. Konkrete Kürzungen je Werkzeug

Die vollständigen konkreten Zieltexte inklusive Parameterbeschreibungen stehen im Entwurfs-JSON. Folgende Tabelle beschreibt die beabsichtigten Änderungen, keine bereits vorgenommene Umsetzung:

| Werkzeug | Optimierung / zu erhaltender Kern |
| --- | --- |
| add_shopping_item | Gemeinsame Mengen-/Kategorie-/Notizregeln einmal knapp im Haupttext; Felder nennen nur ihre spezifischen Eingaben. Exakte Produktidentität, bestehende Kategorie, Erstkategorisierung, Ersatz statt geratener Arithmetik und kein blinder Retry bleiben |
| add_shopping_items | Derselbe kurze Kern; klar category je items[] und 1–20 Artikel. Keine abweichende Semantik oder zusätzliche Modellrunde |
| list_shopping_categories | Ein Satz: echte aktuelle Namen/Reihenfolge für neue Artikel; keine erfundenen Kategorien |
| suggest_shopping_items | Präfixsuche ist keine Produktidentität; ähnliche Namen getrennt, historische Mengen niemals kopieren |
| list_shopping_items | Kurzer Zweck und Vorgabe unchecked; include_checked behält unveränderten Typ/Vertrag |
| list_tasks | Aktuelle Top-Level-Aufgaben, optional Status/AND-Tags. Archiv als separates Archiv und future-Start-Verhalten im Feld erhalten |
| create_task | Kurzer Zweck; Kategorie/Tags, Priorität und Datums-/Zeitformate bleiben in ihren Parametern |
| list_upcoming_events | Heute/vorausliegende Yuvomi-Termine; limit 1–100/Vorgabe 20 bleibt als Feldhinweis erhalten |
| create_event | Zeitformat und Haushaltszeit-/Offsetumwandlung kompakt nur im Datumsfeld; fehlendes Ende und all_day-Semantik bleiben |
| list_recipes | Aktuelle vollständige Rezeptdaten/Metadaten lesen; keine Planung und kein Einkaufsübertrag |
| get_recipe | Exakte ID lesen; intern nötiger vollständiger GET muss nicht im Modelltext wiederholt werden |
| create_recipe | Mittagessen/Basisportionen 4, bekannte Metadaten und begründeter KI-Gesundheitsvorschlag. Exakte Variante, Resten ohne Zutaten, keine Bilder/Links/Skalierung/Übertragung |
| update_recipe | Ausgelassene Felder/Notizen/Bilder/Links erhalten, explizites replace/clear; neue Gesundheit nur mit Begründung, neue Basis mit passenden Zutaten; Provider-Schutz und unklare Ausgänge bleiben |
| list_api_operations | Kurzer Metadatenzweck; bestehende HA-Bestätigung ausdrücklich nicht entfernen |
| get_api_operation | Operation-Key lesen, unverändert bestätigt; keine Umklassifizierung als automatisch erlaubter Leser |
| call_api_operation | Tokenbeschränkung und HA-Bestätigung; kein Umgehen dedizierter Werkzeuge oder neues generisches Schreibrecht |

Wesentliche Parameterhinweise bleiben trotz Kürzung: beim offenen Artikel ohne Mengenangabe +1 der sicher erkannten bestehenden Einheit, bei neu/abgehakt 1; note-only niemals ensure/increase; clear ohne note/notes; Sonstiges nur bei fehlender spezifischer Kategorie; keine neuen Marken-/Größenersetzungen; Rezeptmenge ist Basis, keine Mindestmahlzeit. Die langen Beispiele/Sicherheitsabsätze werden nicht in jedes Feld kopiert. Wichtige Regeln stehen weiter am richtigen Entscheidungsort.

Umsetzungsempfehlung: kleine explizite Beschreibungsoverlays für bekannte Werkzeuge/Felder statt neuer generischer Prompt-Umschreiblogik. Bei Remote-Schemaabweichungen das ursprüngliche Schema samt unpassenden/noch unbekannten Feldbeschreibungen erhalten oder den Overlay gezielt nicht anwenden. Kein Freeze einer veralteten Schema-Kopie und keine Änderung der Backend-Validierung für Tokenersparnis.

## 4. Zusatzreferenz: bereits erhobene Token-Näherung

Vor Festlegung auf die LM-Studio-Logmessung wurde unter der zuvor erlaubten Näherungsmethode eine lokale Referenz berechnet: **tiktoken 0.12.0, cl100k_base**. Das Paket lag nur im ignorierten Analyseverzeichnis, nicht in den Integrationsabhängigkeiten. Diese Zahlen sind **keine Messung des Gemma-Tokenizers und keine LM-Studio-Prompt-Tokens**. Sie werden nur als reproduzierbare Zusatzreferenz behalten; für den strukturellen Vergleich oder spätere Abnahme ist keine separate Installation erforderlich.

| Profil | Ganze Werkzeugdefinitionen vorher | Entwurf | Ersparnis (Proxy-Tokens) | Anteil |
| --- | ---: | ---: | ---: | ---: |
| 6 Standard | 1372 | 994 | 378 | 27.6 % |
| 9 Einkauf | 2235 | 1571 | 664 | 29.7 % |
| 13 kuratierte | 3493 | 2662 | 831 | 23.8 % |
| 16 einschließlich Brücke | 3869 | 2996 | 873 | 22.6 % |

Der bereits existierende gemeinsame PROMPT wird derzeit allen freigegebenen Tools beigegeben. Die Zusatzreferenz zählt dafür 1150 Proxy-Tokens, der separate Entwurf 299. Einschließlich dieses Basisprompts (ohne Routerprompt, HA-eigene Tools, Historie, Chat-Template oder zusätzliche Menüwerkzeuge):

| Profil | Prompt + ganze Definitionen vorher | Entwurf | Ersparnis (Proxy-Tokens) | Anteil |
| --- | ---: | ---: | ---: | ---: |
| 6 Standard | 2522 | 1293 | 1229 | 48.7 % |
| 9 Einkauf | 3385 | 1870 | 1515 | 44.8 % |
| 13 kuratierte | 4643 | 2961 | 1682 | 36.2 % |
| 16 einschließlich Brücke | 5019 | 3295 | 1724 | 34.3 % |

Die Entwurfsvariante mit **13 bisherigen kuratierten plus 3 neuen Planungswerkzeugen** liegt in derselben Proxy-Methode bei **3515 statt 4643**, also **1128/24,3 % weniger** als der alte 13er-Umfang. Die neuen drei Tools allein kosten etwa 557 Proxy-Tokens, mit dem separaten Sync-Entwurf zusammen 681. Das zeigt, warum beschreibungsbezogene Bruttoersparnis und künftige Netto-Promptlast getrennt ausgewiesen werden müssen.

Das Ziel 30–50 % wird für die vollständigen reinen Definitionen je nach Profil nur teilweise erreicht (etwa 23–30 % Token-Näherung bzw. 25–32 % Bytes). Mit separat bewerteter Kurzprompt-Kürzung ergeben sich größere Bruttoeffekte. Typen/Sicherheitsregeln werden nicht entfernt, um eine Zielzahl zu erzwingen. Für volle Rezeptschemas bleibt struktureller Overhead; vollständige seltene Planungskontexte dürfen ausdrücklich größer sein.

## 5. Maßgebliche LM-Studio-Messung durch den Betreiber

Verbindlicher Vergleich nach Benutzervorgabe:

1. Tatsächliches Modell/GGUF, Quantisierung, LM-Studio-Version, Kontextfenster und relevante Inferenz-/Tool-/Templateeinstellungen festhalten. Identische HA-/Agent-/Routerkonfiguration und **identische Werkzeugfreigaben** verwenden.
2. Vor jeder Vergleichsserie Modell neu laden. Für jeden Messlauf eine neue Conversation ohne Historie starten, Eingabe exakt **„hallo“**.
3. LM-Studio-Serverlogs liefern die tatsächlichen Prompt-/Input-Tokens. Output-/Completion-Tokens getrennt halten. Initialisierung/Warmup nicht mit einem anderen Gespräch vergleichen; gegebenenfalls mehrere Läufe und Streuung berichten. Die dynamische Zeitzeile kann geringe Schwankungen erklären.
4. **A:** produktive Referenz 6604; zugehörigen produktiven Systemprompt und Konfigurationsstand sichern. **B:** nur optimierte Beschreibungen bei identischem Systemprompt/Tools/Modell. Der lokale aktuelle 1.4.3-Snapshot darf nicht ohne Gleichheitsprüfung als identischer produktiver Prompt angenommen werden. **C:** zusätzlicher Kurzprompt nach separater Verhaltensprüfung. Neue Menüwerkzeuge bleiben standardmäßig deaktiviert; nur nach bewusster Freigabe als eigene **D**-Variante mit ausgewiesenen neuen Freigaben messen; nicht deren Mehrkosten verstecken.
5. Der Betreiber hat A mit 6604 geliefert und liefert nach Implementierung B; diese Phase führt keine produktiven Modell-/HA-Änderungen oder Logabfragen aus. Einsparung = InputTokens_A − InputTokens_B, Prozent = 100 × Differenz / InputTokens_A. Null/fehlende Werte nicht als Einsparung ausgeben.

| Lauf | Gemma Prompt-Tokens | Stand |
| --- | ---: | --- |
| A: produktive Referenz, neue Conversation „hallo“ | **6604** | Vom Betreiber geliefert; vollständiger Prompt, genaue Konfiguration beim Folgetest identisch halten |
| B: nur Definitionen optimiert | noch nicht geliefert | Nach freigegebener Implementierung |
| C: zusätzlich Kurzprompt | noch nicht geliefert | Separate Qualitäts-/Messstufe |
| D: neue Menüwerkzeuge | noch nicht geliefert | Eigene Mehrkosten ausweisen |

Ein „hallo“-Benchmark belegt Grundlast, nicht Toolqualität oder die garantierte Abwesenheit schwerer Daten. Dafür zusätzlich Spy-/Integrationstests: keine Planungs-/Kalenderabfrage bei gewöhnlichen Befehlen; nach Planung keine schwere Historie im gewöhnlichen Gespräch. Eine bloß spätere Toolantwort verhindert keine Historienbelastung; isolierte Planungs-Conversation ist eigens zu prüfen.

## 6. Separate LLM-API und vereinfachte Planungswerkzeuge

[LLM_API_ARCHITECTURE_1.4.4.md](LLM_API_ARCHITECTURE_1.4.4.md) vergleicht die bisherige assist-Plattform mit einer optionalen eigenen Familien-API. HA 2026.10.2 und der geprüfte lokale Local-OpenAI-Stand unterstützen mehrere APIs. Beim Kombinieren werden Prompts zusammengefügt und Toolnamen zusätzlich namespaced. Legacy-Assist plus eine zweite Yuvomi-API kann dieselben Werkzeuge doppelt exponieren und die Last erhöhen. Eigene API allein kann unbenötigte Assist-Beiträge weglassen, spart aber bei denselben Werkzeugen nicht deren Definitionen und isoliert keine Historien. Für 1.4.4 keine eigene API implementieren; spätere bewusste Auswahl/Expositionsmigration separat freigeben und messen.

Die Aufwärmvereinfachung benötigt keine Werkzeuge zur Chargen-/Restbestands-/Verbrauchsverwaltung. Es bleiben **drei** getrennte kurze Planungswerkzeuge (Kontext, Speichern, Lesen) und optional **eines** für den getrennten Einkaufsablauf. Eine Zusammenlegung würde normale Planabfragen mit umfangreichem Kontext oder Schreibfähigkeit belasten. Keine bisherigen Werkzeuge entfernen, keine neuen standardmäßig aktivieren. Der bestehende Schemaentwurf mit source_date und extra_servings kann die einfache Zuordnung abbilden; kein zusätzliches Chargenwerkzeug und keine allgemeine Restenbuchhaltung. Der gebundene Kontext legt Mahlzeittyp/Quelle fest; mehrdeutige Quellslots werden abgewiesen.

## 7. Qualitätsabnahme mit Gemma 4 12B

Die Beschreibungskürzung wird nicht allein nach Tokens freigegeben. Gleiches deutschsprachiges Fallset vor/nach Optimierung: neue Artikel mit gültiger Kategorie, offene/abgehakte Artikel, „2 Tuben“ gegen „1 Packung“, note-only/clear, Mengen- plus Notizauftrag, mehrere Artikel, unbekanntes Werkzeug mit Bestätigung, Aufgabe/Termin inklusive Offset, Rezeptvariante, Resten, kaputte/unbekannte Metadaten und unklarer Schreibausgang. Werkzeugwahl, Argumentvollständigkeit, unnötige Rückfragen und falsche Erfolgsaussagen vergleichen. Kein Erfolg, wenn kürzere Texte weniger Tokens, aber mehr Fehlaufrufe produzieren.

Der Kurzprompt ist getrennt englisch entworfen, während der aktuelle Basisprompt deutsch ist; dieser Sprachwechsel ist ein zusätzlicher Evaluationsfaktor und kein bereits bewiesener Vorteil. Bei schlechterer Zuverlässigkeit deutschen Kurzprompt vorziehen oder einzelne Hinweise gezielt wieder verlängern. Sicherheitskritische Freigabe-/Bestätigungsprüfungen bleiben Backend-Aufgabe.

## 8. Reproduzierbarer Strukturcheck mit Python-Standardbibliothek

Im Repository-Stamm ausführen; schreibt nichts und benötigt keinen Tokenizer:

```python
import json
from pathlib import Path

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def contract(value):
    if isinstance(value, dict):
        return {k: contract(v) for k, v in value.items()
                if not (k == "description" and isinstance(v, str))}
    if isinstance(value, list):
        return [contract(v) for v in value]
    return value

before = json.loads(Path("docs/TOOL_DEFINITIONS_CURRENT_1.4.3.json").read_text(encoding="utf-8-sig"))
after = json.loads(Path("docs/TOOL_DEFINITIONS_DRAFT_1.4.4.json").read_text(encoding="utf-8-sig"))
assert contract(before) == contract(after)
assert len(before) == len(after) == 16
old = len(canonical(before).encode("utf-8"))
new = len(canonical(after).encode("utf-8"))
print(old, new, round(100 * (old - new) / old, 1))
# Erwartet: 18675 14083 24.6
```

Für Profilmessungen dieselben Namen aus den oben definierten Freigabeprofilen filtern, ganze Arrays erneut serialisieren. JSON-Hashes im Messbericht beziehen sich auf diese kanonischen Nutzdaten, nicht auf hübsch eingerückte Dateibytes. Die bereits erhobene optionale Proxy-Referenz lässt sich mit `tiktoken 0.12.0`, `get_encoding("cl100k_base").encode(text, disallowed_special=())` auf denselben Nutzdaten/Promptstrings nachrechnen. Für die endgültigen Zahlen ist jedoch die vom Betreiber gewählte LM-Studio-Logmessung maßgeblich.
