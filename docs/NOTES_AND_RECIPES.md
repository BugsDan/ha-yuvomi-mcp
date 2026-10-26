# Einkaufsnotizen und Rezeptpflege 1.4.3

Lokaler Entwicklungsstand, noch nicht veröffentlicht. Yuvomi 2.79.0 bleibt einzige Quelle für Einkaufsartikel und Rezepte. Es gibt keine zusätzliche Rezeptdatenbank, keinen Menüplaner und keine automatische Übertragung in den Einkauf.

## Einkaufsnotizen

Beide Einkaufswerkzeuge haben dieselben optionalen Felder `note` und `note_mode`:

- Ohne beide Felder bleibt die vorhandene Notiz erhalten, auch bei Reaktivierung.
- Mit `note` wird vorhandener Text standardmäßig mit einer neuen Zeile ergänzt.
- `note_mode: "replace"` ersetzt nur bei ausdrücklichem Wunsch den Notiztext.
- `note_mode: "clear"` ohne `note` löscht ausdrücklich. Leerer Text ist kein Löschauftrag.
- Für reine Notizänderungen immer `operation: "note"` ohne `quantity`/`category`. Dies verlangt einen vorhandenen Artikel und ändert weder Menge noch Kategorie oder Einkaufsstatus.

```json
{"name":"Mayonnaise","operation":"note","note":"Ohne Ei","list":"Wocheneinkauf"}
```

```json
{"items":[{"name":"Mayonnaise","operation":"note","note_mode":"clear"}],"list":"Wocheneinkauf"}
```

Bei normalen Einkaufsaufträgen mit zusätzlicher Notiz gelten weiterhin die bisherigen Mengenregeln. Ein bloßer Notizauftrag darf daher niemals als ensure/increase gesendet werden. Notizen werden über REST als `notes` geschrieben, nicht über den alten serverseitigen add_shopping_item-MCP-Pfad. Unicode, Umlaute und Zeilenumbrüche bleiben erhalten; Yuvomi entfernt äußeren Leerraum, maximal 5000 UTF-16-Codeeinheiten. Steuerzeichen außer üblichen Zeilenumbrüchen/Tabulator sind unzulässig.

## Yuvomi-Rezepte heißen bei uns Menüs

Neue lokale Werkzeuge sind in den Integrationsoptionen ausdrücklich freizugeben:

| Werkzeug | Wirkung | Tokenrechte |
| --- | --- | --- |
| list_recipes | Ab RC3 kompakte Übersicht, limit/offset/title; vollständige Seiten ausdrücklich mit detail=full | meals:read |
| get_recipe | Ein vollständiges Rezept nach ID oder exaktem Titel lesen | meals:read |
| create_recipe | Ein natives Rezept anlegen | meals:write; shopping:read bei nichtleeren Zutaten |
| update_recipe | Ein natives Rezept mit erhaltenden Vorgaben bearbeiten | meals:write; shopping:read bei geänderten, nichtleeren Zutaten |

Yuvomi schließt bei einem write-Scope das Lesen desselben Moduls ein. Es werden keine Scopes automatisch ergänzt und keine generischen REST-Schreibwerkzeuge benötigt. Bestehende Freigaben bleiben erhalten; neue Werkzeuge sind standardmäßig aus. Zur besseren Modellkategorisierung zusätzlich list_shopping_categories freigeben.

Ab 1.4.4-rc3 ist der Standardausgabevertrag von `list_recipes` bewusst kompakt und paginiert:
`data` bleibt ein Array, enthält standardmäßig aber nur Zusammenfassungen. Bestehende Workflows,
die Zutaten/Notizen brauchen, verwenden `get_recipe` oder `list_recipes` mit `detail="full"`
und folgen `has_more`/`next_offset`. Einzelheiten und Beispiele: [RECIPE_CONTEXT.md](RECIPE_CONTEXT.md).

```json
{
  "title":"Gemüse-Curry – mit Kichererbsen",
  "ingredients":[{"name":"Kichererbsen","quantity":"2 Dosen","category":"Sonstiges"}],
  "notes":"Gemüse vorbereiten, kurz anbraten und zusammen köcheln lassen.",
  "metadata":{
    "wiederaufwärmbar":true,
    "zubereitungszeit_min":40,
    "gesundheit":4,
    "gesundheit_begruendung":"Gemüse und Hülsenfrüchte; abhängig von Salz- und Fettmenge.",
    "mag_nicht":[],
    "basisportionen":4
  }
}
```

Kategorien müssen im konkreten Yuvomi existieren; das Beispiel enthält keine allgemeingültige Kategoriezuordnung. Basisportionen sind beim Erstellen standardmäßig 4, mag_nicht standardmäßig leer (keine erfassten Abneigungen, keine bestätigten Vorlieben). Die übrigen Metadaten müssen angegeben werden; unbekannte Aufwärmbarkeit oder Zeit werden erfragt. Zeit meint den gesamten Ablauf vom Kochbeginn bis servierfertig, einschließlich Warte-/Backzeit. Eine KI-Gesundheitsbewertung enthält eine Begründung und wird als `ki_vorschlag` gespeichert, niemals als menschliche Bestätigung.

Metadaten stehen ausschließlich im gekennzeichneten JSON-Abschnitt `[yuvomi_mcp:menu:v1] ... [/yuvomi_mcp:menu:v1]` der Yuvomi-Rezeptnotiz. Der JSON-Umschlag enthält `metadata` und `gesundheit_herkunft`; er ist ein dokumentierter Notizvertrag, kein Yuvomi-Serverfeld. Leser liefern den Block zusätzlich als menu_metadata. Beschädigte oder doppelte Blöcke werden angezeigt, aber nicht überschrieben. Vorhandene reine Freitextrezepte bleiben ohne automatische Datenanreicherung lesbar.

Neue Rezepte erhalten `meal_types: ["lunch"]` (Mittagessen); bestehende Mahlzeitzuordnungen bleiben erhalten. Titel/Varianten werden exakt übernommen; äußere Leer-/Steuerzeichen oder zu lange Namen werden abgewiesen statt still gekürzt. Ein bereits existierender exakter Titel blockiert eine Neuanlage. Zur Bearbeitung ist eine ID erforderlich; keine unscharfe Namensauflösung.

Bei update_recipe bleiben ausgelassene Felder erhalten. `notes` ergänzt standardmäßig, `notes_mode: "replace"/"clear"` ändert nur den freien Text, nicht den strukturierten Block. `metadata` ergänzt/ändert einzelne Felder eines vollständigen vorhandenen Blocks. Bei erstmaliger Metadatenpflege eines Alt-Rezepts ist der vollständige Block einschließlich basisportionen und mag_nicht nötig. Bei geänderter Basisportionenzahl müssen passende vollständige Zutatenmengen mitgegeben werden; es gibt keine automatische Skalierung. Ein leerer ingredients-Wert bedeutet ausdrücklich die vollständige Zutatenliste zu leeren.

Bilder und Rezept-Links werden ausschließlich im Yuvomi-GUI gepflegt. Updates erhalten Link und Bild; die API ersetzt beim PUT Zutatenzeilen, wodurch Zutaten-IDs wechseln können. Provider-gespiegelte Rezepte werden ausschließlich an ihrer Quelle bearbeitet. Ein Rezept mit Titel „Resten“ und leerer Zutatenliste ist möglich, ohne Vorratsberechnung oder Sonderautomatik.

## Sicherheit und Wiederholungsschutz

Shopping verwendet weiterhin dieselbe Listensperre, REST-Bestandsprüfung und das vorhandene Journal. Bei Notizänderungen werden Notizen in den erneuten Zustandsvergleich und in die Wiederholungsabsicht einbezogen. Notizergänzungen mit neuer kurzfristiger Retry-ID werden für denselben Aufrufer konservativ dedupliziert. Identische echte Ergänzungswünsche können dadurch im 120-Sekunden-Fenster unterdrückt werden; nach diesem Fenster sind neue IDs neue Aufträge.

Rezeptschreiben wird integrationsintern serialisiert. Transaktionsbelege mit `resource: "recipes"` liegen im bestehenden Schema-2-Journal; alte Belege ohne resource gelten weiter als Einkauf. Rezeptbelege sind keine aktive Rezeptkopie: Entscheidungen lesen immer Yuvomi. Request-Replays dürfen frühere Ergebnisse liefern, sind aber kein aktueller Bestandsabruf. POST verwendet einen stabilen Idempotency-Key, PUT vollständige Zielwerte. Gleiche kurzfristige Aufträge desselben Aufrufers werden ohne erneutes Anhängen wiedergegeben. Ein unbekannter Ausgang sperrt weitere Rezept-Schreibaktionen, nicht den Einkauf. Die HA-Ausführungsprüfung liest nur und meldet state_observed, niemals automatische Wiederholung.

Vor PUT wird nochmals der aktuelle Rezeptstand verglichen. Ohne bedingtes serverseitiges Update bleibt ein Zeitfenster für externe Clients. Es gibt keine globale Exactly-once-Garantie. Ein Netz-/HA-Abbruch nach vorbereiteter Transaktion bleibt über Neustarts gesperrt. Volles Journal oder Speicherfehler stoppen vor neuen Schreibaktionen. Rückweg auf ältere Integration nur mit konsistentem Backup, niemals Journalvorgänge löschen.

## Grenzen des Transportes

Wie bisher sind REST-Antworten auf 2 MiB und 8 Sekunden begrenzt; vollständige Listen oberhalb dieses Limits werden sicher abgewiesen, niemals als unvollständiger Bestand weiterverarbeitet. Da Yuvomi hier keine Pagination oder Einzelrezept-GET anbietet, kann dies bei sehr großen Rezeptbeständen relevant werden.

## Kurze lokale Abnahme vor einer späteren Installation

Auf einer ausdrücklich gewählten Testliste/Entwicklungsinstanz: Notiz anlegen, abgehakten Artikel mit alter Notiz reaktivieren, reine Notizänderung mit unveränderter Menge/Status, append/replace/clear und identischen Retry prüfen. Ein Testrezept mit 4 Basisportionen anlegen, in Yuvomi lunch und Notizblock kontrollieren, Freitext ergänzen und vorhandenen Link/Bildbestand erhalten. Metadaten partiell ändern; bei Portionsänderung passende Zutaten explizit nachliefern. Resten ohne Zutaten prüfen. Neue Rezeptwerkzeuge nur bewusst freigeben. Menüplan-Auslöser darf noch keine Planung oder Einkaufsübertragung ausführen.
