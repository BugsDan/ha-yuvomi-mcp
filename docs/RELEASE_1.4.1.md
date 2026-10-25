# Yuvomi MCP 1.4.1 — 25.10.2026

Mengen bei Neuanlage, Reaktivierung und ausdrücklichem operation=set werden jetzt als Freitext unverändert an Yuvomi übergeben. Beispiele: „1 Flasche“, „2 Tuben“, „1 Packung“. Auch Unicode und äußerer Leerraum bleiben erhalten. Nichtleere Zeichenfolgen bis 256 Zeichen ohne Steuerzeichen sind weiterhin erforderlich.

Die numerische Prüfung findet ausschließlich bei increase statt: bekannte eindeutige Ausgangsmenge, positive Zusatzmenge und kompatible unterstützte Einheiten. Nicht interpretierbarer Freitext oder Packung gegenüber Tuben führt zu einer gezielten Rückfrage statt einer geratenen Addition.

ensure schützt die Menge offener Artikel weiterhin. Mayonnaise mit „1 Packung“ wird durch ensure mit „2 Tuben“ weder ersetzt noch dupliziert; quantity_unclear fordert Klärung. Ein ausdrücklich gewünschtes set setzt „2 Tuben“ auf derselben ID. Abgehakte Artikel werden mit der neuen Freitextmenge reaktiviert; ohne neue Mengenangabe wird die alte Menge wie bisher nicht übernommen.

Werkzeugschemata/-beschreibungen und Assist-Prompt sind angepasst. Produktname und Mengenangabe bleiben getrennte Felder. Kategorienlogik, Duplikatvermeidung, Listensperren, Idempotenz, persistentes Journal und Sicherheitsprüfungen bleiben erhalten. Keine Serveränderungen und keine produktive Installation durchgeführt.

## Prüfung

304 automatisierte Tests bestanden, 1 HA-spezifisches Testmodul mangels Home-Assistant-Laufzeit übersprungen. Ruff-Lint und Formatprüfung erfolgreich. Regressionen prüfen Einzel-/Sammelaufrufe, unveränderten Freitext, REST-JSON bei POST/PATCH, Mayonnaise-Konflikt, Reaktivierung, Grenzen/Steuerzeichen, weiterhin sichere Addition und Journal-Wiederholung nach Neustart. Bestehende Tests für Kategorien, Timeouts, Idempotenz, Aufgaben und Kalender bestehen weiterhin.

Keine Live-Abnahme mit HA, Yuvomi oder einem Sprachmodell. Die Integration kann nicht erkennen, ob ein mehrdeutiger Sprachwunsch einen Gesamtwert oder einen Zusatz meint; dafür muss der Assistent gezielt nachfragen. increase unterstützt weiterhin bewusst nur seine bisherigen numerischen Einheiten.

## Installation

HA-Backup einschließlich .storage erstellen, HA geordnet stoppen, bisherigen Integrationsordner sichern und durch custom_components/yuvomi_mcp aus dem ZIP ersetzen, HA starten und neue Assist-Unterhaltung öffnen. Bestehende Config Entries, Token, Freigaben und Schema-2-Journal bleiben erhalten. Beim Upgrade von 1.4.0 ist keine neue Migration nötig. Die Archivmigration für direkte Upgrades von 1.3.0 bleibt verfügbar.

Abnahme: neues Produkt mit „1 Flasche“ anlegen; offene Mayonnaise mit „1 Packung“ per ensure und „2 Tuben“ unverändert lassen; ausdrücklich set auf „2 Tuben“ durchführen; increase Packung/Tuben zurückweisen; abgehaktes Produkt mit Freitext auf derselben ID reaktivieren. Weitere Anleitung: ABNAHME.md.

Dateien: dist/yuvomi_mcp-1.4.1.zip (installierbar), dist/yuvomi_mcp-1.4.1-source.zip (mit Tests), dist/SHA256SUMS-1.4.1.txt.
