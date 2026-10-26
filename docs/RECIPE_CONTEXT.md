# Rezeptabfragen und Planungskontext ab 1.4.4-rc3

## Geprüfte Yuvomi-Funktionen

Im vorhandenen Yuvomi-Quellbaum mit `package.json`-Version 2.79.0 liefert
`server/routes/recipes.js`, `router.get('/')`, `{data: [...]}` mit vollständigen
Rezepten und Zutaten. Sortierung: Titel ohne Beachtung der Groß-/Kleinschreibung,
danach ID absteigend. Keine Such-, Limit- oder Offset-Auswertung; kein Einzelrezept-GET.
Die GET-Unterpfade für Bilder sind kein Ersatz für einen Einzelrezeptabruf.
`image_data` wird serverseitig entfernt, Links, Notizen und Zutaten bleiben in der Liste.

Die Integration liest deshalb weiterhin **den vollständigen REST-Bestand** mit `meals:read`.
Die neue Pagination/Suche ist eine Projektion in HA, keine vorgetäuschte REST-Funktion.
Fehlgeschlagene oder ungültige Antworten werden nicht als leere Liste ausgegeben.
Der vollständige 2.79.0-Vertrag hat ausschließlich den Schlüssel `data`; zusätzliche
Envelope-Felder werden sicherheitshalber als Vertragsänderung zurückgewiesen. So werden
später eingeführte Pagination-/Teilbestandsmarker nicht stillschweigend ignoriert.
Eine unangekündigt serverseitig gekürzte Antwort ohne jeden Marker ist technisch nicht
von einem echten vollständigen Bestand unterscheidbar; Grundlage bleibt der geprüfte REST-Vertrag.
Die bestehenden Grenzen von 10 000 Rezepten/Zutaten bleiben erhalten; Überschreitung ist ein Fehler.

## list_recipes – geänderter Standardausgabevertrag

Werkzeugname und Freigabe bleiben erhalten. `{}` ist weiterhin gültig, liefert aber
**Zusammenfassungen und höchstens 20 Einträge**, nicht mehr alle vollständigen Rezepte.
Dies ist eine bewusste Änderung des Rückgabevertrags; Workflows mit Bedarf an vollständigen
Zutaten oder Anleitungen müssen den expliziten Vollabruf verwenden.

Neue optionale Parameter:

| Parameter | Bedeutung |
| --- | --- |
| `limit` | Ganzzahl 1–100, Standard 20. |
| `offset` | Ganzzahl ab 0, Standard 0. |
| `title` | Exakter gespeicherter Titel einschließlich Groß-/Kleinschreibung, Unicode und Variante. Keine Teilwort-/Ähnlichkeitssuche. |
| `detail` | `summary` (Standard) oder ausdrücklich `full`. |
| `include_metadata` | In Zusammenfassungen zusätzlich strukturierte Menümetadaten inklusive Gesundheitsbegründung/Herkunft; Standard false. |

`data` bleibt ein Array. Kompakte Zeilen enthalten ausschließlich `id`, `title`,
`meal_types`, `basisportionen`, `zubereitungszeit_min`, `wiederaufwärmbar`, `gesundheit`,
`mag_nicht` und gegebenenfalls `metadata_error`. Keine Anleitungen, Freitextnotizen,
Zutatenlisten, Bilder oder Links. Unbekannte Werte sind `null`, keine erfundenen Vorgaben.
Ungültige verwaltete Metadaten bleiben als Fehler gekennzeichnet und werden nicht geändert.

Das Ergebnis enthält außerdem `total`, `limit`, `offset`, `detail`, `has_more` und
`next_offset`. `total` zählt Treffer nach Titelfilter. Bei `has_more: true` die nächste
Seite mit `offset: next_offset` abrufen. Ein Offset hinter dem Ende ergibt ein leeres
Array mit `has_more: false`, nicht einen Fehler oder einen neuen Anfang.

Beispiele:

```json
{"limit": 20, "offset": 0}
```

```json
{"detail": "full", "limit": 100, "offset": 0}
```

Auch der Vollabruf ist paginiert; mehr als 100 Rezepte erfordern weitere Seiten.
Es gibt keinen dauerhaften HA-Rezeptcache. Gleichzeitige Änderungen in Yuvomi können
Offsets zwischen zwei Aufrufen verschieben; für sicherheitsrelevante Schreibentscheidungen
verwendet das Backend weiterhin frische vollständige Quellen und Konfliktprüfungen.

## get_recipe – vollständiges Einzelrezept

Bestehende Aufrufe mit `recipe_id` bleiben unverändert gültig. Alternativ ist jetzt `title`
erlaubt. **Genau einen** der beiden Parameter angeben; beide oder keiner ergeben
`invalid_arguments` vor dem REST-Abruf. Kein unscharfer Variantenabgleich.

```json
{"title": "Fleischkäse mit Ofengemüse"}
```

```json
{"recipe_id": 17}
```

Ein bekannter, exakter Titel kann direkt abgefragt werden, ohne vorher alle Rezepte
aufzulisten. Kein Treffer ergibt `recipe_not_found`; mehrere exakt gleichnamige Rezepte
ergeben `recipe_unclear` und erfordern eine ID. Es wird nie willkürlich die erste Variante gewählt.
Das Ergebnis enthält ausschließlich das ausgewählte vollständige Rezept einschließlich
Zutaten, Freitextmengen/Einheiten, Anleitung/Notizen und strukturierter Menümetadaten.
Yuvomi 2.79.0 speichert die Einheit in der Freitextmenge, nicht in einem separaten Mengenfeld.
Der vollständige REST-Bestand wird intern trotzdem einmal gelesen und validiert.

## LLM-Adapter und Menüplanung

Rezept-Leseergebnisse hatten bisher gleichzeitig `data` und eine als Text serialisierte
`content`-Kopie desselben Inhalts im HA-ToolResult. Für `list_recipes` und `get_recipe`
entfernt der LLM-Adapter jetzt diese redundante `content`-Kopie, wie bisher bei Menüwerkzeugen.
`data`, Fehlerstatus und Pagination bleiben enthalten. Interne Runtime-Ergebnisse behalten
ihren bisherigen `content`-Umschlag; schreibende Rezeptwerkzeuge/Journale werden nicht umgestellt.

`get_menu_planning_context` enthält je Rezept nur ID, exakten Titel, Mahlzeittypen,
strukturierte Menümetadaten einschließlich Gesundheitsbegründung/Herkunft und die Zutatenfelder
Name, Menge, Kategorie. Keine Freitextnotizen, Anleitungen, Bild-/Quellindikatoren oder Links.
Planungsregeln, Familienprofile, Kalenderauswertung, bestehende Mahlzeiten und Rückfragen
bei unbekannten Metadaten bleiben unverändert. Große Zutatenbestände bzw. übrige relevante
Planungsdaten können den Kontext weiterhin vergrößern; es wird nichts stillschweigend abgeschnitten.

Die vollständigen Rezepte bleiben in der bestehenden kurzlebigen Planungssitzung erhalten:
Rezeptidentität, Portionsskalierung, Zutatenberechnung, Notizerhalt, Quellenvergleich vor
Speicherung und Konfliktschutz arbeiten weiterhin mit unveränderten Originaldaten.
Keine Rezeptdatenbank, Migration, zusätzlichen Rechte oder Änderungen an Yuvomi/Einkauf.
Die vollständige Wochenplanung benötigt weiterhin eine bewusst separate Conversation.

## Reproduzierbarer Größenvergleich

Ausführen im Repository:

```text
python -m pytest -q -s tests/test_recipe_views.py -k response_sizes
```

Die Fixture erstellt 22 synthetische Familienmenüs mit zwölf Zutaten, strukturierten
Menümetadaten und einer längeren wiederholten Kochanleitung pro Rezept. Keine produktiven
Familien-/Rezeptdaten werden benötigt. Gezählt werden UTF-8-Bytes von kanonisch serialisiertem
JSON (`ensure_ascii=False`, kompakte Separatoren), einschließlich der jeweiligen Ergebnis-Hülle.

| Antwort | UTF-8-Bytes |
| --- | ---: |
| Bisherige vollständige Liste, einschließlich doppelter content-Kopie | 221 916 |
| Dieselbe vollständige Liste ohne redundante content-Kopie | 106 123 |
| Neue kompakte Liste aller 22 Rezepte (`limit=100`) | 4 022 |
| Ein vollständiges Rezept | 4 846 |
| Bisheriger vollständiger Wochenplanungskontext | 109 096 |
| Neuer kompakter Wochenplanungskontext | 26 706 |

Für die vollständige Liste beträgt die strukturelle Reduktion **98,19 %**; diese setzt
sich aus Projektion und Entfernung der redundanten Textkopie zusammen. Für den bereits
vorher nicht doppelt serialisierten Menüplanungskontext beträgt sie **75,52 %**.
Die Listenzahl umfasst bewusst alle 22 statt nur der standardmäßig gelieferten 20 Rezepte.
Kein Nachweis tatsächlicher Modell-Tokens, Latenz oder KV-Cache-Ersparnis; keine Reproduktion
der Betreiberwerte von etwa 197 KB / 79 000 Tokens / 118 bzw. 49 Sekunden.

## Tests und Betreiber-Abnahme

Regressionen prüfen Zusammenfassungen, unbekannte/beschädigte Metadaten, optionale Metadaten,
Grenzen/Offset-Ende, 501 Rezepte, exakte Varianten und mehrdeutige Titel, vollständige Einzel-
und Legacy-Abrufe, unbekannte REST-Envelopes, widerrufene Freigaben sowie eine vollständige
Wochenspeicherung mit Zutaten-Skalierung aus Originaldaten. Eine echte HA-Laufzeitprüfung
testet den Adapter über HTTP und echte LLM-API-Klassen, einschließlich fehlender content-Duplikation.

Nach erfolgreicher CI in einer Betreiber-Testinstallation prüfen:

1. Exakte Rezeptanfrage direkt mit `get_recipe(title=...)`, inklusive Umlauten und Variante.
2. Übersicht/Pagination ohne Anleitungen und vollständigen Abruf mit `detail=full`.
3. Menüplanung und gezielte Tagesänderung mit korrekten Portionen und erhaltenen Quellen.
4. Tatsächliche Antwortgrößen, Prompt-Tokens und Laufzeiten in LM Studio messen.

Identische Modelle, Familienprompts und Freigaben verwenden. Neue Schemas werden erst nach
Neuladen der Integration/Agentendaten sichtbar; für den Vergleich neue Conversations beginnen.
Die Rezept-Schemas sind etwas größer als zuvor, dafür werden unnötige große Antworten vermieden.
