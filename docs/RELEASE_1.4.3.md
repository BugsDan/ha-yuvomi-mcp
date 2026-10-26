# Yuvomi MCP 1.4.3 – lokaler Entwicklungsstand

Noch nicht veröffentlicht. Einkaufsnotizen und Yuvomi-Rezeptpflege; Menüplanung wird ausschließlich spezifiziert.

## Funktionen

- Einzel-/Sammelwerkzeug: optional note und note_mode append/replace/clear. Ausgelassen erhält Notizen. operation=note bearbeitet ausschließlich Notizen bestehender Artikel, ohne Menge, Kategorie oder Status zu ändern.
- Eng begrenzte, ausdrücklich freizugebende Werkzeuge list_recipes, get_recipe, create_recipe und update_recipe. Yuvomi bleibt einzige Rezeptquelle. Neue Rezepte als lunch/Mittagessen, Basisportionen standardmäßig 4.
- Strukturierter Menümetadatenblock in den Rezeptnotizen; vorhandener Freitext bleibt erhalten, Bewertung wird als KI-Vorschlag geführt. Keine Bilder oder Links über das Werkzeug schreiben.
- Persistente Rezept-Schreibbelege und unklare Ausgänge im bestehenden Journal; kein paralleler Rezeptkatalog. Einkaufssperren und Rezeptschreibsperren sind getrennt. Alte Journalvorgänge bleiben erhalten.

## Prüfung und Grenzen

Lokale vollständige Suite: 452 Tests bestanden, ein HA-spezifisches Modul auf Windows/Python 3.12 übersprungen. Ruff-Lint, Format, offizielle HA-API-Verträge und Publikationsprüfung erfolgreich. Neue HA-Plattform-/Optionsprüfungen sind ergänzt, hier aber nicht ausgeführt.

Tests und Abnahme siehe TEST_REPORT_1.4.3.md. Der echte HA-Testjob, HACS und hassfest werden ohne Push noch nicht auf GitHub ausgeführt. Keine produktiven Verbindungen oder Änderungen.

Yuvomi 2.79.0 besitzt kein Basisportionsfeld und keinen atomaren bedingten Rezept-Updatepfad. Portionen werden nur in notes gespeichert, nicht automatisch skaliert. Rezept-PUT ersetzt Zutatenzeilen; deren IDs können wechseln. Namen, Mengen, Kategorien, Links, Bild und fremde Notizen werden erhalten; bestehende Pantry-Zuordnungen bleiben serverseitig namensbasiert. Vor PUT erfolgt ein erneuter Vergleich; externe Änderungen im verbleibenden Zeitfenster sind nicht vollständig ausschließbar.

Kein Planungswerkzeug, Kalenderzugriff, Vorratsabgleich oder Zutatenübertrag in diesem Release. Anforderungen: MENU_PLANNING.md.

## Lokale Installation und Rückweg

Vor einer späteren Installation vollständiges HA-Backup einschließlich .storage und Integrationsordner erstellen, Yuvomi separat sichern. Nur Codeordner ersetzen, Config Entry behalten, HA neu starten, neue Werkzeuge ausdrücklich freigeben. Ein zurückgespielter älterer Code kann neue Rezept-PUT-Belege nicht lesen und sperrt dann Schreibaktionen sicher. Kein blindes Downgrade und keine Journalbereinigung; für Rückwege konsistentes Backup verwenden. Offene Ausführungen ausschließlich über die Integrationsoptionen lesend prüfen.

Noch kein Commit, Push, Tag, Release oder produktive Installation für 1.4.3.
