# Architektur 1.4.2

- `client.py`: bestehender MCP-Transport und feste REST-Leser; gleiche Token und Ursprungsprüfung.
- `shopping.py`: gemeinsame Einzel-/Sammelschemata, konservative Namensnormalisierung und Kategorievalidierung. Keine Klassifikation nach Produktregeln und keine historische Kategorieanreicherung.
- `shopping_api.py`: vollständige Listen-/Artikelabrufe sowie ausschließlich feste POST-/PATCH-Schreibpfade für Einkaufsartikel.
- `purchasing.py`: aktueller Yuvomi-Bestand als alleinige Entscheidungsgrundlage, Vorprüfung aller Artikel, Listensperren, gezielte Kategorienachlieferung, Reaktivierung und Mengenoperationen.
- `journal.py`: unabhängiges, atomar geschriebenes Ausführungsjournal mit interner Schema-Version 2 und verlustfreier Archivmigration aus Schema 1. Alte Namen/Kategorien in Transaktionsbelegen werden nur für Wiederholungsschutz und Zustandsprüfung verwendet, niemals als Produktkatalog.
- `persistence.py`: zwei HA-Store-Adapter (aktives Journal und einmaliges unveränderliches Altdatenarchiv).
- `journal_ui.py`: ausschließlich administrative lesende Prüfung unklarer Ausführungen.
- `runtime.py`: unveränderte Allowlist, Bestätigung unbekannter Werkzeuge und MCP-Aufgaben/Kalender. Beide Einkaufswerkzeuge setzen einen geladenen Einkaufsprozessor voraus; kein MCP-Fallback ohne Journal.
- `llm.py`: bestehende HA-LLM-Plattform, klare per-item-Kategorie- und Mengenanweisungen, keine zusätzlichen Modellaufrufe im Backend.

`catalog.py` und `catalog_ui.py` sind entfernt. Es gibt keine Katalogbeobachtung, Produktbestätigung, Synonymauflösung oder Importfunktion mehr. Der Config-Entry bleibt Version 1; seine gespeicherten Daten/Optionen werden nicht migriert oder ergänzt. Die Migration findet ausschließlich beim Laden des Integrationsstores statt.

REST: GET `/api/v1/shopping`, GET `/api/v1/shopping/{id}/items` (einschließlich abgehakter), GET `/api/v1/shopping/categories`, POST `/api/v1/shopping/{id}/items` mit Idempotency-Key, PATCH `/api/v1/shopping/items/{id}`. Die bestehenden optionalen Vorschläge nutzen weiterhin GET `/api/v1/shopping/suggestions?q=...`; sie sind keine Identitäts- oder dauerhafte Historienquelle für Schreibaktionen.
