# Testbericht 1.4.3 – 25.10.2026

Lokaler Entwicklungsstand, keine produktive Installation. Kein Commit, Push, Tag oder GitHub-Release für 1.4.3; vorhandener Tag/Draft 1.4.2 bleibt unberührt.

## Ausgeführt und bestanden

- Vollständige Suite unter Windows/Python 3.12.10: **452 Tests bestanden, 1 HA-spezifisches Modul übersprungen**, 14,08 Sekunden im abschließenden Lauf. Gegenüber der Baseline 373 zusätzliche 79 lokal ausgeführte Regressionen. Keine alten Tests deaktiviert oder entfernt; der bestehende Schema-Test erwartet jetzt zusätzlich die neue Operation note.
- Ruff-Lint und Formatprüfung für custom_components, tests und tools erfolgreich.
- Offizielle HA-2026.10.2-Quellverträge mit tools/check_ha_api.py erfolgreich geprüft; keine produktive HA-API kontaktiert.
- Neun unveränderte offizielle Yuvomi-2.79.0-Quellen vom geprüften Commit direkt über GitHub gelesen und SHA-256-/Bytevergleich durchgeführt. Nachweis: yuvomi_2.79.0_evidence.json. Keine produktive Yuvomi-Verbindung und keine Serverdatei geändert.
- Publikations-/Versionsprüfung mit angenommenem Tag v1.4.3: keine Findings. Dies ist nur eine lokale Konsistenzprüfung und erstellt keinen Tag.
- Paketierungsregressionen prüfen manuelles ZIP, Source-ZIP, öffentliche Dateigrenzen, Originalbytes, Brand und Metadaten. Lokale Entwicklungsarchive und SHA-256-Datei werden mit tools/build_release.py erzeugt; kein Upload.

## Abgedeckte Fälle

- Einkaufsnotizen: optionales Feld in Einzel-/Sammelverarbeitung; Erhalt, Ergänzung, Ersatz, ausdrückliches Löschen; unveränderte Menge/Kategorie/Status bei operation=note, auch abgehakt; Unicode, UTF-16-Grenze und CRLF.
- Mengen- plus Notizauftrag: nur eine Addition/Ergänzung bei gleichem Request und kurzfristig neuer Retry-ID, auch set mit zusätzlicher Notiz. Reaktivierung mit neuer Menge und erhaltener/ergänzter Notiz.
- Parallele Aufträge, fremde Notizänderungen, Timeouts nach erfolgreichem Serverspeichern, Neustart und rein lesende Zustandsprüfung. Unvollständige Notizantworten werden abgewiesen.
- Rezeptanlage als lunch und 4 Basisportionen, andere ausdrücklich genannte Basis; exakte Varianten, Resten mit leerer Zutatenliste und Zeit 0; echte Kategorien, begründete Bewertung als KI-Vorschlag.
- Rezeptbearbeitung mit Erhalt von Zutatenmengen/-kategorien, bestehendem Notiztext, Link und Bild. Strukturierte Teiländerungen, keine ungefragte Skalierung, Portionsänderung nur mit ausdrücklich passenden Zutaten.
- Kaputte/doppelte Metadatenblöcke, ungültige Bewertung/Unicode, fehlende Felder, Provider-Rezepte und Titelkonflikte werden sicher behandelt.
- Rezept-POST mit Idempotency-Key, vollständiges PUT, parallele identische Aufträge und kurzfristige neue IDs, persistente Wiederherstellung aus echtem lokalem Dateispeicher, Netzfehler, fehlende Schreibantwort, Abbruch und HA-Entladeverhalten.
- Fehlendes/volles/defektes Journal stoppt sicher. Rezept-Schreibsperre blockiert nicht versehentlich die Einkaufsliste; generische Einkaufs-PUT-Belege bleiben verboten. Alte Migrations-/Journalregressionen bestehen unverändert.
- Neuer echter lokaler TCP-Test durchläuft HA-Runtime → REST → Rezeptanlage/Bearbeitung/Lesen, ohne shopping-/meals-Schreibzugriff. Schema-/Freigabe-/Revokationstests verwenden keine produktiven Dienste. Bestehende MCP-Aufgaben-/Kalender- und Assist-Router-Kontexttests bestehen.

## Noch nicht ausgeführt

Das echte HA-Modul benötigt Linux/Python >=3.14.2 mit HA 2026.10.2. Die zwei neuen HA-spezifischen Tests zu Rezept-Annotationen und Ausführungsoptionen sind ergänzt, werden auf diesem Windows/Python-3.12-Host aber zusammen mit dem bestehenden Modul übersprungen. Auch HACS und hassfest wurden für diesen ungepushten Stand nicht ausgeführt. Alte grüne CI-Ergebnisse von 1.4.2 gelten ausdrücklich nicht als Nachweis für 1.4.3.

Keine Live-Abnahme mit produktivem HA/Yuvomi oder Alexa/Gemma/OpenAI/Gemini; die tatsächlich laufende Container-Instanz wurde nicht abgefragt. Keine gesonderte Ausführung der Tests eines anderen Router-Repositories. Die bestehenden Integrations-/Runtime-Tests prüfen dessen bisherige Aufrufkontexte.

Vor einem späteren Release: vollständige GitHub-CI einschließlich echtem HA, HACS und hassfest; danach bewusst gewählte Testinstanz/Testliste und Backup-/Abnahmehinweise in NOTES_AND_RECIPES.md.

## Grenzen

- Keine serverseitige atomare Konfliktvorbedingung für Rezept-PUT; Fremdänderung zwischen letztem Vergleich und Schreiben möglich.
- PUT erzeugt neue Zutatenzeilen-IDs. Yuvomi erhält vorhandene Pantry-Verknüpfungen namensbasiert; kein neuer Pantry-Abgleich in HA.
- 120-Sekunden-Heuristik kann absichtliche identische Wiederholungen unterdrücken und erkennt spätere neue IDs nicht unbegrenzt. Keine globale Exactly-once-Garantie.
- Vollständige REST-Antworten sind auf 2 MiB/8 Sekunden begrenzt. Zu große Bestände werden sicher abgewiesen.
- Kein Menüplaner, keine Planungskonfiguration, Kalender-/Vorratsabfrage oder Einkaufssynchronisation implementiert. Anforderungen stehen in MENU_PLANNING.md.
