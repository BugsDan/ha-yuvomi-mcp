# Yuvomi MCP 1.4.4-rc3

**Pre-Release / Release Candidate, keine stabile Version 1.4.4.**

Aufbauend auf dem unveränderten veröffentlichten RC2:

- `list_recipes` liefert standardmäßig kompakte Zusammenfassungen (20 pro Seite), mit
  limit/offset, exaktem title-Filter und optionalen strukturierten Metadaten.
- `get_recipe` liest weiterhin eine vollständige Rezept-ID und alternativ direkt einen exakten Titel.
  Mehrdeutige Titel erfordern eine ID; unterschiedliche Varianten werden nicht gleichgesetzt.
- Menüplanung erhält schlanke Rezeptprojektionen; vollständige Originaldaten bleiben intern
  für Portionsberechnung, Validierung, Konfliktschutz und Speicherung erhalten.
- Redundante content-Textkopie aus Rezept-Leseergebnissen im HA-LLM-Adapter entfernt.
- Keine Änderungen an Yuvomi, Einkaufslisten, Schreibrechten, Freigaben, Journal oder Idempotenz.

## Bewusste Rückgabevertragsänderung

`list_recipes({})` ist weiterhin gültig, liefert aber eine kompakte Seite statt aller
vollständigen Rezepte. `data` bleibt ein Array; `has_more`/`next_offset` steuern die Pagination.
Bestehende Workflows mit Bedarf an vollständigen Rezepten verwenden `get_recipe` oder
`list_recipes({"detail":"full","limit":100,"offset":0})` und weitere Seiten bei Bedarf.
Unbekannte bzw. ungültige Metadaten werden nicht geraten; eine geänderte REST-Envelope wird
als ungesicherter Listenvertrag zurückgewiesen statt als vollständig ausgegeben.

## Struktureller Vergleich, keine Modellmessung

22 synthetische Rezepte: vollständige bisherige Liste 221 916 UTF-8-Bytes,
neue kompakte Liste 4 022 Bytes (**98,19 % weniger**, einschließlich vermiedener Textduplikation).
Einzelnes vollständiges Rezept 4 846 Bytes. Wochenplanungskontext 109 096 → 26 706 Bytes
(**75,52 % weniger**). Die tatsächlichen Token- und Performancewerte misst der Betreiber
anschließend in Home Assistant/LM Studio; vorhandene RC1-/RC2-Werte sind keine RC3-Ergebnisse.

## Installation und verbleibende Grenzen

- Vollständiges HA-Backup vor Installation. Home Assistant mindestens **2026.10.2**.
- In HACS Pre-Release-/Beta-Versionen für das Repository auswählen; `v1.4.4-rc3` verwenden.
  HACS installiert aus dem Tag-Quellbaum (`zip_release: false`).
- Manifest und Paketnamen bleiben **1.4.4**; Git-Tag/Pre-Release unterscheiden die Kandidaten.
  Installations-ZIP, Source-ZIP und SHA256SUMS stammen aus dem vorhandenen Paketbauer.
- Yuvomi 2.79.0 liefert weiterhin den gesamten Rezeptbestand an die Integration; verringert wird
  die an das Modell übergebene Ausgabe. Exakte Titelsuche ist keine semantische Suche.
- Gleichzeitige Änderungen können clientseitige Offsets verschieben. Vor Schreibaktionen bleiben
  vollständige Quellen- und Konfliktprüfungen aktiv. Sehr große planungsrelevante Zutatenbestände
  können weiterhin viel Kontext benötigen; keine stille Kürzung.
- RC1 und RC2 sowie `main` bleiben unverändert. Keine produktive Installation durch diesen Auftrag.

[Verträge, Beispiele, Teststrategie und Messanleitung](RECIPE_CONTEXT.md)
beschreiben die Betreiber-Abnahme. Veröffentlichung erst nach erfolgreicher vollständiger
CI einschließlich echter HA-2026.10.2-Laufzeittests unter Python 3.14, Ruff/Format,
Repository-/Paketprüfung, HACS, hassfest und Secret-Scan.
