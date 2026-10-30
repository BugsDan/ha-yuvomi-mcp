# Yuvomi MCP 1.4.5 – lokaler Entwicklungskandidat

Noch nicht veröffentlicht oder produktiv freigegeben. Keine Tags oder Releases geändert.

- Neue, auswählbare Familienprofile und Standardwoche ohne JSON-Eingabe.
- Backend berechnet Frisch-, Mitnahme- und Gesamtportionen sowie skalierte Zutaten.
- Nur Kochtage erzeugen Yuvomi-Menüs. Mitnahmeportionen bleiben eindeutig am Quellgericht dokumentiert.
- Kompakter Werkzeugvertrag mit optionaler Quellenauswahl, Wochenabweichungen und schreibfreiem Prüfmodus.
- Explizite Rezeptwünsche bei Tagesänderungen übersteuern Geschmack, Wiederholung und Zeitlimits; technische Sicherheit und Mitnahme-Eignung bleiben verpflichtend.
- Mahlzeitname mit Portionshinweis, unverändertes Originalrezept und reale Yuvomi-Kochidentitäten.
- Journal, Idempotenz, unklare Schreibsperren und Reconciliation bleiben erhalten.

Die alte Planungskonfiguration wird nicht automatisch migriert. Vor neuen Planungsaktionen die Standardwoche über die Integrationsoptionen neu einrichten und speichern. Bis dahin bleiben neue öffentliche Planungsaktionen gesperrt; Menüabfragen und Journalprüfung bleiben möglich. Bestehende Yuvomi-Menüs werden nicht bereinigt oder verändert. Alte RC3-Aufwärmeinträge werden erkannt und bei betroffenen Quellenänderungen sicher blockiert.

Einrichtung, Vertrag, Grenzen und Abnahme: [SETUP_1.4.5.md](SETUP_1.4.5.md).
Lokale Prüfbelege: [VALIDATION_1.4.5.md](VALIDATION_1.4.5.md).
