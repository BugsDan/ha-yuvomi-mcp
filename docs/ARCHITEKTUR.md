# Architektur 1.4.3

- `client.py`: bestehender MCP-Transport und feste REST-Leser; gleiche Token und Ursprungsprüfung.
- `shopping.py`: gemeinsame Einzel-/Sammelschemata, konservative Namensnormalisierung und Kategorievalidierung. Keine Klassifikation nach Produktregeln und keine historische Kategorieanreicherung.
- `shopping_api.py`: vollständige Listen-/Artikelabrufe sowie ausschließlich feste POST-/PATCH-Schreibpfade für Einkaufsartikel.
- `purchasing.py`: aktueller Yuvomi-Bestand als alleinige Entscheidungsgrundlage, Vorprüfung aller Artikel, Listensperren, gezielte Kategorienachlieferung, Reaktivierung und Mengenoperationen.
- `journal.py`: unabhängiges, atomar geschriebenes Ausführungsjournal mit interner Schema-Version 2 und verlustfreier Archivmigration aus Schema 1. Alte Namen/Kategorien in Transaktionsbelegen werden nur für Wiederholungsschutz und Zustandsprüfung verwendet, niemals als Produktkatalog.
- `persistence.py`: zwei HA-Store-Adapter (aktives Journal und einmaliges unveränderliches Altdatenarchiv).
- `journal_ui.py`: ausschließlich administrative lesende Prüfung unklarer Ausführungen.
- `runtime.py`: unveränderte Allowlist, Bestätigung unbekannter Werkzeuge und MCP-Aufgaben/Kalender. Beide Einkaufswerkzeuge setzen einen geladenen Einkaufsprozessor voraus; kein MCP-Fallback ohne Journal.
- `llm.py`: bestehende HA-LLM-Plattform, klare per-item-Kategorie- und Mengenanweisungen, keine zusätzlichen Modellaufrufe im Backend.

Es gibt keine aktiven Produktkatalogmodule. Es gibt keine Katalogbeobachtung, Produktbestätigung, Synonymauflösung oder Importfunktion mehr. Der Config-Entry bleibt Version 1; seine gespeicherten Daten/Optionen werden nicht migriert oder ergänzt. Der bestehende Speicherkompatibilitätsadapter bleibt zum Schutz früherer manueller Installationen erhalten; siehe [Speicherkompatibilität](STORAGE_COMPATIBILITY.md).

REST: GET `/api/v1/shopping`, GET `/api/v1/shopping/{id}/items` (einschließlich abgehakter), GET `/api/v1/shopping/categories`, POST `/api/v1/shopping/{id}/items` mit Idempotency-Key, PATCH `/api/v1/shopping/items/{id}`. Die bestehenden optionalen Vorschläge nutzen weiterhin GET `/api/v1/shopping/suggestions?q=...`; sie sind keine Identitäts- oder dauerhafte Historienquelle für Schreibaktionen.

## Notizen und Rezepte

notes.py enthält ausschließlich explizite Textoperationen. shopping.py/purchasing.py verwenden dieselbe persistente Einkaufsverarbeitung für normale Aufträge und reine Notizänderungen. recipes.py kapselt Schema, Metadatenvertrag und feste Rezept-REST-Pfade; recipe_engine.py serialisiert Rezeptschreiben und führt Transaktionsbelege im gemeinsamen Journal. GET liest Yuvomi; kein Rezeptkatalog oder aktiver Metadaten-Store in HA. RecipeAPI verwendet denselben begrenzten, redirectfreien Transport wie ShoppingAPI.

Neue Belege sind durch resource=recipes getrennt, alte Belege ohne resource bleiben Einkaufsbelege. Schema 2 und alte Vorgänge bleiben erhalten. Rezept-PUT ist nur für Rezeptbelege erlaubt; Einkaufs-PUT bleibt abgewiesen. Ein Downgrade auf 1.4.2 kann solche neuen Belege sicher ablehnen, daher vollständige Sicherung und keine blinde Journalbereinigung.

Planung ist ausschließlich in MENU_PLANNING.md spezifiziert, keine Planungskonfiguration oder Kalender-/Vorratsabfrage implementiert.
