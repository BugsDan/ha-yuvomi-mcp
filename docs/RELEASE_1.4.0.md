# Yuvomi MCP 1.4.0 — 25.10.2026

## Ergebnis

Yuvomi 2.79.0 ist die einzige aktive Quelle für Produkte, Kategorien, Mengen und Einkaufsstatus. Der HA-Produktkatalog samt Synonymen, Produktbestätigung, Beobachtung und Pflege-/Import-/Exportoptionen ist entfernt. Der vollständige alte Store wird vor der Migration unverändert archiviert; alle Transaktionen des Journals bleiben im neuen unabhängigen Speicher erhalten.

Einzel- und Sammelwerkzeug verwenden dieselbe Logik: vollständiger Listenbestand einschließlich abgehakter Artikel, konservative vollständige Namensgleichheit, keine Marken- oder Größenersetzung, aktuelle Yuvomi-Kategorie vor Modellvorschlag, offene Artikel nicht duplizieren, abgehakte IDs reaktivieren. Nach Löschen gibt es bewusst kein HA-Produktgedächtnis.

Neue Produkte benötigen eine gültige KI-Kategorie. Bei fehlender Kategorie meldet `category_required` gezielt Artikel und verfügbare Kategorien. Die Sammelvorprüfung meldet sämtliche betroffenen Artikel, bevor etwas geschrieben wird. Kein stiller Sonstiges-Fallback. Beschreibungen und JSON-Schemata erläutern category innerhalb jedes items[]-Objekts.

Mengen: standardmäßig ensure; ausdrückliche Gesamtmenge mit operation=set; sichere Addition mit increase. Unklare Ausgangsmengen/Einheiten werden zurückgewiesen. Alte Mengen abgehakter Artikel werden nicht kopiert. Weitere Metadaten bleiben erhalten.

Unverändert bzw. angepasst erhalten: Serialisierung je Liste, vorbereiteter persistenter Schreibbeleg, Idempotency-Key bei POST, Sperre unklarer Ausgänge über Neustarts, lesende Zustandsprüfung und konservativer Schutz gleicher Zusatzmengen. Ohne geladenen Einkaufsprozessor/Journal gibt es keinen MCP-Schreibfallback. Aufgaben, Kalender, bestehende Freigaben, Token und Config Entries bleiben erhalten. Kein generisches REST-Schreibwerkzeug und keine Serveränderung.

## Lokale Prüfung

- 247 Tests bestanden; 1 HA-spezifisches Testmodul übersprungen (Windows/Python 3.12 ohne Home Assistant).
- 219 Tests des bestehenden Assist Routers bestanden, mit dessen eigener Testumgebung. Routerquellcode unverändert.
- Ruff-Lint und Formatprüfung erfolgreich.
- Echte lokale HTTP-Testserver prüfen MCP-JSON/SSE für unveränderte Werkzeuge sowie Einkaufs-REST, Unicode, Kategorienachlieferung, Idempotency-Key und REST/MCP-Trennung. Keine Verbindung zur produktiven Installation.
- Regressionen für unterschiedliche Produkt-/Markennamen, vollständige Normalisierung, vorhandene/abgehakte Artikel, Kategorieänderungen, absolute/additive Mengen, Sammelvorprüfung, parallele Aufrufe, Wiederholungen, Dateispeicher-Wiederherstellung und persistente unklare Ausgänge.
- Migrationsprüfungen: alle Journalzustände unverändert, vollständiges Unicode-Archiv, fehlerhafte oder nicht bestätigte Archivierung, fehlender Archivadapter, Konfliktarchiv, unterbrochene Migration und sicherer Wiederanlauf. Alte Produktdaten werden nicht aktiv verwendet.
- HA-Options-/Store-Adaptertests sind im übersprungenen Modul aktualisiert und ergänzt; für Linux/Python >=3.14.2 mit HA 2026.10.2 vorbereitet. Sie wurden hier nicht ausgeführt.

## Verbleibende Grenzen

Keine Live-Abnahme mit Gemma, OpenAI, Gemini, Alexa oder produktivem HA. Kein Versprechen, dass ein Modell stets alle erforderlichen Felder liefert. Ein fehlendes category führt daher bewusst zu einem korrigierbaren Werkzeugfehler, möglicherweise mit einer weiteren Modellrunde. Die Integration selbst ruft kein zusätzliches LLM auf.

Die Sperre wirkt innerhalb dieser Integrationsinstanz. Andere Clients können zwischen Bestandsprüfung und Schreiben eingreifen; vor PATCH wird erneut geprüft, aber keine globale atomare Transaktion/Exactly-once-Garantie behauptet. Sammelaufrufe sind vorgeprüft, jedoch keine serverseitige Transaktion; bestätigte Teilaktionen werden bei späteren Fehlern nicht zurückgerollt. Nicht eindeutig auflösbare Journale bleiben sicher gesperrt.

Schema 2 ist nicht direkt mit 1.3.0 rückwärtskompatibel. Vor Installation vollständiges HA-Backup erstellen; das unveränderte Altarchiv ist keine laufende Sicherung neuer Journaleinträge. Rückweg und Abnahme siehe ABNAHME.md.

## Dateien

- `dist/yuvomi_mcp-1.4.0.zip`: installierbare Integration unter custom_components/yuvomi_mcp plus Dokumentation.
- `dist/yuvomi_mcp-1.4.0-source.zip`: zusätzlich Quelltests, Build-Werkzeuge und Linux-CI-Konfiguration.
- `dist/SHA256SUMS-1.4.0.txt`: SHA-256 beider ZIP-Dateien.

Keine automatische Installation, Aktivierung, produktive Datenänderung oder Anpassung am Assist Router durchgeführt.
