# Backup, Installation und Abnahme 1.4.2

## Vorher sichern

1. Vollständiges HA-Backup einschließlich Konfiguration, bisherigem `custom_components/yuvomi_mcp` und `.storage` erstellen und extern aufbewahren. Offene Ausführungen in 1.3.0 notieren. Yuvomi wie üblich separat sichern.
2. ZIP-Prüfsumme mit `SHA256SUMS-1.4.2.txt` vergleichen. Keine Daten aus `.storage` löschen und keine bestehenden Werkzeugfreigaben zurücksetzen.

## Manuelle Installation

1. HA geordnet stoppen. Bisherigen Integrationsordner außerhalb von `custom_components` sichern, damit alte und neue Module nicht vermischt werden.
2. Aus `yuvomi_mcp-1.4.2.zip` ausschließlich `custom_components/yuvomi_mcp` an dieselbe Stelle unter der HA-Konfiguration kopieren. Dokumentation kann außerhalb der Konfiguration bleiben.
3. HA starten. Kein Löschen/Neuanlegen der Integration nötig. Beim Upgrade von 1.4.0/1.4.1 bleibt der Schema-2-Store unverändert; keine neue Migration. Nur beim direkten Upgrade von 1.3.0 wird der bisherige vollständige Store archiviert und das Journal übernommen. Es gibt keine Yuvomi-Schreibaktion während der Migration.
4. Version 1.4.2, unveränderte URL/Token/Freigaben und Optionenmenü prüfen: Werkzeuge, Aktion bestätigen, Ausführungen prüfen. Produktpflege/Vorschläge/Import/Export dürfen nicht mehr erscheinen.
5. Existierten 1.3.0-Daten, müssen aktiver Store und `.catalog_archive_v1`-Archiv existieren. Nicht manuell bearbeiten. Bei Fehlern erst Speicher/Backup prüfen; keine erzwungene Neuanlage des Journals.
6. `add_shopping_items` und `list_shopping_categories` nur dann explizit aktivieren, wenn gewünscht und noch nicht freigegeben. Eine neue Assist-Unterhaltung starten, damit Werkzeugbeschreibungen frisch geladen werden.

## Funktionstest auf einer ausdrücklich ausgewählten Testliste

- Neu ohne Menge anlegen: quantity „1“. Mit „1 Flasche“, „2 Tuben“ oder „1 Packung“: Text unverändert.
- Chips offen mit „1 Packung“ und quantity „2 Packungen“ über ensure/increase: gleiche ID, „3 Packungen“, action increased, old_quantity/new_quantity korrekt.
- Mayonnaise offen mit „1 Packung“ und quantity „2 Tuben“: gleicher Artikel mit „2 Tuben“, action replaced, transparentes Ergebnis, keine Rückfrage.
- Offenen Artikel ohne Mengenangabe ergänzen: +1 der sicher erkennbaren Einheit. Abgehakten Artikel ohne Menge reaktivieren: neue Menge „1“, nicht zur alten addieren.
- Identischen Vorgang wiederholen bzw. kurzfristig mit neuer ID anfragen: keine erneute Addition; bei neuer ID replayed. Für einen echten identischen zweiten Wunsch im 120-Sekunden-Fenster gegebenenfalls set als absolute Korrektur verwenden.
- Kategorie in Yuvomi ändern und neue Anfrage ausführen: aktuelle Kategorie verwenden, auch wenn das Modell eine andere vorschlägt.
- Neues Produkt ohne Kategorie aufrufen: `category_required`, gültige Kategorien im Ergebnis, kein neuer Artikel. Mit gültiger Kategorie korrigieren: genau eine Neuanlage.
- Sammelaufruf mit zwei fehlenden Kategorien: beide im selben Vorprüfergebnis aufführen; keinerlei neue Schreibaktion. Anschließend korrigierten Sammelaufruf ausführen.
- Kochschokolade/Schokolade, Thon klein/Thon gross, Mais klein/Mais gross und Markenvarianten als getrennte Artikel prüfen. Groß-/Kleinschreibung und harmlose Leerraumvarianten dürfen vorhandene IDs wiederverwenden.
- Explizite Gesamtmenge mit operation=set korrigieren. Nicht sicher addierbare Freitextmenge übernehmen statt nachzufragen; unveränderte Sicherheitsprüfung für leere/zu lange/steuerzeichenhaltige Angaben. Ergebnis und Sprachausgabe müssen Addition und Ersatz unterscheiden.
- Aufgaben und Kalender wie bisher prüfen. Neues unbekanntes Werkzeug darf weder automatisch freigegeben noch ohne bisherige Aktionsbestätigung ausgeführt werden.
- Nach kontrolliertem HA-Neustart denselben Testvorgang nicht nochmals schreiben. Für Timeout-/Abbruchtests ausschließlich eine Entwicklungsumgebung nutzen: vorbereitetes/unklares Journal muss die Liste sperren, Ausführungsprüfung darf nur lesen.

## Rückweg und Grenzen

Kein automatischer Rollback auf 1.3.0: dessen Katalogschema versteht den aktiven Schema-2-Store nicht. Für einen Rückweg ein konsistentes vollständiges Backup verwenden und seitdem erfolgte Yuvomi-Aktionen vor neuen Anfragen prüfen. Das Altkatalogarchiv enthält den Stand vor der Migration und ist kein laufendes Journalbackup. Niemals einen alten Journalstand unbesehen über neuere Schreibvorgänge zurückspielen.

Alle Tests des Releases sind lokal mit simuliertem Yuvomi bzw. lokalen Testservern. Das HA-Testmodul benötigt Linux/Python >=3.14.2 mit HA 2026.10.2; die Modell-, Alexa- und produktive HA-Abnahme ist durch diese lokalen Tests nicht ersetzt. Die Installation und Tests in dieser Anleitung führt der Betreiber bewusst selbst aus.

Zentrale Systemprompt-Hinweise siehe PROMPT_1.4.2.md. Keine produktive Promptänderung erfolgt automatisch.
