# Implementierungsplan 1.4.4 – Menüplanung und Kontextoptimierung

> Umsetzung vom 26.10.2026: Lokale Implementierung ausdrücklich freigegeben; eigene LLM-API jetzt enthalten. Ältere „nur Analyse“-/„später freigeben“-Passagen unten dokumentieren den vorausgehenden Entscheidungsstand. Verbindlicher tatsächlicher Umfang, Grenzen, Konfiguration und neue Referenzmessungen: [SETUP_1.4.4.md](SETUP_1.4.4.md), [TEST_REPORT_1.4.4.md](TEST_REPORT_1.4.4.md). Kein Push/Tag/Release oder produktiver Eingriff.


**Nur Analyse und Planung.** Ausgangspunkt ist der unveränderte lokale 1.4.3-Code. In dieser Phase keine neue Funktion, keine Versionserhöhung, kein Commit/Push/Tag/Release und keine Installation. [MENU_PLANNING.md](MENU_PLANNING.md) ist die fachliche Vorgabe; Gemma stellt den Plan zusammen, die Integration sichert ihn deterministisch ab.

## 1. Technischer Ist-Zustand

| Komponente 1.4.3 | Vorhanden / wiederverwendbar | Für Menüplanung fehlt |
| --- | --- | --- |
| runtime.py / llm.py | Native HA-LLM-Plattform, Schema-/Formatprüfung, Toolfreigaben bei jedem Aufruf, Aufrufer-/Kontextbindung, unbekannte Werkzeuge mit HA-Bestätigung | Zweckgebundene Planungskontexte und Menü-Schreibregeln; kein Zugriff auf Originaläußerung/Conversation-Historie allein aus den bestehenden Toolargumenten garantiert |
| shopping.py / purchasing.py | Gleiche Einzel-/Sammellogik, Bestandsprüfung, Notizen, Listensperren, Kategorienvalidierung, persistente Belege | Nicht als Menü-Synchronisation verwendbar: ensure/increase addieren und kennen keine Planrevision |
| shopping_api.py | Beschränkter Same-Origin-Transport, 8 s, 2 MiB, keine Weiterleitungen, feste Schreibpfade, POST-Idempotency-Key | Enger MealAPI-Adapter und gezielter Pantry-Leser, keine vom Modell wählbaren URLs/Methoden |
| recipes.py / recipe_engine.py | Aktuelle Rezepte, exakte Varianten, Zutaten, strukturierte Menümetadaten, Portionenbasis; persistente Rezeptschreibbelege | Kein Mahlzeitenplan, keine tatsächlichen Essensportionen, keine Anwesenheits-/Aufwärmzuordnung |
| quantities.py | Decimal-basierte Normalisierung klarer Zahlen/Einheiten | Echte Skalierung, planbezogene Zusatzportionen und Packungsprüfung. add_or_replace darf nicht als Multiplikation verwendet werden |
| journal.py / persistence.py / journal_ui.py | Atomarer HA-Store, Schema 2, alte Migration erhalten, begrenzte Belege, Neustartbarrieren, rein lesende Prüfung | Neue Ressourcen meals und deren Beobachter; langfristige abgeschlossene Sync-Belege außerhalb des verdrängbaren Rings |
| config_flow.py | Optionen für Werkzeuge, Bestätigungen und Ausführungen | Editierbare Planungskonfiguration mit Revisionen/Hilfetexten, Kalender-Allowlist, Profilen und Validierung |

Die vier Rezeptwerkzeuge bleiben deaktiviert, bis sie explizit gewählt werden. Neue Menüwerkzeuge bleiben ebenfalls aus. Bestehende Config Entries, Tokens und Freigaben werden nicht neu angelegt oder automatisch erweitert. Aufgaben, Kalender und sämtliche bisherigen Werkzeugnamen/Parameterverträge bleiben kompatibel.

## 2. API-Bestandsaufnahme mit Belegstufen

Referenz ist offizielles Yuvomi 2.79.0, Commit a6812d433fc25a0f8bf1389542e68111f9169a82. Die relevanten unveränderten Dateien wurden von GitHub bytegleich verifiziert. Quellen/Hashes und Testbefehl: [MENU_API_EVIDENCE_1.4.4.json](MENU_API_EVIDENCE_1.4.4.json). Die produktive Instanz wurde nicht kontaktiert.

Belegstufen: **Q** = Quellcode/OpenAPI geprüft; **T** = durch vorhandene lokale Tests für den genannten Teil belegt; **P** = in späterer kombinierter HA-/LM-Studio-/Yuvomi-Testinstanz zu verifizieren. Ein T für Middleware ist kein vollständiger Beleg des realen Deployments.

| Eigenschaft | Befund und Konsequenz | Beleg |
| --- | --- | --- |
| GET /api/v1/meals?week=YYYY-MM-DD | Liefert eine Yuvomi-Haushaltswoche mit weekStart/weekEnd, nicht unseren beliebigen Planungszeitraum. Wochenstart unterstützt dort Montag/Sonntag/Samstag. Für Mi–Di zwei/mehr Abfragen, über Grenzen nach Rückgabe iterieren, nach IDs deduplizieren und exakt nach Ziel-/Vorperiode filtern | Q; T test-meals-routes.js:151,174; P echte HA-Adapterabdeckung |
| GET-Nebenwirkung | Materialisiert fehlende Vorkommen von Wiederholungsserien. Kein fachlich neuer HA-Planauftrag, aber serverseitig nicht garantiert ohne Datenbankschreibzugriff | Q; T :187; P Annotationen/Bedienhinweise |
| POST /meals | Erstellt einzelne Mahlzeit mit date, meal_type, title, optional notes/recipe_id/recipe_url/cook_user_id/ingredients und optionaler Wiederholungsserie | Q/T; für Wochenplanung bevorzugt apply-plan, niemals repeat_weekly automatisch setzen |
| POST /meals/apply-plan | Mehrere Zuweisungen in einer DB-Transaktion; ohne Flags additiv selbst bei belegten Slots | Q; T :202–268 |
| skip_occupied:true | Schützt gespeicherte und noch nicht materialisierte Serienvorkommen; liefert skipped samt Assignmentindex. Beide Flags gleichzeitig sind 400 | Q; T :293–468 |
| Doppelte Assignments | Mehrere Zuweisungen desselben vorher freien Datum-/Typ-Slots werden trotz skip_occupied alle gespeichert. HA muss sie vor dem Schreiben ablehnen | Q; T :321 |
| replace_existing:true | Löscht alle Einträge in jedem genannten Slot, berücksichtigt Serienausnahmen und erzeugt neue Mahlzeit-IDs. Andere Slots bleiben stehen | Q; T :240,268. Keine atomare erwartete-ID-/Revisionsvorbedingung; externe Race-Bedingung bleibt |
| PUT /meals/:id | Gezielte Feldänderung, ausgelassene Felder bleiben erhalten; im normalen Einzelpfad werden Zutaten nicht ersetzt. scope=series verändert Template und andere Instanzen | Q; T Felder/Serie :490,502; Einzelpfad-Zutaten-Nichtänderung zusätzlich in neuer Adapterregression prüfen |
| Datum / Typ | Datumsstrings YYYY-MM-DD; lokale Kalendertage. Mealtypen breakfast/lunch/dinner/snack. HA muss Kalendergültigkeit strenger prüfen und darf sich nicht auf lockere Regex-/Servernormalisierung verlassen | Q/T; P DST/Agentauflösung |
| Portionen | Kein natives basisportionen-/tatsächliche-Portionen-Feld im geprüften Meals-/Recipe-Schreibvertrag | Q; geplante Berechnungen/Zuordnungen versioniert in Yuvomi-Mahlzeitnotizen, nicht in einer Rezeptkopie |
| Zutaten / Rezeptverweis | Eigene meal_ingredients oder recipe_id mit späterem Rezeptzutaten-Fallback beim Transfer. Titel und Mengen werden serverseitig gekürzt/normalisiert, daher vorher streng validieren | Q; T Transfer-/Fallbackfälle am Ende von test-meals-routes.js |
| Transferpfade | /meals/:id/to-shopping-list und /meals/week-to-shopping-list nutzen Zutaten-/Übertragungsflags. Sie kennen nicht unsere Vorratsprüfung, Portionenskalierung oder Bestätigungsrevision | Q/T lokale Transferfälle; nicht bei Planerstellung aufrufen, nicht als vollständige neue Synchronisation ausgeben |
| POST-Idempotenz | Schlüssel pro Benutzer, Methode/Pfad/kanonischem Body; gleiche Anfrage wird wiedergegeben, andere Anfrage/parallel noch offen → 409; 24 h TTL, Wiederfreigabe verwaister Anfrage nach 60 s | Q; T test-idempotency.js mit echtem Tasks-Router und Middleware. P kombinierter Meals-/Vollserver-Timeouttest |
| Rechte | /meals und /recipes gehören meals; write schließt read ein. Einkauf braucht shopping:write, Vorrat pantry:read. Keine zusätzlichen Familienrechte nötig, wenn Profile lokal konfiguriert werden | Q; P vollständige Token-/Rollenmatrix im echten HA-Testpfad |
| Konkurrenz | Kein If-Match/CAS in apply-plan oder Einzel-PUT. HA-Sperren schützen nur diese Integration, nicht andere Clients | Q; P parallele externe Testclients |

**Ausgeführt:** 98 vorhandene Upstream-Tests erfolgreich (Node 24.19.0):

```text
node --loader ./test/test-browser-loader.mjs --experimental-sqlite --test test/test-meals-routes.js test/test-meals-recipe-entry.js test/test-idempotency.js
```

Die Tests verwenden In-Memory-Datenbanken und lokale Loopback-Server. Meals-Routen/UI und globale Idempotenz werden damit getrennt geprüft; das ist kein Test einer produktiven Installation. Der Browser-Loader ist für den UI-Test erforderlich. Relevante Meals-/Middleware-Dateien entsprechen dem geprüften Commit; ein früherer lokaler Shopping-Patch im Nachbarprojekt wurde weder verändert noch als neuer Produktivstand veröffentlicht.

HA-Kalenderverträge wurden zusätzlich gegen die Originalquellen 2026.10.2 geprüft (calendar/__init__.py und services.py). Tatsächliche Entity-Leserechte, Aufruferkontext und Conversation-Isolation bleiben P.

## 3. Empfohlene neue Werkzeuge

Drei Planungswerkzeuge; ein viertes ausschließlich für die getrennte Einkaufssynchronisation. Die Vereinfachung benötigt keine weiteren Werkzeuge für Chargen, Reservierung, Restmengen oder Verbrauch. Eine Verringerung auf zwei würde Lesen mit schwerem Kontext oder Speichern vermischen und wird nicht empfohlen. Entwürfe ihrer vollständigen Schemas: [MENU_TOOL_CONTRACT_DRAFT_1.4.4.json](MENU_TOOL_CONTRACT_DRAFT_1.4.4.json). Sie sind Spezifikation, werden nicht registriert oder freigegeben.

| Werkzeug | Rolle |
| --- | --- |
| get_menu_planning_context | Nur bei explizitem Planungs-/Änderungs-/Vorschlagsauftrag: zweckgebundenen Kontext einschließlich vollständiger relevanter Rezepte, Regeln/Revision, Profile, Anwesenheit und Ziel-/Vorperiode laden. create_period / replace_day / suggest_day begrenzen die Befugnis; Vorschläge bleiben schreibgeschützt |
| save_menu_plan | Vom Modell ausgewählte Zuweisungen prüfen und direkt innerhalb des gebundenen Umfangs speichern. Neue freie Slots mit skip_occupied; ausdrückliche Tagesersetzung nur im abgesicherten Einzel-Slot-Pfad. Kein allgemeines replace_existing-Flag für das Modell |
| get_menu_plan | Bereits gespeicherte Mahlzeiten lesen; kurze Tages-/Heute-morgen-Ausgabe als Vorgabe, vollständig nur ausdrücklich. Kein voller Planungskontext |
| sync_menu_plan_shopping | Optionaler eigener Umsetzungsschritt: preview nach ausdrücklich angeforderter Vorratsprüfung, commit nur nach vertrauenswürdiger separater Bestätigung. Kein Aufruf durch save_menu_plan |

Es werden keine Werkzeuge für jedes Planungsdatum, Familienmitglied oder einzelne Regel erzeugt. Keine generische REST-Brücke, kein zweites Kalenderlesewerkzeug und keine Funktion entfernt. Bereits freigegebene Werkzeuge bleiben in der verfügbaren Liste; Tokenzahlen werden nicht durch heimliches Wegfiltern günstiger gerechnet.

Für neue Meal-GET-Werkzeuge Annotationen explizit prüfen: die Servermaterialisierung macht eine strikte read_only-Zusage problematisch. Empfehlung: diese besondere Wirkung offen dokumentieren und read_only nicht pauschal behaupten; Cachepolitik und Annotationen nötigenfalls entkoppeln. Destruktive Tagesersetzung verlangt einen gebundenen Änderungsumfang und darf keine pauschale unknown-tool-Bestätigung der gesamten Menüplanung erzwingen. Unbekannte/generische Werkzeuge behalten unverändert ihre Bestätigung.

## 4. Schlanke Modulaufteilung und Datenfluss

Vorgesehene abgegrenzte Verantwortlichkeiten, keine allgemeine Workflow-Engine:

- `planning_config.py` und `planning_ui.py`: versionierter Store, Defaultwerte/Revision, UI-Selektoren, Quellenprüfung. Family-/Calendar-Regeln ausschließlich hier, nicht als statischer Prompttext.
- `meals_api.py`: nur feste GET-meals- und POST-apply-plan-Pfade; Einzel-PUT erst für ausdrücklich geprüfte geeignete Änderungen. Vollständige Bereichsabdeckung, IDs und Antworten validieren; bestehendes Transportverhalten wiederverwenden.
- `planning_context.py`: tatsächlicher Planungseinstieg, Perioden, Datenbeschaffung, Kalender-Allowlist, Ablaufzeit/Quellenfingerprints und aufgelöste Fakten. Rezepte werden aus RecipeAPI gelesen; keine Rezeptliste persistieren.
- `menu_planning.py`: Kontext-/Auftragsbindung, harte Validierung der **Modellwahl**, Decimal-/Portionszuordnung, Serialisierung und Journal. Kein eigener Rezeptauswahlalgorithmus.
- Später `menu_shopping.py`: getrennte Vorrats-/Packungs-/Differenzvorschau und dauerhafte Sync-Belege; keine zweite Einkaufsverarbeitung, sondern sorgfältig gebundene Übergabe an Purchasing mit stabilen Einzelschlüsseln.

Ablauf: eindeutiger Benutzerauftrag → isolierte Planungsunterhaltung mit demselben Gemma → Kontextwerkzeug → Modell wählt Rezepte/Verteilung und vorgeschlagene Zusatzportionen → save_menu_plan prüft alle Zuweisungen/Quellen → durable prepared → begrenzter REST-Aufruf → Antwort/Belege prüfen → kurze Ergebnismeldung. Fehler dürfen eine begrenzte Modellkorrektur innerhalb desselben gültigen Kontexts auslösen, keine ungeprüfte Schleife und keinen deterministischen Ersatzplan.

Das optionale Feld requested_recipe im Kontextschema begrenzt die Auswahl auf das exakt genannte Rezept; mehrere passende Varianten ergeben Rückfrage. Bestehende Rezeptwerkzeuge bleiben unverändert. Der Schemaentwurf hat vorläufig höchstens 64 Assignments; UI-Last-/Bereichsgrenzen müssen dazu konsistent festgelegt werden, ohne eine feste Sieben-Tage-Logik einzubauen.

### Kontext-/Alexa-Abhängigkeit

`async_get_tools()` ist synchron; dort keine Store-/Netzwerk-/Kalenderabfrage und keine vollständigen Regeln einbetten. Lokale kurze Beschreibungen/Schemaansichten können bereits beim Runtime-Aufbau vorbereitet werden. Vollständige Planungseingaben entstehen nur im asynchronen Kontextwerkzeug.

Heavy-Toolantworten können im Agentenverlauf verbleiben. Deshalb vor Implementierung testen, ob der bestehende Agent/Assist Router eine eigene kurzlebige Conversation-ID für Planungsaufträge zulässt. Derselbe LM-Studio-/Gemma-Backend bleibt ausreichend; kein zusätzlicher Container und kein anderes Modell nötig. Falls Host-/Routeränderung nötig ist, als eigener kleiner Integrationsschritt ausweisen, nicht heimlich aus MCP heraus fremde Historien löschen oder Nachrichten versenden.

Lange Bearbeitung kann das Alexa-Zeitfenster überschreiten. Das bestehende 8-s-REST-Limit ist kein LLM-Planungszeitlimit. Einen Auftrag dann mit stabiler Vorgangs-ID als „wird erstellt“ quittieren und anschließend eindeutig abschließen/statuslesbar machen. Eine erneute Alexa-Anfrage darf keinen zweiten Modell-/Schreibvorgang starten. Ein unbegrenzt wartender blockierender Toolaufruf und eine Erfolgsmeldung vor Abschluss sind keine Lösung. Mechanismus zur Hintergrundfortsetzung und Sprachrückmeldung ist ein explizites Gate; keine versprochene Alexa-Fertigmeldung ohne getesteten Kanal.

## 5. Persistenz und migrationssichere Belege

Bestehender HA-Ausführungsstore/Schema-2-Daten und alle offenen Zustände bleiben erhalten. Konservativ einen neuen eng geprüften `resource: meals`-Belegtyp für feste Operationen ergänzen; alte Shopping-/Recipe-Belege unverändert laden. Journal-UI dispatcht nur zu expliziten lesenden Beobachtern; ein unbekannter Ressourcentyp darf nicht im Einkaufsbeobachter landen. Ein Downgrade darf neue Formen ablehnen statt sie zu verwerfen.

Empfehlung für die zusätzliche Planungspersistenz: ein atomarer HA-Store `yuvomi_mcp.<entry_id>.planning` mit eigener interner Version 1. Enthalten sind Konfiguration/Revision, minimale Auftrags- und Quellenfingerprints sowie kompakte abgeschlossene Synchronisationsbelege. Gemeinsame Zugriffssperre gegen verlorene Änderungen zwischen Optionsflow und Synchronisation; optional spätere Aufteilung, falls Größenmessung sie rechtfertigt. Kein separater Rezept-, Kategorie- oder Vorratskatalog, keine dauerhaften Rohkalenderkopien. Konfiguration nur in Optionsbearbeitung oder tatsächlichen Planungs-/Sync-Aktionen laden, nicht in gewöhnlichen Sprachbefehlen.

Kurzlebige volle Kontextdaten nach Ende/Ablauf freigeben; nach Neustart neuen Kontext verlangen. Durable vorbereitete/unklare Schreibbelege bleiben bestehen und werden ausschließlich lesend geprüft. Abgeschlossene Sync-Identitäten müssen länger als der 512er-/48h-Verdrängungsring des bisherigen Journals erhalten bleiben; sonst wäre derselbe alte Plan erneut addierbar. Bei Kapazitätsgrenze sicher stoppen, nie unbemerkt abgeschlossenes Sync-Wissen löschen.

Minimaler Meal-Beleg: authentifizierter Aufruferhash, ursprüngliche Auftragsidentität, Kontext/Revision, exakter Datums-/Slotumfang, erwarteter Vorzustand, kanonischer Zielbody, Idempotency-Key, Einzel-/Batchstatus und beobachtete IDs. Titel/Kategorien in Belegen sind Transaktionsnachweise, kein Produktgedächtnis. Minimale Sync-Identität: Plan-/Kochslotrevision, Ziel-Liste, Zutatenidentität und genehmigter Vorschauhash; für Differenzprüfung die belegte Beitragsmenge und das zugehörige Einkaufsziel erhalten.

Für Alexa-Retries mit neuen IDs und anderer Modellwahl reicht ein Body-Fingerprint nicht. Bevorzugt ursprüngliche Request-ID vom vertrauenswürdigen Router/Agenten durchreichen, laufenden Auftrag je Aufrufer/Periode/Änderungsziel wiederfinden und Ergebnis weiterverwenden. Fehlt diese Information, konservative Wiederholungsbarriere und `request_unclear` statt erneuter beliebiger Tagesersetzung; absichtlich neue Alternativwünsche bleiben ohne stabile Eingangsidentität nicht perfekt unterscheidbar. Das ist eine bestehende technische Grenze, keine Exactly-once-Zusage.

## 6. Vereinfachte Aufwärmportionen und Yuvomi-Abbildung

Familienprofile und ausdrücklich gewählte Kalender liefern den datums-/personenbezogenen Bedarf. Gemma wählt ein akzeptiertes wiederaufwärmbares Gericht ein bis zwei lokale Kalendertage vorher. Die Integration berechnet heutige plus geplante Zusatzportionen und skaliert **nur die Mahlzeitzutaten des Kochtags**; ursprüngliches Rezept und Rezeptbasis bleiben unverändert. Beispiel Mittwoch drei plus Donnerstag zwei Kinder = fünf kochen bei Basis vier, Faktor 5/4. Kein Mindestwert vier.

Schlanke Zuordnung im Yuvomi-Mahlzeitnotizblock: Quellslot/Rezept und `(Zieldatum, Zieltyp, Profil-ID, Portionen)`. Ein Zielbedarf darf nur einmal zugeordnet sein; Spiegelung im Aufwärmeintrag ist dieselbe Planung, keine zweite Buchung. Keine Chargen-IDs, Restmengen, Verbrauchsstände, tatsächlichen Resten oder allgemeine Reservierungsverwaltung. Bei Quellenänderung abhängige Tage erkennen, ohne sie ungefragt umzuschreiben. Über Periodengrenzen die relevanten maximal zwei Nachbartage lesen; die Regel unmittelbar benachbarter Perioden und konfigurierte Ausnahmen bleiben erhalten.

Notizformat und Erhaltung freier Texte sind in MENU_PLANNING Abschnitt 6 spezifiziert. Kochtag speichert skalierte eigene Zutaten und native recipe_id; Aufwärmtag exakten Titel und Herkunft/Empfänger in Notizen, aber keine native recipe_id und keine eigenen Einkaufszutaten. Damit kein Rezeptzutaten-Fallback beim späteren nativen Transfer. Nachteil: keine native Rezept-/Bildverknüpfung am Aufwärmeintrag. Offizieller GUI-Code zeigt Notizen nur als Text im Detail/Editor, nicht als eigenes Portionsfeld. Diese serverneutrale Variante ist bevorzugt; Parser, Mobilanzeige, Quelle/Reheat und beide Transferpfade in Tests abnehmen. Kein Nullmengen-/Dummyzutaten-Workaround.

Für Kochtage gilt gesamte Koch-/Back-/Wartezeit. Für zeitlimitierte Aufwärmtage keine kurze Zeit erfinden; nachvollziehbare Angaben oder Rückfrage, da kein eigenes Metadatenfeld vorhanden ist. Allgemeines „Resten“ bleibt ohne Bestandsnachweis zulässig und führt keine Verbrauchsbuchhaltung ein.

## 7. Direkte Tagesersetzung: akzeptierter optimistischer Schutz

Ein reines Einzel-PUT hält die ID, lässt aber alte eigene Zutaten bestehen. Mehrstufiges Zutatenlöschen/-anlegen ist nicht atomar und wird nicht als sichere Standardlösung empfohlen. `scope=series` ist unzulässig, wenn nur ein Tag geändert werden soll.

Für eine vollständige Rezept-/Zutatenersetzung passt ein einzelnes `apply-plan` mit replace_existing und genau einem gebundenen Datum/Typ, nachdem die einzige erwartete Mahlzeit nochmals vollständig verglichen wurde. Andere Tage bleiben unberührt, neue ID wird transparent im Beleg gespeichert, freie manuelle Notizen werden erhaltend behandelt. Ein inzwischen ungültiger gespeicherter Koch kann bei Neuanlage einen Serverfehler auslösen; nicht still entfernen.

Grenze: replace_existing kann einen parallel hinzugekommenen Eintrag im selben Slot mitlöschen. Die API bietet keine atomare expected_ids-/Fingerprint-Prüfung. **Entschieden:** Das verbleibende theoretische Risiko ist für die private Familiennutzung akzeptiert. Eine eindeutige ausdrückliche Tagesänderung erlaubt direkte Ersetzung ohne weitere Bestätigung; keine neue serverseitige CAS-API. Vor I/O nach Möglichkeit aktuell lesen/vergleichen; ein bereits bemerkter Konflikt stoppt. Das Race-Fenster danach bleibt dokumentiert, ebenso mögliche Konkurrenz weiterer Clients. HA-Serialisierung beseitigt es nicht. Keine blinden Retries, keine Serienänderung und kein falscher Gesamterfolg.

## 8. Getrennte Einkaufsintegration

Planung schreibt nie nach shopping/pantry. Für später explizit angeforderte Vorratsprüfung liefert Yuvomi Pantry-Chargen mit Menge/Einheit; eine Menge ist nicht automatisch eine sichere Packungsgrößenumrechnung. Vor Umsetzung den tatsächlichen Pantry-/Produkt-/Zuordnungsvertrag separat mit Quellen und Fixtures prüfen. Kein „Dose = 400 g“, keine unscharfe Produktidentität und kein automatisches Anlegen eines Produktkatalogs in HA.

Nur explizit bestätigte Zutaten-/Pantry-Zuordnungen bzw. eindeutig unterstützte IDs/Einheiten verwenden. Mehrere Bedarfe dürfen denselben bekannten Bestand nicht mehrfach abziehen; Vorratsanteile innerhalb der Vorschau einmalig zuordnen. Unbekannte Bestände oder Packungsgrößen bleiben sichtbar unbekannt. Es wird kein realer Vorrat durch diese Prüfung verbraucht oder reserviert.

`sync_menu_plan_shopping` preview bindet Planrevision, Quellslots und Zusatzportionen, skalierte Mengen, Zielliste, Vorrats-/Bestandsfingerprints und offene Fragen. commit setzt eine eigene vertrauenswürdige Bestätigung voraus. Bestehenden HA-Optionsflow für exakte Aktion/Argumente wiederverwenden, aber die neue bekannte Sync-Funktion muss ihren Commit selbst absichern; KNOWN_TOOLS darf diese Bestätigung nicht umgehen. Keine neue generische Schreibfreigabe und kein LLM-Feld als Zustimmungsbeweis.

Bereits skalierte eigene Kochtag-Zutaten werden nicht erneut multipliziert; gegen den gespeicherten Quellen-/Portionsstand prüfen. Gleiche bestätigte Revision/Kochslot/Zutat/Liste liefert den Beleg statt einer erneuten Addition. Geänderter Plan erzeugt eine Differenzvorschau unter Einbezug früherer Überträge. Bereits konsumierte, abgehakte, gelöschte oder fremd veränderte Einkaufsartikel erlauben keine sichere automatische Subtraktion; dann manuell/gezielt klären. Eine neue Planrevision darf nicht als pauschale Erlaubnis zur erneuten Volladdition gelten. Teilfehler erhalten Einzelstatus, unklare Zustände blockieren Folgeaktionen. Kein automatischer Rollback fremder Beiträge.

## 9. Implementierungsreihenfolge mit Abnahme-Gates

| Phase | Änderung | Geeignete Prüfung / Gate |
| --- | --- | --- |
| 0: Entscheidungen | Zielkonfiguration, Kontext-Isolation/Agent und Request-ID-Übergabe testen; vereinfachte Aufwärmabbildung und akzeptierten Ein-Slot-Konfliktschutz zugrunde legen | Kein 1.4.4-Code vor Freigabe dieses Plans |
| 1: Kontextoptimierung | Nur Beschreibungen und getrennt bewerteter Kurzprompt, unveränderte Namen/Schemas/Freigaben. Bekannte Remote-Schemata vor Beschreibungsoverlay vergleichen, unbekannte Varianten erhalten | Strukturvergleich + alle 1.4.3-Regressionen + echte Gemma-Toolwahl; LM-Studio-„hallo“-Vergleich |
| 2: Planungskonfiguration | Store/UI mit Defaults, Profil-/Kalenderreferenzen, Revisionen und Validierung | Frisch-/Altentry, atomare Speicherung, unvollständige Konfiguration, Kalenderrechte, Reload; keine neue Werkzeugfreigabe |
| 3: Kontext und Lesen | MealAPI, frei konfigurierbare Perioden, vorige Periode, isolierter Vollkontext und get_menu_plan | Vollständige Bereichsabdeckung, Serien/GET-Materialisierung, normaler Sprachbefehl mit 0 Planungs-/Kalenderlesevorgängen |
| 4: Modellplanung und Speichern | Gemma wählt; Backend validiert Portionen/Zeit/Präferenzen und schreibt freie Slots direkt mit Journal/Idempotenz | Keine Bestätigung für eindeutige neue Menüs, kein Einkaufszugriff, Teil-/Timeout-/Neustarttests, begrenzte Modellkorrektur |
| 5: Einzeländerung | Gezielter Ein-Slot-Ersatz mit akzeptiertem externem Restrisiko; Vorschläge/Lesen strikt ohne beabsichtigte Planänderung | Andere Tage/Serien bleiben gleich, Zutaten/Notizen korrekt, externe Konkurrenz offen getestet |
| 6: Getrennter Einkauf | Nur falls ausdrücklich im Umfang freigegeben: Pantry-/Packungsprüfung, Vorschau/Bestätigung, dauerhafte Sync-Belege und Differenzen | Keine Doppeladdition auch nach Journalverdrängung, Planänderung, Neustart und neuem Retry; keine automatische Vorratsänderung |
| 7: Freigabe | Versionsfelder/Changelog erst jetzt gezielt auf 1.4.4; lokale Tests, Linux/HA 2026.10.2, HACS/hassfest, bewusste Testliste | Erst danach separat Commit/Push/Tag/Release freigeben; keine produktive Automatik |

Aufgabe der Implementierung ist vollständige KI-gestützte Planung; diese Phasen trennen Abnahmen, nicht eine Umdeutung in einen regelbasierten Generator. Falls Einkauf wegen offener Packungs-/Identitätsverträge noch nicht freigegeben werden kann, den Sync-Toolentwurf nicht als funktionsfähiges Werkzeug exponieren.

## 10. Testkonzept

| Bereich | Wesentliche Fälle |
| --- | --- |
| Perioden | Mi–Di/Mo–Fr-Vorgabe; andere Starttage, freie Tagesauswahl, nicht 7 Tage, Jahres-/Monatswechsel, nächste Periode vs ISO-Woche, Sommerzeit 23/25 h, mehrfach gleicher Wochentag → Rückfrage |
| Bestehender Bestand | Erstplanung überschreibt nichts; belegte/mehrfach belegte Slots, Serien ohne vorherige Materialisierung, bekannte Lücken, skip-Ergebnis/201 mit leerem data, doppelte Modellzuweisungen abgewiesen |
| Direkte Änderung | Bestimmter Tag/benanntes Rezept, eindeutige ID/Variante, ausdrücklich gewünschte Alternative; Vorschlag und Lesen schreiben nichts. Kein anderer Tag/kein Serienumfang geändert; ingredient-PUT-Falle und Vollersatz prüfen |
| Wiederholungen | Vergleich unmittelbar benachbarter Perioden trotz 1 bzw. >7 Tage Abstand; Resten-/Notfall-ID-Ausnahmen; keine unbenannte Ausnahme für Aufwärmen über Grenze; alte freie Titel/gelöschte Vorgeschichte kenntlich |
| Modellwahl | Gemma erhält vollständige relevante Auswahl und wählt selbst. Keine versteckte Backend-Auswahl bei fehlerhaftem Modellplan. Reparatur nur begrenzt, harte Fehler präzise, Rezept-/Kalendertexte als Daten |
| Portionen | Basis 4, tatsächliche Mahlzeit 1/2/3 Portionen; Faktoren und Zusatzbedarfe, 5/4-Zutatenfaktor, einmal zugeordneter Zielbedarf, ungeeignetes Gericht/Abneigung, 2-Tage-Grenze, extern geänderte Quellslots/Zuordnungen |
| Zeit / Resten | Ganze Koch-/Back-/Wartezeit pro Tageslimit; unbekannte Aufwärmzeit nicht geraten; Resten ohne Bestandsnachweis zulässig, keine Phantomzutaten, Notfallersatz nur im erlaubten Umfang |
| Kalender | Exakte Allowlist, keine Area-/Label-Expansion, Registry-Umbenennung/Entfernung, fehlende Entity-Leserechte, ganztägig/exklusives Ende, Serientermine, Gleichrangkonflikt, notwendiger Kalender ausgefallen, kein Match → feste Regel |
| Kontext | Normaler „hallo“/Alexa-Einkauf lädt 0 Planungsdaten. Reiner Planlesebefehl lädt 0 Profile/Kalender. Planung isoliert; nach Ende kein Vollkontext im gewöhnlichen Verlauf. Kontextablauf und Revision geändert → kein Schreiben |
| Sicherheit | Token meals:read/write; shopping/pantry nur in explizitem Sync-Pfad. Neue Werkzeuge aus, Rechteentzug bei gehaltenem Tool/Reload, unveränderte Bestätigung unbekannter Tools, kein bestätigtes Bool aus LLM |
| Persistenz | prepared vor I/O, Speicherfehler vor/nach Antwort, Timeout nach Commit, Neustart, parallele Aufrufe/überlappende Perioden, 409/in-flight/TTL, Kontext-/Request-ID-Replay ohne neue Modellentscheidung, keine blinde Wiederholung |
| Teilzustände | Cook geschrieben/reheat geskippt, falsche/fehlende Rückgabe-IDs, nur ein Teil belegt, externe Änderung zwischen Prüfung und Schreiben, manuelle Änderung am Metadatenblock. Kein falscher Gesamterfolg oder automatischer gefährlicher Rollback |
| Einkauf | Explizite Vorratsprüfung, unbekannt ≠ 0, Packungsgröße unbekannt, Bestand nicht doppelt verrechnet, Vorschau abgelehnt/veraltet, vertrauenswürdige Bestätigung, gleiche Revision/andere Retry-ID/Neustart, alte Belege aus Ring verdrängt, geänderter Plan nur Differenz |
| Regression / Sprache | Alle 1.4.3-Funktionen und bisherigen Schemas; Gemma-Auswahl/Argumente für Einkauf, Notizen, Termine, Rezepte unverändert zuverlässig; kurze Alexa-Antwort ohne ungefragten Wochenplan |

Die 98 bestandenen Upstream-Tests belegen vorhandene Teile, nicht diese künftige Matrix. Neue 1.4.4-Laufzeittests werden erst in der freigegebenen Implementierung geschrieben; aktuell bleiben Runtime und bestehende Tests unverändert.

## 11. Zusätzliche LLM-API: getrennte spätere Entscheidung

Die Prüfung ist in [LLM_API_ARCHITECTURE_1.4.4.md](LLM_API_ARCHITECTURE_1.4.4.md) dokumentiert: HA 2026.10.2 und der lokale Local-OpenAI-Referenzstand unterstützen mehrere APIs; der Router übergibt nur den Agenten, keine API-Auswahl pro Nachricht. Kombinierte APIs erzeugen zusätzliche Namensräume und bei fortbestehender Legacy-Exposition doppelte Yuvomi-Werkzeuge. Eine optionale eigene API wäre organisatorisch sinnvoll, bietet aber keine automatische Tokenersparnis oder Verlaufsisolation.

**Empfehlung für 1.4.4: bestehende assist-Anbindung unverändert erhalten, zusätzliche API nicht implementieren.** Für eine spätere ausdrücklich freigegebene Umsetzung braucht es einen manuellen Expositionsmodus, unveränderte Runtime-Allowlist, stabile API-IDs, getesteten Reload-/Fehlverfügbarkeitsweg und explizite Agentenauswahl. Keine automatische Neukonfiguration oder Erweiterung der Werkzeugfreigaben.

## 12. Vor Implementierung noch zu klären bzw. zu prüfen

1. **Kontext-/Zeitweg:** isolierte Planungs-Conversation, vertrauenswürdige Request-ID-Übergabe und Alexa-Timeout-/Fortsetzungsverhalten mit bestehendem Agent/Router verbindlich testen. API-Trennung allein löst dies nicht; der derzeitige Router akzeptiert keinen eigenmächtigen Conversation-ID-Wechsel.
2. **Aufwärmabnahme:** bevorzugte Notiz-/Quellslotdarstellung und GUI-/Transferverhalten testen; für zeitlimitierte Aufwärmtage nachvollziehbare Zeitquelle festlegen. Keine offene Entscheidung mehr über Chargen-/Bestandsbuchhaltung: sie entfällt.
3. **Fachliche Einrichtung:** konkrete Profile, erlaubte Kalender, regelmäßiger Aufwärmbedarf, Resten-/Notfall-IDs, Tageszeitlimits und Ausnahmen in der UI einrichten; keine zwingende Quellcodeentscheidung.
4. **Getrennter Einkauf:** Pantry-/Packungs-/Identitätsvertrag sowie vertrauenswürdige Vorschau-Bestätigung vor Umsetzung abnehmen. Vereinfachte Portionen erfordern weiterhin dauerhafte Sync-Belege, aber keine Restenverwaltung.
5. **Beschreibungsabnahme:** neue Messung bei identischem Systemprompt, Modell und Toolfreigaben gegen **6604 vollständige produktive Prompt-Tokens**. 26,4 % sind ausschließlich ein noch nicht implementierter struktureller Entwurf. Neue Planungstools bleiben aus, bis bewusst freigegeben; separate Kurzprompt-/API-Varianten nur separat messen.

Direkte Tagesersetzung und ihr begrenztes Konkurrenzrisiko sind entschieden; CAS-Serverentwicklung ist kein Gate mehr. Die zusätzliche eigene LLM-API ist eine optionale spätere Freigabe, keine Voraussetzung für 1.4.4. Es fehlen keine pauschalen Familien-Bestätigungen für eindeutige Menüaufträge.

## 13. Dokumentationsprüfung dieser Entscheidungsrunde

Nur Spezifikationen/Architektur- und Messnachweise aktualisiert. Nicht-Dokumentationsdateien werden gegen den vor Beginn gesicherten SHA-256-Bestand geprüft; aktuelle Version bleibt 1.4.3. JSON-/Schema-/Linkprüfung, unveränderte bestehende Werkzeugverträge und lokaler Repository-Check gehören zur Abschlussprüfung. Die zuvor ausgeführten 98 Upstream-Tests bleiben Quellenbelege; in dieser reinen Dokumentationsrunde werden keine neuen Laufzeittests oder produktiven Registrierungen behauptet.
