# Yuvomi MCP 1.4.5

Stabile Version mit vereinfachter Familien- und Wochenplanung. Installation und Aktivierung erfolgen ausschliesslich durch den Betreiber.

- Neue, auswählbare Familienprofile und Standardwoche ohne JSON-Eingabe.
- Backend berechnet Frisch-, Mitnahme- und Gesamtportionen sowie skalierte Zutaten.
- Nur Kochtage erzeugen Yuvomi-Menüs. Mitnahmeportionen bleiben eindeutig am Quellgericht dokumentiert.
- Kompakter Werkzeugvertrag mit optionaler Quellenauswahl, Wochenabweichungen und schreibfreiem Prüfmodus.
- Explizite Rezeptwünsche bei Tagesänderungen übersteuern Geschmack, Wiederholung und Zeitlimits; technische Sicherheit und Mitnahme-Eignung bleiben verpflichtend.
- Mahlzeitname mit Portionshinweis, unverändertes Originalrezept und reale Yuvomi-Kochidentitäten.
- Journal, Idempotenz, unklare Schreibsperren und Reconciliation bleiben erhalten.

Die alte Planungskonfiguration wird nicht automatisch migriert. Vor neuen Planungsaktionen die Standardwoche über die Integrationsoptionen neu einrichten und speichern. Bis dahin bleiben neue öffentliche Planungsaktionen gesperrt; Menüabfragen und Journalprüfung bleiben möglich. Bestehende Yuvomi-Menüs werden nicht bereinigt oder verändert. Alte RC3-Aufwärmeinträge werden erkannt und bei betroffenen Quellenänderungen sicher blockiert.

Einrichtung, Vertrag, Grenzen und Abnahme: [SETUP_1.4.5.md](https://github.com/BugsDan/ha-yuvomi-mcp/blob/v1.4.5/docs/SETUP_1.4.5.md).
Lokale und GitHub-CI-Prüfbelege: [VALIDATION_1.4.5.md](https://github.com/BugsDan/ha-yuvomi-mcp/blob/v1.4.5/docs/VALIDATION_1.4.5.md).

CI-Abnahme: 602 Unit-/Regressionstests bestanden (zwei HA-Testmodule nur im separaten HA-Job); mit echtem Home Assistant 2026.10.2 unter Python 3.14: 631 bestanden, keine übersprungen. Ruff, Formatprüfung, Repository-/Paketprüfung, HACS, hassfest und Gitleaks erfolgreich. Die Veröffentlichung durchläuft diese Prüfungen erneut. Keine produktive Installation oder Datenänderung durch die Veröffentlichung.
