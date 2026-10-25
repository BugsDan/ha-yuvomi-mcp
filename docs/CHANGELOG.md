# Änderungen

## 1.4.2 – erste öffentliche Version

Release noch nicht veröffentlicht. Ältere Nummern bezeichneten interne Entwicklungsstände und sind keine öffentlichen Releases dieses Repositories.

- Native Home-Assistant-LLM-Werkzeuge für Yuvomi 2.79.0; ausdrückliche Werkzeugfreigaben und Bestätigung unbekannter Werkzeuge.
- Yuvomi als einzige Quelle für Produkte, Kategorien, Mengen und Status. Keine zweite Produktdatenbank oder Synonymverwaltung in HA.
- Gemeinsame Einzel-/Sammelverarbeitung mit vollständigem REST-Bestand, eindeutiger Produktidentität und Reaktivierung bestehender IDs.
- Bestehende Yuvomi-Kategorie hat Vorrang. Neue Produkte benötigen eine gültige KI-Kategorie; gezielte Nachlieferung bei fehlender Kategorie.
- Mengen: Default 1, offene Artikel ergänzen, abgehakte mit neuer Menge reaktivieren, explizites set als absolute Korrektur. Nicht addierbare Freitextmengen transparent ersetzen.
- Persistentes Journal, Listensperren, POST-Idempotenz, Neustartwiederherstellung und konservativer Wiederholungsschutz für kurzfristige Retry-IDs.
- HACS-Metadaten, lokale Brand-Grafik, Publikationsprüfung und CI mit Unit-Tests, echtem HA 2026.10.2, HACS und hassfest. Tag-Workflow erzeugt nur einen Release-Entwurf.
- HA-Testaufbau korrigiert: isoliertes Setup-Modul verwendet den echten Paketkontext; synchrone redact-Methode wird mit Mock simuliert. Keine Testaussage entfernt und keine Laufzeitfunktion verändert.
- Öffentliche Dokumentation auf Erstinstallation ausgerichtet. Bestehende Journale und benötigte Speicherkompatibilität bleiben unverändert erhalten.

Geplante Notizfunktionen für 1.4.3: [Anforderungen](PLAN_1.4.3.md). Noch keine Implementierung oder Versionserhöhung.
