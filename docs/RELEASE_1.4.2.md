# Yuvomi MCP 1.4.2 – erste öffentliche Version

Noch nicht veröffentlicht. Diese Baseline enthält die nachfolgend beschriebenen Funktionen; ältere Versionsnummern waren interne Entwicklungsstände. Keine produktive Installation durch die Veröffentlichungsvorbereitung.

## Mengenlogik

ensure und increase verarbeiten Einkaufswünsche gleich: neue Artikel mit angegebener Menge oder „1“ erstellen; offene Artikel auf bestehender ID ergänzen; abgehakte Artikel mit der gewünschten neuen Menge oder „1“ reaktivieren, niemals zur alten Menge addieren. set bleibt eine ausdrücklich gewünschte absolute Korrektur.

Sicher kompatible Mengen werden addiert. Ohne Mengenangabe wird +1 einer sicher erkannten aktuellen Einheit verwendet, z.B. 2 Packungen → 3 Packungen. Bei unbekannter Basis oder nicht kompatibler/parsebarer Menge wird die neue Angabe übernommen statt nachgefragt. Es gibt keine geratene Einheitenumrechnung. Eine explizite einheitenlose Angabe ist nur mit einheitenloser Basis kompatibel; bei unbekannter Einheit ist der ausgelassene Default „1“.

Freitext bleibt bei Neuanlage, Reaktivierung, Ersatz und set unverändert. Unterstützte arithmetische Einheiten umfassen zusätzlich Flasche/Flaschen, Tube/Tuben und Einheit/Einheiten. Zahlen und positive Dezimalmengen mit den bisherigen Einheiten bleiben unterstützt. Leere/zu lange/steuerzeichenhaltige Werte werden weiterhin sicher abgewiesen.

Ergebnisse ergänzen old_quantity, new_quantity, action, replacement_reason und quantity_defaulted. status und quantity bleiben verfügbar. Bei Addition action/status increased, bei Reaktivierung reactivated, bei nicht sicher addierbarer Menge replaced. Für set bleibt status quantity_set kompatibel, action replaced mit reason explicit_set; unveränderter Zielwert meldet already_present/unchanged. Keine Addition behaupten, wenn ersetzt wurde.

Beispiele:

- Chips 1 Packung + 2 Packungen → 3 Packungen, increased.
- Mayonnaise 1 Packung + 2 Tuben → 2 Tuben, replaced.
- Abgehakte Mayonnaise 99 Packungen + gewünschte 2 Tuben → reactivated, neue Menge 2 Tuben.
- Neues Produkt ohne Mengenangabe → created, Menge 1.

## Kategorien und Prompt

Bestehende aktuelle Yuvomi-Kategorien bleiben maßgeblich. Beschreibungen beider Werkzeuge weisen ausdrücklich an, für jedes neue Produkt schon beim ersten Aufruf die fachlich passendste tatsächlich vorhandene Kategorie mitzugeben. list_shopping_categories vorher nutzen, sofern Namen nicht im Kontext bekannt sind. Keine erfundenen Kategorien, Sonstiges nur wenn keine spezifische Kategorie passt. Fehlende Kategorien bleiben gezielt nachlieferbar; keine festen Produktregeln und kein Backend-LLM.

Der integrierte Assist-Prompt ist angepasst. Hinweise für einen eventuell zentral gepflegten Router-/Modellprompt: PROMPT_1.4.2.md. Eine produktive Promptänderung wurde nicht vorgenommen.

## Wiederholungsschutz

Identische Request-IDs werden aus dem persistenten Journal wiedergegeben und nicht erneut addiert, auch nach Neustart. Zusätzlich werden kurzfristige identische Produkt-/Mengenabsichten desselben Aufrufers auf derselben Liste innerhalb von 120 Sekunden als replayed zurückgegeben, wenn der quittierte offene Zielzustand noch besteht. ensure/increase, normalisierte numerische Schreibweisen und Einzel-/Sammelwerkzeug teilen diese zusätzliche Prüfung. Neue Retry-IDs werden ebenfalls im Journal vermerkt und verlängern das ursprüngliche Zeitfenster nicht. replayed bedeutet ausdrücklich: keine weitere Addition ausgeführt.

Ohne stabile durchgereichte Alexa-Request-ID ist eine echte identische zweite Bestellung nicht zuverlässig von einer Wiederholung mit neuer ID unterscheidbar. Im Zeitfenster kann daher eine absichtlich identische Nachbestellung unterdrückt werden; explizite absolute Korrektur über set ist möglich. Nach Ablauf des Fensters sind neue IDs neue Wünsche. Ein erneut abgehakter oder gelöschter Artikel gilt bei neuer ID als neuer Einkaufszyklus. Andere Aufruferkontexte/Clients teilen diese Heuristik nicht. Keine unbegrenzte Erkennung beliebiger neuer IDs und keine globale Exactly-once-Garantie.

Hat sich die Menge/Identität eines weiterhin offenen Ziels zwischenzeitlich geändert, wird eine erkannte mögliche Wiederholung ohne weitere Addition mit execution_unconfirmed gestoppt. Manuelle Kategorieänderungen bleiben erhalten. prepared/unknown sperren die Liste weiterhin über Neustarts. POST-Idempotency-Key, Listensperren, erneute PATCH-Bestandsprüfung und lesende Ausführungsprüfung bleiben erhalten. Mehrdeutige Produkte und unklare Schreibausgänge werden nicht automatisch geraten oder erneut geschrieben.

## Tests

Die CI führt die vollständige Suite unter Python 3.12 und unter Linux/Python 3.14 mit echtem HA 2026.10.2 aus. HACS und hassfest sind eigene Pflichtprüfungen vor dem Release. Ergebnisse des jeweiligen Commits: [GitHub Actions](https://github.com/BugsDan/ha-yuvomi-mcp/actions/workflows/tests.yml). Alle vier Jobs müssen für den zu taggenden Commit erfolgreich sein.

Die beiden Fehler aus dem ersten HA-Lauf (Run 40206049922) sind im Testaufbau korrigiert: korrekter Paketkontext beim isolierten Import und synchroner Mock für redact. Assertions, Testumfang und produktive Funktionalität bleiben erhalten. Regressionen decken Mengen, Freitext, Kategorien, Reaktivierung, Parallelaufrufe, Retries, Neustarts, Journalzustände und Aufgaben-/Kalenderwerkzeuge ab.

Keine Live-Abnahme mit Alexa, Gemma oder produktivem HA/Yuvomi. Die HACS-Installation auf einer echten Betreiberinstallation bleibt gesondert zu prüfen.

## Installation und Abnahme

Voraussetzungen: HA ab 2026.10.2, Yuvomi 2.79.0 und Token mit passenden Rechten. Nach Veröffentlichung HACS als benutzerdefiniertes Repository verwenden; siehe [GitHub/HACS](GITHUB_HACS.md). Für manuelle Installation nur custom_components/yuvomi_mcp aus dem Installations-ZIP übernehmen. Anschließend HA neu starten, Integration einrichten und gewünschte Werkzeuge explizit freigeben.

Bereits manuell eingerichtete Integrationen vor der Übernahme vollständig einschließlich .storage sichern. Config Entries, Tokens, Freigaben und Journale behalten; nichts löschen oder neu anlegen. Technische Altzustände sind separat in [Speicherkompatibilität](STORAGE_COMPATIBILITY.md) beschrieben.

Abnahme auf Testliste: Neuanlage ohne Menge = 1; Chips 1 Packung plus 2 Packungen = 3; Mayonnaise 1 Packung plus 2 Tuben = 2 Tuben mit replaced; abgehakte ID mit neuer Menge reaktivieren; exakt gleichen Vorgang und kurzfristigen Retry erneut aufrufen ohne weitere Addition; explizites set korrigiert den Zielwert. Weitere Details: ABNAHME.md.

Release-Dateien: dist/yuvomi_mcp-1.4.2.zip, dist/yuvomi_mcp-1.4.2-source.zip, dist/SHA256SUMS-1.4.2.txt. Keine produktive Installation oder Änderung am Yuvomi-Server.

## Ausblick

[Notizfunktionen für 1.4.3](PLAN_1.4.3.md) sind nur spezifiziert, nicht implementiert. Die Version bleibt 1.4.2.
