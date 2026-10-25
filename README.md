# Yuvomi MCP 1.4.2 für Home Assistant

Yuvomi 2.79.0 ist die einzige Quelle für Einkaufsnamen, Kategorien, Mengen und Status. Die Integration stellt weiterhin explizit freigegebene Werkzeuge über die native HA-LLM-Plattform bereit. Aufgaben und Kalender laufen unverändert über MCP. Keine Serveränderung, zusätzliche Datenbank oder Installation durch dieses Release.

## Installation über HACS

Repository: [BugsDan/ha-yuvomi-mcp](https://github.com/BugsDan/ha-yuvomi-mcp). Diese Adresse ist für die geplante Veröffentlichung vorgesehen; die lokale Vorbereitung erstellt das Repository noch nicht. Eigenständige Integration, kein offizielles Yuvomi- oder HA-Projekt.

Voraussetzungen: Home Assistant ab 2026.10.2, HACS und ein erreichbarer Yuvomi-Server 2.79.0 mit API-Token. Die getestete HA-API ist auf 2026.10.2 festgelegt; spätere HA-Versionen müssen ihre Kompatibilität in CI/Abnahme bestätigen.

Nach dem ersten veröffentlichten GitHub-Release:

1. HACS → Menü → Benutzerdefinierte Repositories → https://github.com/BugsDan/ha-yuvomi-mcp → Typ **Integration** hinzufügen.
2. **Yuvomi MCP** öffnen, Release auswählen und herunterladen; HA anschließend neu starten.
3. Bei Erstinstallation: Einstellungen → Geräte & Dienste → Integration hinzufügen → **Yuvomi MCP**. Eigene MCP-URL und Token eingeben; `http://yuvomi.example:3015/mcp` ist nur ein Beispielhost.
4. In den Integrationsoptionen nur gewünschte Werkzeuge freigeben. Den nativen Assist-LLM-Werkzeugzugriff des verwendeten Conversation Agents nutzen. HACS allein aktiviert keine neuen Werkzeuge und installiert keinen Conversation Agent.

Bei einer bereits manuell eingerichteten Integration **keinen Config Entry löschen oder neu anlegen**: nach Backup dieselbe Version über HACS erneut herunterladen und neu starten. Domain yuvomi_mcp, Konfiguration, Tokens, Freigaben und .storage-Journal bleiben erhalten. HACS übernimmt die Codeverwaltung, nicht die Yuvomi-Daten. Details und sichere Abnahme: [GitHub-/HACS-Anleitung](docs/GITHUB_HACS.md).

HACS installiert aus dem Quellbaum des veröffentlichten Release-Tags. Die angehängten ZIPs behalten das Layout für manuelle Installation; sie sind nicht als HACS-ZIP-Asset konfiguriert. Ein Tag allein reicht für den vorgesehenen Updateweg nicht: das zugehörige GitHub-Release muss veröffentlicht werden.

## Entwicklung und Veröffentlichung

[CONTRIBUTING.md](CONTRIBUTING.md), [GitHub-/HACS-Anleitung](docs/GITHUB_HACS.md) und [Veröffentlichungsprüfung](docs/PUBLISHING_REVIEW.md). Lizenz: **MIT**, siehe [LICENSE](LICENSE) und [Drittanbieterhinweise](THIRD_PARTY_NOTICES.md). Sicherheitsmeldungen: [SECURITY.md](SECURITY.md).

Git-Tags entsprechen der Anwendungsversion: v1.4.2, später z.B. v1.4.3. Der vorbereitete Tag-Workflow führt die Prüfungen aus und erstellt ausschließlich einen **Release-Entwurf**. Die Veröffentlichung erfolgt nach menschlicher Prüfung. Neue Versionen müssen Manifest, const.VERSION und Projektmetadaten konsistent aktualisieren.

## Einkaufsverarbeitung

Vor neuen Einkaufsaktionen wird der vollständige Bestand der Zielliste einschließlich abgehakter Artikel über REST gelesen. Nur vollständige Namen nach Unicode-NFKC-, Leerraum- und Kleinschreibungsnormalisierung gelten als gleich. Keine Teilwörter, unscharfen Treffer oder Synonyme: Kochschokolade/Schokolade, Thon klein/Thon gross, Mais klein/Mais gross und unterschiedliche Marken bleiben getrennt. Neue Namen werden einschließlich Marke übernommen; äußerer Leerraum wird entfernt. Bei mehreren passenden offenen oder mehreren passenden abgehakten Einträgen wird nichts ausgewählt oder bereinigt. Ein einzelner offener Eintrag hat Vorrang vor alten abgehakten Kopien.

- Offen: Menge addieren (ensure und increase), bei nicht sicher addierbaren Mengen die neue übernehmen und als replaced melden. Keine Dublette und keine automatische Mengenrückfrage.
- Abgehakt: dieselbe ID reaktivieren; Yuvomi-Name und aktuelle Kategorie bleiben erhalten. Alte Mengen werden nicht übernommen: ohne ausdrückliche Menge wird `quantity: "1"` gesetzt. Andere Metadaten bleiben erhalten.
- Unbekannt: KI-Kategorie erforderlich. Eine gültige Kategorie wird übernommen; eindeutige Unicode-/Schreibfehler werden auf einen vorhandenen Namen korrigiert. Ungültige und mehrdeutige Namen werden niemals geschrieben.
- Fehlende Kategorie: `category_required` mit Artikelname und `valid_categories`. Keine stillschweigende Wahl von Sonstiges. Ein korrigierter Aufruf ist möglich. Für Sonstiges muss das Modell diese gültige Kategorie ausdrücklich wählen.
- Bekannte Artikel behalten ihre aktuelle Yuvomi-Kategorie, selbst bei einer falschen Modellangabe. Manuelle Änderungen werden bei der nächsten neuen Anfrage verwendet.

`list_shopping_categories` vor der Kategorisierung nutzen, sofern die aktuellen Namen nicht bereits im Kontext bekannt sind. Dieser Leser und `add_shopping_items` bleiben ausdrücklich freizugebende Werkzeuge. Es wird nichts automatisch aktiviert.

## Einzel- und Sammelwerkzeug

Beide nutzen dieselben Parameter und dieselbe REST-/Journalverarbeitung. Das Sammelwerkzeug verarbeitet höchstens 20 Artikel je Liste mit gemeinsamem Bestands- und Kategorienabruf. Alle Artikel werden vor dem ersten Schreiben geprüft. Fehlende/ungültige Kategorien werden für alle betroffenen Artikel gemeinsam zurückgegeben; zunächst werden keine neuen Schreibaktionen ausgeführt. Bei einem Schreibfehler stoppt die Verarbeitung und meldet pro Artikel Erfolg, Fehler oder `not_executed`.

```json
{"list":"Wocheneinkauf","items":[{"name":"Aubergine","category":"Obst & Gemüse"},{"name":"Avocado","quantity":"2","category":"Obst & Gemüse"}]}
```

Die Kategorien im Beispiel müssen tatsächlich in Yuvomi vorhanden sein. Keine zusätzliche Modellintegration oder automatische Kategorisierung im Hintergrund.

## Mengen

`operation` ist bei beiden Werkzeugen optional und standardmäßig `ensure`. `ensure` und `increase` haben dieselbe Mengenlogik:

- Neu: mit angegebener Freitextmenge anlegen, sonst „1“.
- Offen: neue Menge zur bestehenden addieren, wenn beide eindeutig parsebar und kompatibel sind. Ohne Angabe +1 der sicher erkannten aktuellen Einheit; z.B. 2 Packungen → 3 Packungen. Ist keine Einheit sicher erkennbar, ist die neue Vorgabe „1“.
- Abgehakt: dieselbe ID reaktivieren und die neue Menge setzen (standardmäßig „1“), niemals zur alten addieren.
- Nicht sicher addierbar, unterschiedliche Einheiten oder unbekannte Basis: neue Freitextmenge unverändert übernehmen, action/status replaced und replacement_reason liefern. Keine geratene Umrechnung und keine automatische Mengenrückfrage.
- set: ausdrücklich gewünschte absolute nachträgliche Korrektur; quantity ist erforderlich. status quantity_set bleibt kompatibel, action ist replaced und replacement_reason explicit_set. Ist der Zieltext bereits erreicht, bleibt der Artikel unverändert (already_present/unchanged).

Freitext bleibt bei Neuanlage, Reaktivierung, Ersatz und set einschließlich Unicode und äußerem Leerraum unverändert. Nichtleere Strings bis 256 Zeichen ohne Steuerzeichen sind weiterhin erforderlich. Rechenergebnisse werden dagegen kanonisch formatiert.

Rechenbare Einheiten: reine Zahlen, l/Liter, ml, g, kg, Stück/Stueck/Stk, Packung/Packungen, Flasche/Flaschen, Tube/Tuben und Einheit/Einheiten. Dezimalpunkt/-komma sind möglich. Es gibt keine Einheitenumrechnung: z.B. 2 l plus 200 ml ersetzt durch „200 ml“. Eine ausdrücklich einheitenlose Menge passt rechnerisch nur zu einer einheitenlosen Basis; nur der ausgelassene Default übernimmt eine sicher erkannte aktuelle Einheit.

Beispiele: Chips „1 Packung“ + „2 Packungen“ → „3 Packungen“ (increased); Mayonnaise „1 Packung“ + „2 Tuben“ → „2 Tuben“ (replaced). Ergebnisse liefern old_quantity, new_quantity, quantity, action, status, replacement_reason und quantity_defaulted. So kann Assist „Chips waren bereits vorhanden, von 1 auf 3 Packungen erhöht“ oder „Menge von 1 Packung durch 2 Tuben ersetzt“ sagen.

Von 1.4.0/1.4.1 auf 1.4.2 ist keine neue Datenmigration nötig: Schema 2 und das vollständige Journal bleiben erhalten. Neue optionale Transaktionsfelder speichern ausschließlich den Wiederholungsschutz, keine Produktdatenbank.

## Journal und Migration von 1.3.0

Der aktive HA-Store bleibt `.storage/yuvomi_mcp.<Entry-ID>`. Er enthält nach Migration ausschließlich `schema: 2`, die Yuvomi-URL-Bindung und das Ausführungsjournal. Keine aktive Produktdatenbank, Synonyme, Vorschläge, Bestätigungen oder Kategoriebeobachtungen.

Vor der Umstellung wird der komplette bisherige Schema-1-Speicher einmalig atomar unter `.storage/yuvomi_mcp.<Entry-ID>.catalog_archive_v1` archiviert und zurückgelesen. Erst bei bestätigter Archivierung wird der aktive Speicher auf Journalbetrieb umgestellt. Alle Journaleinträge einschließlich offener/unklarer Vorgänge und alter Ergebnisdaten bleiben unverändert erhalten. Das Archiv wird anschließend nicht mehr als Produktwissen gelesen. Keine Migration schreibt nach Yuvomi oder ändert Config Entry, Token, Listen oder Werkzeugfreigaben.

Bei Archivierungsfehlern, fremder URL, unbekannten Formaten oder widersprüchlichem Archiv bleiben vorhandene Daten erhalten und Einkaufsaktionen gesperrt. Aufgaben und Kalender bleiben verfügbar. Bei frischer Einrichtung oder einem Upgrade ohne Schema-1-Speicher ist kein Produktarchiv nötig. Der äußere HA-Store-Versionswert bleibt 1, damit der alte Speicher lesbar bleibt; die interne Datenversion ist 2.

Die Integrationsoptionen enthalten nur Werkzeugfreigabe, Bestätigung unbekannter Werkzeuge und Ausführungsprüfung. Produktpflege, Import/Export, Synonyme und Kategorievorschläge sind entfernt. Nach vollständigem Löschen eines Yuvomi-Artikels gibt es bewusst kein Produktgedächtnis; ein neuer Aufruf benötigt wieder eine Kategorie.

## Wiederholungsschutz und Grenzen

Schreibvorgänge werden pro Liste innerhalb dieser Integrationsinstanz serialisiert. Vor dem Netzwerkaufruf muss der Journalzustand `prepared` dauerhaft gespeichert sein. Neuanlagen verwenden einen stabilen `Idempotency-Key`. Derselbe Werkzeugvorgang wird aus dem Journal beantwortet, auch nach Neustart; dabei handelt es sich um ein damaliges Ausführungsergebnis, nicht um einen neuen aktuellen Bestandsabruf.

Ein unklarer Ausgang oder ein abgebrochener vorbereiteter Vorgang sperrt die Liste für weitere Einkaufsaktionen. Unter **Konfigurieren → Ausführungen prüfen** wird ausschließlich gelesen, niemals erneut geschrieben. `state_observed` bestätigt nur einen eindeutig beobachteten Zielzustand, nicht die Urheberschaft. Nicht eindeutig auflösbare Fälle bleiben gesperrt; Sicherung und Yuvomi-Zustand prüfen, Journal nicht einfach löschen.

Erkannte identische Vorgänge werden niemals erneut addiert. Identische Requests bleiben über das persistente Journal geschützt. Zusätzlich wird ein neuer Aufruf derselben Produkt-/Mengenabsicht desselben Aufrufers auf derselben Liste innerhalb von 120 Sekunden als replayed zurückgegeben, wenn das offene Ziel noch die quittierte Menge besitzt. ensure/increase, normalisierte numerische Schreibweisen und Einzel-/Sammelaufrufe teilen diese Sperre. Neu entstandene Retry-IDs werden ebenfalls dauerhaft als Replay vermerkt; sie verlängern das ursprüngliche 120-Sekunden-Fenster nicht.

Ohne stabile durchgereichte Alexa-Request-ID sind eine echte identische Nachbestellung und ein Retry mit neuer ID nicht zuverlässig unterscheidbar. Innerhalb des Fensters kann daher eine bewusste identische Nachbestellung unterdrückt werden; bei Bedarf explizit set als absolute Korrektur verwenden. Nach Ablauf des Fensters gelten neue IDs als neue Einkaufswünsche. Ein inzwischen abgehakter oder gelöschter Artikel gilt bei einer neuen ID als neuer Einkaufszyklus; nur die identische ursprüngliche Request-ID wird immer wiedergegeben. Hat sich die Menge eines noch offenen Artikels inzwischen geändert, wird ein erkannter möglicher Retry mit execution_unconfirmed ohne Addition gestoppt. Manuelle Kategorieänderungen bleiben erhalten. Es gibt keine unbegrenzte Erkennung von Retries mit beliebigen neuen IDs und keine Exactly-once-Garantie.

 Das Journal ist auf 512 Vorgänge begrenzt; abgeschlossene Vorgänge können frühestens nach 48 Stunden verdrängt werden, ungeklärte niemals. Bei voller Kapazität wird sicher gestoppt.

Andere Yuvomi-Clients sind nicht Teil der HA-Sperre. Vor PATCH werden Name, Kategorie, Menge und Status erneut geprüft; eine letzte Änderung zwischen Prüfung und Schreiben lässt sich ohne serverseitige atomare Vorbedingung nicht vollständig ausschließen. Gleichzeitige Neuanlagen durch externe Clients können ebenfalls kollidieren. Es gibt keine globale Exactly-once-Garantie. Keine automatische Wiederholung unklarer Aktionen.

## Installation und Abnahme

Siehe [ABNAHME.md](docs/ABNAHME.md) und [RELEASE_1.4.2.md](docs/RELEASE_1.4.2.md). Ein Token mit `shopping:read` und `shopping:write` wird für Einkaufsaktionen benötigt; Rechte werden serverseitig geprüft. Allgemeine REST-Schreibwerkzeuge sind nicht erforderlich. Keine Codeänderung am Assist Router nötig. Hinweise zur Anpassung zentraler Systemprompts: docs/PROMPT_1.4.2.md. Keine HA-Katalog-/Synonymanweisungen oder alten Mengenrückfragen weiterverwenden.
