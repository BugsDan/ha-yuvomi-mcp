# Release 1.3.0 – 24.10.2026

## Umsetzung

Phasen 1–3 sind in getrennten Modulen umgesetzt. Phase 4 ist nicht enthalten. Einkaufsfunktionen verwenden einen lokalen HA-Store und die vorhandene REST-API von Yuvomi 2.79.0. Es gibt keine Serveränderung, zusätzliche Datenbank, generischen Schreibzugriff oder neue Zugangsdatenverwaltung.

Produktpflege einschließlich Synonymen und Bestätigung erfolgt über die Integrationsoptionen. JSON-Export ist als kopierbares Textfeld umgesetzt; Import unterstützt nur das eigene Format mit vollständiger Vorschau, ausdrücklicher Bestätigung und Konfliktprüfung. Es ist noch keine Rundgangs-/Massenimportoberfläche. Bestehende Produkt-IDs werden beim Import nicht überschrieben.

## Schrittweise geprüfte Abschnitte

- Phase 1: 109 Tests zu Katalog plus bestehender Runtime-/Kategorieabsicherung bestanden.
- Phase 2: 69 fokussierte Tests zu Katalog, Einkauf, Journal und bestehender Runtime bestanden.
- Phase 3: vollständige Integration einschließlich echtem lokalem HTTP, Sammelaktionen, Mengen, Beobachtung und Sicherheitsrandfällen; 246 Tests bestanden, ein HA-Testmodul lokal übersprungen.
- Ruff und Formatprüfung bestanden. ZIP-Inhalte, Versionsgleichheit und Prüfsummen werden vor Auslieferung geprüft.
- Router-Regressionssuite separat ausgeführt: 219 Tests bestanden; Quellcode unverändert. Das ist keine echte Alexa-/Modell-/HA-Systemabnahme.

Die Tests schreiben ausschließlich in isolierte Testspeicher und lokale HTTP-Fakes. Keine produktiven Zugangsdaten, Container, Listen oder HA-Dateien wurden verändert.

## Sichere Vereinfachungen

- Keine periodische Hintergrundbeobachtung: expliziter Abgleich und Abgleich beim Hinzufügen.
- Keine automatische Bewertung fremder Änderungen als menschlich. Bestätigung nur in HA.
- Kein generisches Ersetzen oder freies Mengenrechnen. Nur sicherstellen oder eindeutig gleiche Einheiten addieren; sonst Rückfrage.
- Keine automatische Wiederholung unklarer Schreibaktionen. Ungeklärte Liste bleibt gesperrt, auch wenn das manuelle Eingreifen erfordert.
- Gleiche Zusatzmenge in neuer Anfrage binnen 120 Sekunden wird konservativ blockiert. Keine Änderung am Alexa-Eingang oder Assist Router zur Request-ID-Durchleitung.
- Keine globale Sperre gegenüber anderen Yuvomi-Clients, keine Exactly-once-Garantie, kein atomarer Sammelauftrag.
- Keine automatische Bereinigung alter Dubletten/Kategorien. Kein Pantry-Abgleich. Alte Preise/Notizen bleiben bei Reaktivierung bestehen und werden nicht neu interpretiert.

## Backup, Update und Rückfall

1. Vollständiges HA-Backup und separat Yuvomi sichern.
2. Integrationsdateien aus dem installierbaren ZIP ersetzen und HA neu starten; Config Entry behalten.
3. Kein Config-Entry-Migrationsschritt erforderlich: v1.2.1 hatte keinen Produktstore. Schema 1 beginnt leer; Bestand wird nur auf Anfrage als unbestätigtes Wissen genutzt.
4. Testliste verwenden und Funktionsprüfungen aus ABNAHME.md ausführen. Keine unbekannten oder generischen Werkzeuge dafür freigeben.
5. Sammelwerkzeug bei Bedarf manuell freigeben. Produktkatalog optional in HA pflegen oder eigenes Exportformat importieren.
6. Vollständiger Zustand liegt im HA-Store je Config Entry; Export allein enthält kein Journal. Unbekannte Formate werden nicht überschrieben. Daten sind an die bisherige Server-URL gebunden.
7. Vor Rückkehr zu 1.2.1 alle unklaren Vorgänge klären und Store sichern. Eine alte Integration ignoriert die neue Sperre. HA-Restore setzt bereits in Yuvomi ausgeführte Aktionen nicht zurück.

## Auslieferung

`dist/yuvomi_mcp-1.3.0.zip`: installierbare Integration plus Dokumentation.
`dist/yuvomi_mcp-1.3.0-source.zip`: zusätzlich Tests, Build-Werkzeuge und vorbereiteter Linux-CI-Workflow.
`dist/SHA256SUMS-1.3.0.txt`: SHA-256 beider Archive.
