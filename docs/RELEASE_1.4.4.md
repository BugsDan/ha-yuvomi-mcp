# Yuvomi MCP 1.4.4 – lokale Prüfversion

Noch nicht veröffentlicht oder produktiv installiert. Kein Commit, Push oder Tag gehört zu diesem Entwicklungsauftrag.

- Eigenständige auswählbare LLM-API „Yuvomi MCP Familie“, ID yuvomi_family_<entry_id>. Expliziter reversibler Expositionsmodus assist/dedicated; assist bleibt Standard. Gleiche Runtime, Berechtigungen, Allowlist, Bestätigungen und Journale.
- Optimierte bekannte Werkzeugbeschreibungen mit vollständiger Schemakompatibilitätsprüfung. Namen und bestehende Parameterverträge unverändert. Neun Referenzdefinitionen: 11026 → 7467 kanonische UTF-8-Bytes, 32,3 % weniger. Das sind keine Gemma-Tokens.
- Drei neue standardmässig deaktivierte Werkzeuge: get_menu_planning_context, save_menu_plan, get_menu_plan. Keine automatische Freigabe der vier Rezeptwerkzeuge.
- HA-Optionseditor für versionierte Planungskonfiguration, Familienprofile, explizit ausgewählte Kalender, Tageszeitlimits, Perioden, Wiederholungsausnahmen, Resten/Notfall und Aufwärmbedarf.
- Gemma wählt Gerichte. Backend prüft Modellzuweisungen, skaliert Mahlzeitzutaten und speichert über feste Meals-REST-Pfade. Erstplanung schützt belegte Slots; explizite Tagesänderung ersetzt genau einen Slot ohne weitere Bestätigung.
- Schlanke Zusatzportionen in Yuvomi-Mahlzeitnotizen, keine tatsächlichen Restenbestände. Aufwärmeinträge ohne native Rezeptverknüpfung, damit kein erneuter Zutaten-Fallback entsteht.
- Persistente meals-Belege, Serialisierung, POST-Idempotency-Key und sichere Barrieren für unklare Schreibausgänge; administrative Wiederherstellung ausschliesslich lesend.

Einrichtung, A/B-Vergleich und Grenzen: [SETUP_1.4.4.md](SETUP_1.4.4.md). Ergebnisse und noch offene Abnahme: [TEST_REPORT_1.4.4.md](TEST_REPORT_1.4.4.md).

Nicht enthalten: automatische Conversation-Isolation, Assist-Router-Änderungen, virtueller HA-Schalter, Hintergrundplanungsdienst und Einkaufssynchronisation. Letztere wird wegen nicht hinreichend geprüfter Pantry-/Packungsverträge nicht exponiert. Menüplanung schreibt niemals automatisch in Einkauf oder Vorrat.
