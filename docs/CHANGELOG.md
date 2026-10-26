# Änderungen

## 1.4.4 – lokal, unveröffentlicht

- Kürzere Beschreibungen nur bei kompatiblen bekannten Schemas; bestehende Namen, Parameterverträge und Freigaben erhalten. Gemeinsamer Basisprompt für die neun bisherigen Tools bleibt unverändert.
- Eigene auswählbare Yuvomi-LLM-API, reversibler Expositionsmodus assist (bestehender Standard) oder dedicated. Gleiche Runtime und sofortige Sperre alter Toolinstanzen bei Moduswechsel. Keine Router-/Agentenänderung.
- Drei neue standardmässig gesperrte Menüwerkzeuge: get_menu_planning_context, save_menu_plan, get_menu_plan. Gemma wählt; Backend validiert, skaliert und speichert freie Slots bzw. ausdrücklich geänderte einzelne Tage über feste REST-Pfade.
- Separater versionierter Planungsstore mit HA-Optionseditor, Kalender-Allowlist/Leserechten, Portionen, Präferenzen, Wiederholungen und Tageszeitlimits. Schlanke Zusatzportionen in Yuvomi-Mahlzeitnotizen, kein Restenbestand.
- Persistente meals-Ausführungsbelege, Serialisierung, POST-Idempotenz, lesende Wiederherstellung und kein automatischer Retry unklarer Schreibausgänge.
- Vollständige Wochenplanung setzt bewusst separate Conversation voraus; kein automatischer Sitzungswechsel oder Hintergrunddienst. Einkaufssynchronisation wegen nicht ausreichend geprüfter Pantry-/Packungsverträge nicht exponiert.
- Einrichtung, A/B-Messanleitung und lokale Prüfergebnisse dokumentiert. Keine Veröffentlichung oder produktive Installation.

## 1.4.3 – lokal, unveröffentlicht

- Einkaufsnotizen in Einzel-/Sammelwerkzeug: append als Vorgabe, explizites replace/clear, ausgelassen erhält Text. Eigene operation=note ohne Mengen-/Statusänderung.
- Neue ausdrücklich freizugebende Rezeptwerkzeuge list_recipes, get_recipe, create_recipe und update_recipe über feste Yuvomi-REST-Pfade. Standard Mittagessen und 4 Basisportionen; Zutatenkategorien validiert.
- Strukturierte Menümetadaten ausschließlich in Yuvomi-Rezeptnotizen, begründete Gesundheit als KI-Vorschlag; Freitext, Varianten, vorhandene Links/Bilder erhalten. Keine Rezeptdatenbank in HA.
- Persistente Rezept-Schreibbelege im bestehenden Journal, Serialisierung und POST-Idempotenz; unklare Ausgänge sperren sicher, Prüfung nur lesend. Notiz-Retries ohne erneutes Anhängen oder Mengenaddition.
- Menüplanung getrennt spezifiziert: konfigurierbare Perioden, Familien-/Kalenderregeln, Bestätigung und spätere wiederholungssichere Einkaufssynchronisation. Noch kein Planungswerkzeug.
- Keine Yuvomi-Serveränderung, keine automatische Werkzeugfreigabe oder produktive Aktivierung.

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
