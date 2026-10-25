# Änderungen

## 1.4.2 - 25.10.2026

- Neue/offene/abgehakte Mengenlogik: Default 1, offene Artikel über ensure/increase addieren, abgehakte ID mit neuer Menge reaktivieren, explizites set für absolute Korrekturen.
- Inkompatible oder nicht sicher addierbare Mengen ohne Mengenrückfrage durch den neuen Freitext ersetzen und transparent als replaced melden. Flaschen, Tuben und Einheiten rechnerisch normalisiert.
- Ergebnisse mit old_quantity, new_quantity, action und replacement_reason für klare Sprachausgabe erweitert.
- Persistenter Wiederholungsschutz auch für ensure, Ersatz, Defaultmengen und neue kurzfristige Retry-IDs desselben Aufrufers; keine automatische erneute Addition. Grenzen der 120-Sekunden-Heuristik dokumentiert.
- Werkzeugbeschreibungen priorisieren gültige fachliche Kategorien bereits im ersten Aufruf; Sonstiges nur echte Auffangkategorie. Systemprompt-Hinweise dokumentiert.
- Schema 2, alte Journalzustände, Kategorienlogik, ID-Wiederverwendung und Freigaben erhalten. Keine produktive Installation.

## 1.4.1 - 25.10.2026

- Mengen bei Neuanlage, Reaktivierung und explizitem set als Freitext unverändert übernehmen; kein Rechenparser und kein Entfernen äußeren Leerraums. Nichtleere Strings bis 256 Zeichen ohne Steuerzeichen bleiben Voraussetzung.
- Nur increase verlangt weiterhin sichere Mengenarithmetik mit kompatiblen Einheiten. ensure überschreibt keine abweichenden Mengen offener Artikel.
- Gemeinsame Werkzeugbeschreibungen und Assist-Prompt erläutern Freitext und den Fall „2 Tuben Mayonnaise“ gegenüber „1 Packung“.
- Schema 2, Journal, Kategorien, Duplikatvermeidung, Idempotenz und Freigaben unverändert; keine neue Datenmigration.
- Regressionen für Einzel-/Sammelwerkzeug, Reaktivierung, Mengenschutz, REST-JSON und Neustart-Wiederholung ergänzt.

## 1.4.0 - 25.10.2026

- HA-Produktkatalog, Synonyme, Kategoriebeobachtung, Bestätigung und Katalogoptionen entfernt; Yuvomi ist alleinige Quelle.
- Vollständiges Schema-1-Archiv vor Migration, unabhängiges Schema-2-Journal mit unveränderten offenen und unklaren Vorgängen.
- Aktuelle Yuvomi-Kategorien haben Vorrang; neue Artikel ohne KI-Kategorie verlangen gezielte Nachlieferung mit gültigen Namen. Kein stiller Sonstiges-Fallback.
- Gemeinsame beschriebene Parameter für Einzel- und Sammelwerkzeug; absolute Gesamtmenge über operation=set, sichere Zusatzmenge über increase.
- REST-Bestand einschließlich abgehakter Artikel, bestehende IDs, Listensperren, POST-Idempotenz und dauerhafte Schreibbarrieren erhalten. Kein MCP-Einkaufsfallback ohne Journal.
- Config Entries, Token, Freigaben und sonstige MCP-Werkzeuge unverändert. Keine Yuvomi-Serveränderung.
- Abnahme, Testgrenzen und Rückweg siehe RELEASE_1.4.0.md und ABNAHME.md.

## 1.3.0 - 24.10.2026

- Persistenter, atomarer HA-Store für Produktwissen, Revisionen, Vorschläge, Beobachtungen und Ausführungsjournal. Keine zusätzliche Datenbank.
- Produktpflege und Bestätigung über Integrationsoptionen, JSON-Export sowie validierter Import mit Vorschau ohne Überschreiben bestehender IDs.
- Einkaufsaktionen über feste Yuvomi-REST-Pfade: voller Bestand, offene Artikel wiederverwenden, eindeutig abgehakte reaktivieren, neue Artikel mit Katalogkategorie anlegen.
- Bestätigte Zuordnungen gegen KI-Überschreiben geschützt; fremde Änderungen nur als Vorschläge. Keine automatisch bestätigte Historie.
- Persistente Sperre unklarer Ausgänge, POST-Idempotenzschlüssel, Serialisierung je Liste und lesende Ausführungsprüfung. Kein automatischer Retry.
- Optionales add_shopping_items für bis zu 20 Artikel. Keine automatische Freigabe. Sichere Mengenaddition bei gleichen Einheiten, konservativer Wiederholungsschutz und Rückfragen bei Unsicherheit.
- Config Entry, Token und gespeicherte Allowlist bleiben erhalten. Aufgaben/Kalender weiter über MCP; unbekannte Werkzeuge weiter bestätigungspflichtig.
- Lokale Tests und Einschränkungen siehe RELEASE_1.3.0.md und ABNAHME.md. Phase 4 folgt separat.


## 1.2.1 - 23.10.2026

- Explizite Kategorien vor MCP zwingend gegen die aktuellen Yuvomi-Kategorien prüfen, auch ohne separat freigegebenes LLM-Lesewerkzeug. Exakte Treffer unverändert, eindeutige Schreib-/Unicodevarianten auf vorhandene Originalnamen korrigiert.
- Ungültige oder mehrdeutige Kategorien blockieren und gültige Namen als Werkzeugfehler zurückgeben. Fehlgeschlagene Pflichtprüfung blockiert die Speicherung. Keine neuen Kategorien erstellen.
- Fehlende Kategorien behalten die bisherige optionale Übernahme aus exakt passenden Einkaufsartikeln. Mengen und Allowlist unverändert; keine Migration oder Yuvomi-Änderung.
- 171 lokale Tests bestanden, darunter sechs TCP-Tests; HA-Testmodul mangels Laufzeit übersprungen.


## 1.2.0 - 22.10.2026

- Lokale HA-Lesewerkzeuge für Kategorien und Artikelvorschläge über bestehende REST-Endpunkte; gleicher Token und Server-Ursprung, keine Yuvomi-Änderung erforderlich.
- Beide Leser nur nach expliziter Freigabe ohne Aktionsbestätigung. Sechs Standardfreigaben und Bestätigung unbekannter Werkzeuge bleiben erhalten.
- Assist-Prompt zur Kategoriepriorität. Fehlende Kategorien werden bei Freigabe beider Leser aus exakt passenden gültigen Vorschlägen ergänzt; explizite Kategorien und Mengen bleiben erhalten.
- Begrenzte asynchrone GETs ohne Weiterleitungen oder Retries. REST-Fehler verhindern keine ursprünglichen MCP-Schreibaufrufe.
- 131 lokale Regressionstests bestanden, einschließlich fünf echter lokaler TCP-Tests. HA-Testmodul mangels HA-Laufzeit übersprungen; Live-LLM-Abnahme offen.


## 1.1.0 - 22.10.2026

- `list_shopping_categories` als bekanntes Lesewerkzeug erkannt: nach ausdrücklicher Freigabe ohne zusätzliche Aktionsbestätigung ausführbar.
- Korrekte Annotationen: rein lesend, idempotent, nicht destruktiv; keine Schreib-Deduplizierung für Kategorienabrufe.
- Initiale Freigaben und gespeicherte Auswahl unverändert. Unbekannte und generische Werkzeuge bleiben weiterhin freigabe- und bestätigungspflichtig.
- Regressionstests für Freigabe, Ausführung, wiederholte Abrufe, Widerruf, Unload, unbekannte Werkzeuge und Versionskonsistenz ergänzt. HA-spezifische Annotationstests liegen für die Linux/HA-Testumgebung bei.
- Release-Dateinamen werden aus der Manifest-Version abgeleitet; versionierte SHA-256-Prüfsummen werden mitgeliefert.

## 1.0.0

Erste lokale Implementierung der Yuvomi-MCP-Integration für die Assist-LLM-API von Home Assistant Core 2026.10.2.
