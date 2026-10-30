# Menüplanung 1.4.4 – fachliche und technische Spezifikation

> Für den lokalen 1.4.5-Stand gilt vorrangig [SETUP_1.4.5.md](SETUP_1.4.5.md). Die nachfolgenden älteren Entwurfs-/RC3-Regeln zu eigenen Aufwärmeinträgen und manuellen Zusatzportionen gelten nicht für den neuen cooking_only-Vertrag.

> Umsetzung vom 26.10.2026: Lokale Implementierung ausdrücklich freigegeben; eigene LLM-API jetzt enthalten. Ältere „nur Analyse“-/„später freigeben“-Passagen unten dokumentieren den vorausgehenden Entscheidungsstand. Verbindlicher tatsächlicher Umfang, Grenzen, Konfiguration und neue Referenzmessungen: [SETUP_1.4.4.md](SETUP_1.4.4.md), [TEST_REPORT_1.4.4.md](TEST_REPORT_1.4.4.md). Kein Push/Tag/Release oder produktiver Eingriff.


**Status: ausschließlich Spezifikation auf Basis des lokalen 1.4.3-Stands; Architekturentscheidungen vom 25.10.2026 eingearbeitet.** Keine Implementierung, Versionsänderung, Konfigurationsmigration oder produktive Aktion. Bestandsaufnahme und Phasen stehen in [PLAN_1.4.4.md](PLAN_1.4.4.md); API-Nachweise in [MENU_API_EVIDENCE_1.4.4.json](MENU_API_EVIDENCE_1.4.4.json).

## 1. Architektur und Zuständigkeit

Das lokale Sprachmodell (aktuell Gemma 4 12B über LM Studio) stellt den Wochenmenüplan zusammen. Es wählt geeignete Gerichte, berücksichtigt Vorlieben und Abwechslung und verteilt Kochen, Aufwärmen und Resten sinnvoll. Es darf bei dieser ausdrücklich ausgelösten Aufgabe die vollständigen relevanten Rezepte, Familienprofile, Anwesenheitsinformationen und Regeln erhalten. Höherer Tokenverbrauch und längere Bearbeitungszeit sind hier akzeptabel.

Die Integration beschafft Daten, löst Daten/IDs eindeutig auf, berechnet Portionen und skalierbare Mengen, prüft harte Regeln, schützt Schreibvorgänge und speichert Ergebnisse. Sie erzeugt keinen eigenen regelbasierten Ersatzplan, kein verstecktes Ranking mit anschließender automatischer Rezeptauswahl und keine zweite Rezeptdatenbank. Gesundheit und Abwechslung bleiben Modellentscheidungen innerhalb der freigegebenen Regeln; eine harte Regelverletzung führt zu einer gezielten Korrekturanforderung oder Rückfrage, niemals zu einer willkürlichen Ersatzwahl der Integration.

Yuvomi bleibt Quelle für Rezepte, ihre Metadaten und gespeicherte Mahlzeiten. HA speichert Planungskonfiguration, Revisionen, kurzlebige Vorgänge und notwendige Ausführungs-/Synchronisationsbelege. Rezept- oder Kalenderkopien werden nicht als dauerhaftes alternatives Wissen gepflegt.

## 2. Bedienkonzept: direkt speichern, Einkauf getrennt

| Anfrage | Verhalten |
| --- | --- |
| „Erstelle den Menüplan für nächste Woche.“ | Periode bestimmen, relevante Daten laden, Modell planen lassen, hart validieren und freie Slots direkt speichern. Kein vorheriges Vorlesen/Vorschlag und keine zusätzliche Bestätigung für neue eindeutig ausführbare Mahlzeiten |
| „Plane für Donnerstag etwas anderes.“ | Datum/Slot und vorhandenen Eintrag eindeutig bestimmen; Modell wählt eine gültige Alternative. Ausdrücklicher Änderungsauftrag erlaubt die direkte gezielte Ersetzung dieses Slots |
| „Plane am Dienstag Spaghetti Carbonara.“ | Exaktes Rezept eindeutig auflösen und direkt in diesem Slot speichern/ersetzen. Mehrere Varianten oder widersprüchliche Regeln erfordern Rückfrage |
| „Was könntest du stattdessen für Montag vorschlagen?“ | Modell nennt Alternativen, ohne zu schreiben. Ein Vorschlagskontext bekommt keine Schreibbefugnis |
| „Was gibt es am Freitag?“ | Gespeicherten Plan des eindeutigen Datums lesen, ohne volle Familien-/Kalender-/Planungsdaten zu laden |
| „Was gibt es diese Woche?“ | Standardmäßig heute und morgen nennen, soweit in der angefragten Periode. Liegt keiner darin, knapp auf diesen Umstand hinweisen und einen konkreten Tag anbieten, keinen fremden Zeitraum vorlesen |
| „Lies den vollständigen Wochenplan vor.“ | Nur auf diesen ausdrücklichen Wunsch die gesamte angefragte Periode ausgeben |

Erstmalige Wochenplanung überschreibt keinen bestehenden Eintrag. Bereits belegte Slots werden im Planungsdatensatz als unveränderlich markiert; bekannte Lücken können als Teilplan gefüllt werden, belegte Slots werden kurz genannt. Bei unklarer Belegung/mehreren Einträgen oder einem Konflikt während des Schreibens gezielt nachfragen. Eine Erfolgsmeldung darf einen Teilplan nicht als vollständige Neuerstellung ausgeben.

Ein Änderungsauftrag autorisiert ausschließlich das eindeutig genannte Datum und den vorgesehenen Mahlzeittyp (Vorgabe Mittagessen). Er erlaubt weder die ganze Woche neu zu planen noch andere Tage oder eine Wiederholungsserie zu verändern. Ein Modellparameter allein ist kein technischer Nachweis des gesprochenen Benutzerwillens: die Anfrage wird vom Conversation Agent interpretiert; die Integration bindet den daraus erzeugten Kontext an authentifizierten Aufrufer, Datum und zulässigen Umfang. Falls eine zusätzliche technische Prüfung des Originalwortlauts gefordert wird, ist eine vertrauenswürdige Übergabe durch Agent/Router nötig; ein LLM-Feld `confirmed: true` genügt nicht.

Nach Erfolg kurz bestätigen, z.B. „Der Menüplan vom 28. Oktober bis 3. November ist erstellt. Du findest ihn in Yuvomi.“ Keine ungefragte Aufzählung. Unklare Datumszuordnung, fehlende Rezeptvariante, keine regelkonforme Auswahl und Teilfehler werden kurz und konkret genannt. `accepted`/„in Bearbeitung“ ist noch kein Erfolg; `state_observed` beweist nur den beobachteten Zustand.

**Planerstellung und Tagesänderung übertragen niemals automatisch Zutaten in den Einkauf.** Auch ein ausdrücklich angeforderter Wochenplan ist keine Zustimmung zur Einkaufsbuchung. Für diese gelten weiterhin ausdrücklich angeforderte Vorratsprüfung, bekannte Mengen/Packungsgrößen, Vorschau, separate vertrauenswürdige Bestätigung und dauerhafter Wiederholungsschutz.

## 3. Eigenständige Planungskonfiguration

Empfehlung: ein versionierter HA-Store pro Config Entry, getrennt vom allgemeinen Systemprompt und den Yuvomi-Rezeptdaten. Integrationsoptionen bekommen einen eigenen Bereich „Menüplanung“ mit Unterseiten Periode/Tage, Familienprofile, Kalender, Resten/Notfall und Prüfung. Keine manuelle YAML-Pflege im Alltag. Die Konfiguration erhält eine monotone Revision; Speichern erst nach Validierung und verständlicher Zusammenfassung. Bestehende Tokens, Werkzeugfreigaben und Journale bleiben erhalten.

| Feldgruppe | Vorbelegung | Validierung/Hilfetext |
| --- | --- | --- |
| Zeitzone | Europe/Zurich | Gültige IANA-Zone; lokale Kalendertage statt fester 24-Stunden-Blöcke |
| Einkaufstag | Mittwoch | Frei wählbarer Wochentag; darf unabhängig von Planungstagen sein |
| Periodenbeginn/-dauer | Einkaufstag plus Versatz 0; 7 Tage | Frei wählbarer Beginn und positive Dauer. Bei nicht siebentägiger Dauer verbindliches Ankerdatum; Last-/Bereichsgrenzen vor Implementierung testen, keine fest eingebaute Mittwoch–Dienstag-Annahme |
| Planungstage | Montag bis Freitag | Frei wählbare Wochentage; optional konkrete Datums-Ausnahmen. Kein Zwang zu Werktagen |
| Mahlzeittyp/-zeit | lunch/Mittagessen, 12:00 lokal | Zeitpunkt dient der Kalenderauswertung. Anderer Typ/Zeit konfigurierbar; keine Gleichsetzung von Datum ohne Uhrzeit mit Mitternacht |
| Zeitlimits | Je Planungstag separat; zunächst kein Limit | Nichtnegative ganze Minuten oder „kein Limit“. Gemeint ist die komplette Zeit vom Kochbeginn bis servierfertig, einschließlich Gar-, Back- und Wartezeiten. Unbekannte Rezeptzeit erfüllt ein gesetztes Limit nicht nachweislich |
| Wiederholungsregel | Rezept-IDs der unmittelbar vorherigen Periode ausschließen | Ausnahmen getrennt für ausgewähltes Resten-Rezept und explizite Notfall-Rezept-IDs; keine Ausnahme nach bloßem Namen oder KI-Einstufung |
| Restentag | Flexibel, sofern Resten-Rezept bewusst ausgewählt | Fixer Tag oder flexible Auswahl, ausgeschlossene Tage, optional „kein Restentag“. Widerspruch fixer/ausgeschlossener Tag ablehnen. Ohne ausgewähltes Rezept kein automatisches Erfinden |
| Notfallmenüs | Leere Liste | Vorhandene Rezept-IDs auswählen, Einsatzbedingungen und Wiederholungsausnahme erklären; keine stillen Ausnahmen von Allergien/Abneigungen/Zeitlimits |
| Aufwärmabstand | Höchstens 2 lokale Kalendertage | Konfiguration darf den Abstand verkürzen, aber die fachliche Obergrenze nicht überschreiten |
| Familienprofile | Keine erfundenen Personen | Stabile lokale Profil-ID, Anzeigename, reguläre Anwesenheit, Portionenfaktor/Vorgabe 1, zusätzliche Portionen für konkrete spätere Mahlzeiten, explizite Abneigungen/Rezept-IDs |
| Kalenderregeln | Leere Allowlist, keine dynamischen Abfragen | Nur genaue calendar-Entity-Referenzen, betroffene Profile, Ereignisfilter, Zeitbezug und Priorität; siehe Abschnitt 5 |

Vorbelegte Zeit-/Wochentagswerte sind editierbare Einstiegshilfen. Persönliche Profile und Kalender werden nicht erraten. Der Bereich bleibt bis zur Einrichtung ausdrücklich als unvollständig erkennbar. Beispiel-Hilfetexte: „Vier ist die Rezeptbasis, nicht die Anzahl am Tisch“, „Kalender nur auswählen, wenn dessen Ereignisse Anwesenheit tatsächlich ändern sollen“, „Ein Zeitlimit umfasst auch Back- und Wartezeiten“.

Konfigurationsänderungen verändern keinen gespeicherten Plan und starten keine Synchronisation. Laufende Vorgänge binden an eine Revision; ändert sie sich vor dem Schreiben, muss neu validiert/geplant werden. Es werden weder andere Rezepte automatisch bestätigt noch Personen aus Rezepttexten erzeugt.

## 4. Perioden, Datumsauflösung und Wiederholungen

Eine Periode wird durch `anchor_date`, positive `length_days` und Zeitzone eindeutig in aufeinanderfolgende nicht überlappende Intervalle geteilt. Bei der Sieben-Tage-Vorgabe wird das Ankerdatum aus dem ausgewählten Startwochentag abgeleitet; bei späterer Änderung wird eine neue Konfigurationsrevision mit ausdrücklich angezeigtem Anker gespeichert. Grenzen verwenden lokale Datumsarithmetik, nicht UTC-Stundenabstände.

„Nächste Woche“ bedeutet standardmäßig die **nächste vollständige konfigurierte Planungsperiode** nach der aktuell laufenden. Beispiel am 25.10.2026: aktuelle Periode 21.–27.10., nächste 28.10.–03.11. Bei Mo–Fr werden darin 28., 29., 30.10. sowie 02. und 03.11. geplant. Diese konkrete Zuordnung wird im Kontext und Ergebnis mitgeliefert. Falls der Benutzer ausdrücklich ISO-Kalenderwoche oder einen Datumsbereich nennt, nicht still darauf umdeuten; eindeutigen Bereich verwenden oder bei Regelkonflikt kurz klären.

Ein alleiniger Wochentag richtet sich im aktiven Planungs-/Änderungskontext nach dessen Periode. Außerhalb davon wird das nächste noch nicht vergangene Vorkommen dieses Tages in der konfigurierten Zeitzone vorgeschlagen; passt es zu mehreren gespeicherten/angesprochenen Perioden, Datum klären. Innerhalb einer Periode mit mehrfach demselben Wochentag genügt der Wochentag nicht. Jede Schreibzuweisung enthält ein gültiges ISO-Datum und den Mahlzeittyp; Freitextdaten werden nie unmittelbar an REST weitergereicht.

Wiederholungen vergleichen gespeicherte `recipe_id` zwischen der Zielperiode und **genau der unmittelbar vorherigen Periode**, unabhängig vom Tagesabstand. Gerichte verschiedener exakter Varianten bleiben verschiedene IDs. Bestehende Zieleinträge sind mitzuberücksichtigen, werden aber nicht nachträglich bereinigt. Ein Aufwärmeintrag innerhalb derselben Kochverwendung ist kein neuer Kochvorgang; dafür gelten die Portionszuordnungen. Er umgeht jedoch nicht den Ausschluss unmittelbar benachbarter Perioden: grenzüberschreitende Nutzung braucht eine ausdrücklich konfigurierte Wiederholungsausnahme. Konfigurierbare Resten-/Notfallausnahmen beziehen sich auf IDs und erlauben keine willkürliche Ausnahme für andere Rezepte.

Vergangene Mahlzeiten mit freiem Titel ohne Rezept-ID gelten als nicht eindeutig zugeordnet. Bei mehreren exakten Rezeptmöglichkeiten nachfragen; keine unscharfe Zuordnung. Löscht ein Benutzer frühere Mahlzeiten in Yuvomi vollständig, kann deren frühere Verwendung nicht mehr bewiesen werden. Eine zusätzliche Rezept-/Kochhistorie in HA wird dafür nicht eingeführt; der aktuelle Yuvomi-Bestand ist maßgeblich, Unsicherheit wird kenntlich gemacht.

## 5. Anwesenheit: Kalenderreferenzen und Vorrang

Kalender werden ausschließlich im HA-Menüplanungsbereich mit einem Entity-Selector für Domain `calendar` ausgewählt. Eine Regel referenziert feste Profil-IDs und eine stabile Registry-Referenz, sofern verfügbar, plus den aktuell aufgelösten `calendar.entity_id`. Keine Area-/Geräte-/Label-Expansion, keine automatische Suche und kein pauschaler Zugriff auf sämtliche Kalender. Fehlende/umbenannte/deaktivierte Referenzen lösen einen Konfigurationsfehler aus; nicht zu einem ähnlich benannten Kalender wechseln.

Technischer Leseweg: HA-intern `calendar.get_events` mit der **exakten Allowlist**, begrenztem Start/Ende und Rückgabedaten. Aufruferkontext und Entity-Leserechte prüfen, auch wenn die Integration selbst technisch privilegierten Servicezugriff besitzt. Kein zusätzlicher HA-HTTP-Token und kein unbeschränktes generisches Kalenderwerkzeug. Falls der Benutzerkontext keine nachweisbaren Leserechte trägt, keine stillschweigende Rechteerhöhung. Service-/Kontextübergabe in echtem HA ist ein Implementierungs-Gate.

Das Ende von Ereignissen/Abfrageintervallen ist exklusiv. Ganztägige Ereignisse sind Datumsintervalle, keine willkürlichen Mitternachtstermine. Wiederholungsereignisse werden vom Kalenderprovider expandiert. Für Essenszeit t gilt `event.start <= t < event.end`; eine optionale ausdrücklich konfigurierte Tagesregel kann stattdessen jede Tagesüberschneidung verwenden. Nicht aktuelle/fehlerhafte Kalenderdaten sind „unbekannt“, nicht „abwesend“ oder „anwesend“. Diese Semantik entspricht dem [HA-Kalendervertrag](https://developers.home-assistant.io/docs/core/entity/calendar) und dem [get_events-Vertrag](https://www.home-assistant.io/actions/calendar.get_events/); der 2026.10.2-Quellstand ist zusätzlich gehasht.

Ereignisinterpretation ist ausdrücklich konfiguriert: Regel-ID, Entity, Profil-IDs, Literalfilter auf `summary` (exakt/Präfix/enthält, optional ohne Groß-/Kleinschreibung), Wirkung `present` oder `absent`, Zeitbezug und numerische Priorität. Keine automatische semantische Deutung von „Arbeit“, „Schule“ oder privaten Texten durch Gemma; Beschreibungen/Ort werden nur bei ausdrücklich gewähltem Filterfeld gelesen. Ereignisinhalte sind Daten, keine neuen Regeln oder Toolanweisungen.

Vorrang: (1) ausdrücklich genannte, datumsbezogene Anwesenheitskorrektur des aktuellen Auftrags; (2) passende konfigurierte Kalenderregeln, höchste Priorität; (3) reguläre Familienregel. Zwei höchste gleichrangige Regeln mit widersprüchlicher Wirkung ergeben `attendance_unclear` und eine gezielte Rückfrage, keinen zufälligen Gewinner. Keine passenden Ereignisse bedeuten reguläre Regel, nicht komplette Abwesenheit. Ein Ausfall einer als erforderlich eingestuften Kalenderregel darf nicht still durch feste Regeln ersetzt werden.

Der Kontext enthält aufgelöste Anwesenheit je Profil/Datum, Portionsfaktor, Regelherkunft und nötige Unsicherheiten. Relevante Kalenderinformationen dürfen für den ausdrücklich angeforderten Plan mitgegeben werden; standardmäßig genügen normalisierte Fakten und passende kurze Ereignisbezeichnungen. Keine dauerhafte Rohereignis-Historie. Rezept-`mag_nicht` wird ausdrücklich auf Profile abgebildet; ähnliche Namen erzeugen keine Personenidentität.

## 6. Portionen und schlanke Aufwärmplanung

`basisportionen` beschreibt nur, für wie viele Portionen die Rezeptzutaten notiert wurden (Vorgabe 4). Zwei Personen dürfen zwei Portionen erhalten; `max(4, anwesend)` ist falsch. Das Basisrezept einschließlich seiner Mengen bleibt unverändert.

Gemma erhält den ausdrücklich konfigurierten Aufwärmbedarf je Profil/Datum, aus Familienregeln und gegebenenfalls erlaubten Kalendern. Es wählt ein akzeptiertes, nachweislich wiederaufwärmbares Gericht für einen geeigneten Kochtag **ein oder zwei lokale Kalendertage vorher**. Die Integration prüft diese Wahl und berechnet die benötigte Gesamtmenge aus den heutigen Portionen und eindeutig zugeordneten späteren Zusatzportionen. Beispiel: Mittwoch drei Personen, Donnerstag je eine Aufwärmportion für beide Kinder → Mittwoch fünf Portionen kochen; bei Rezeptbasis vier Zutatenfaktor 5/4. Donnerstag entsteht daraus kein weiterer Rezeptbedarf.

Dafür genügt eine **planbezogene Liste zusätzlicher Portionen**: Quellslot `(Kochdatum, Mahlzeittyp)`, exakte Rezept-ID und Ziel `(Datum, Mahlzeittyp, Profil-ID, Portionen)`. Kein `cook_batch_id`, keine Bestands-/Restmengen, kein Verbrauchskonto, keine Reservierungszustände, keine Erfassung gegessener oder tatsächlich übrig gebliebener Portionen. Eine Person darf pro Zielmahlzeit nicht doppelt mit demselben Zusatzbedarf eingeplant werden; identische Ziele aus Profil und Kalender werden einmal aufgelöst, nicht summiert. Eine ausdrücklich konfigurierte datumsbezogene Kalender-Ausnahme ersetzt für diesen Bedarf die feste Regel; widersprüchliche gleichrangige Mengen bleiben unklar statt addiert zu werden. Koch- und Aufwärmeintrag spiegeln dieselbe Zuordnung und zählen nicht als zwei Bedarfe. Verschiedene Quellgerichte für denselben Zielbedarf sind ein Planungsfehler, sofern nicht ausdrücklich aufgeteilte Teilportionen fachlich vorgesehen sind; die erste Umsetzung weist diese Mehrdeutigkeit zurück.

Zusatzportionen sind nur für ausdrücklich bedürftige und akzeptierende Profile zulässig. Die Integration prüft Abneigungen, Wiederaufwärmbarkeit, genaue Quelle/Zielzuordnung, Mengen und `1 <= Zieldatum - Kochdatum <= 2`. Sie beobachtet **keinen** realen Restenbestand. Änderungen am Quell- oder Zieltag dürfen andere Tage nicht still verändern. Wird dadurch eine bekannte geplante Zuordnung ungültig, den Zusammenhang kurz nennen und den Änderungsumfang klären; keine verdeckte Umplanung abhängiger Tage. Auch die angrenzenden bis zu zwei Tage außerhalb einer Periode lesen, soweit für bestehende Zuordnungen erforderlich. Wiederholungsregeln und deren konfigurierte Ausnahmen bleiben unabhängig davon erhalten.

Für Kochtage gilt die gesamte Koch-/Gar-/Back-/Wartezeit. Unter einem Zeitlimit am Aufwärmtag keine kürzere Dauer erfinden: nachvollziehbare Angaben nutzen, sonst klären. Ein eigenes Aufwärmzeitfeld ist im aktuellen Rezeptvertrag nicht vorhanden und wird nicht still ergänzt.

Skalierung nur bei eindeutigen Zahlen/Einheiten mit Decimal. Das Einkaufs-`add_or_replace` ist kein Skalierer. Freitext nicht raten; „2 Dosen“ belegt keine Gramm-/Packungsgröße. Unteilbare Verpackungen/Rundung gehören in die getrennte Einkaufsvorschau.

### Speicherung in Yuvomi und Anzeige

Yuvomi 2.79.0 hat kein natives Portionsfeld. Deshalb am **Mahlzeiteintrag**, nicht am Rezept und nicht in einer HA-Produktdatenbank, einen begrenzten versionierten Notizabschnitt speichern. Vorgesehene Felder: `v`, `kind`, `recipe_id`, `date`, `meal_type`, `servings_now`, berechnetes `servings_total` und `extras` mit Profil-ID/Zieldatum/Zieltyp/Portionen; beim Aufwärmeintrag `source_date`, `source_meal_type`, `source_recipe_id` und die zugehörigen Empfänger. Quellslot statt allgemeiner Chargen-ID. Eine Plan-/Eintragsrevision dient nur Konflikt- und Synchronisationsbelegen.

Der Block wird mit `[yuvomi-menu:v1]` und `[/yuvomi-menu]` begrenzt; darin stehen eine kurze verständliche Zusammenfassung und ein kompakter JSON-Datensatz. Beispiel Kochtag: „5 Portionen: 3 für Mittwoch, zusätzlich je 1 für Kind A und Kind B am Donnerstag.“ Aufwärmtag: „Aufwärmen vom Mittwoch: je 1 Portion für Kind A und Kind B; Zutaten beim Kochtag berücksichtigt.“ Namen sind Anzeige, stabile Profil-IDs Identität. Vorhandene freie Notizen außerhalb des Blocks unverändert erhalten. Doppelte, beschädigte, unbekannt versionierte oder extern geänderte Blöcke nicht still ersetzen. Gesamtbudget 5000 Zeichen einschließlich freier Notizen vor REST prüfen; bei Überlänge gezielt abbrechen statt abschneiden.

Der [offizielle GUI-Quellcode](https://github.com/ulsklyc/yuvomi/blob/a6812d433fc25a0f8bf1389542e68111f9169a82/public/pages/meals.js) zeigt Notizen im Mahlzeitdetail und als bearbeitbares Textfeld, aber keine besondere Portionsspalte oder automatische Auswertung dieses Blocks. Rezepttitel/Varianten bleiben exakt; keine Namenszusätze als Ersatz für Metadaten. JSON ist dort sichtbarer Text, keine zugesicherte versteckte Struktur. Der genaue Blockparser und die Lesbarkeit auf Mobilgeräten werden in der Implementierung getestet.

**Doppelbedarf beim nativen Einkaufstransfer verhindern:** Am Kochtag eigene, auf `servings_total` skalierte Mahlzeitzutaten speichern. Am Aufwärmtag keine eigenen Einkaufszutaten und **keine native `recipe_id`** setzen: sonst greift bei leerer Zutatenliste Yuvomis Rezeptzutaten-Fallback. Herkunftsrezept und exakter Titel bleiben in Notizen/Eintrag nachvollziehbar; die native Rezept-/Bildverknüpfung dieses Aufwärmeintrags entfällt. Das ist die bevorzugte serverneutrale Abbildung, vor Freigabe durch Adapter-/GUI-Tests zu belegen. Die eigene spätere Synchronisation berücksichtigt nur Kochtag-Zutaten einmal. Manuelle GUI-Neuverknüpfung eines Aufwärmeintrags mit einem Rezept kann den Fallback wieder aktivieren und muss beim nächsten Prüfvorgang als relevante Änderung erkannt werden. Keine Dummy-/Nullzutaten als Workaround.

Das einfache Modell setzt einen eindeutig zugeordneten geplanten Eintrag je Datum/Mahlzeittyp voraus. Verschiedene Gerichte für zuhause und auswärts am selben Slot werden nicht als ein Gericht für alle ausgegeben; ein solcher Mehrfachfall erfordert eine gesonderte fachliche Erweiterung oder Rückfrage, keine automatische breite Slot-Ersetzung.

## 7. Resten und Notfallmenüs

„Resten“ ist ein gewöhnliches, ausdrücklich ausgewähltes Yuvomi-Rezept. Es darf fix oder flexibel eingeplant werden, auch **ohne vorherigen Nachweis einer konkreten Restenmenge**. Das ist kein Nachweis vorhandener Vorräte und keine Buchung tatsächlicher Restenbestände. Dafür werden keine fiktiven Zutaten oder Aufwärmportionen erzeugt.

Geplante konkrete Aufwärmportionen und der allgemeine Restentag sind getrennt. Welche Resten tatsächlich gegessen werden, wird nicht erfasst; es entsteht keine zusätzliche Verbrauchsbuchhaltung. Konfigurierte Notfallmenüs können fehlende tatsächliche Resten ersetzen, werden aber vom Modell innerhalb der Regeln ausgewählt und nicht ungefragt in einen bestehenden Tag geschrieben. Wiederholungsausnahmen sind für Resten und Notfallmenüs separat konfigurierbar. Andere harte Verträglichkeits- und Zeitregeln bleiben wirksam.

## 8. Kontext nur bei tatsächlicher Planung

Gewöhnliche Alexa-/Einkaufs-/Aufgabenbefehle erhalten nur kurze Werkzeugdefinitionen und gemeinsame Sicherheitsregeln. Kein Laden von Rezeptvollbestand, Familienprofilen, Kalenderereignissen oder kompletter Planungskonfiguration in `async_get_tools()` oder den allgemeinen Systemprompt. Ein schlichter Planleseauftrag lädt gespeicherte Mahlzeiten, nicht den gesamten Planungskontext.

Bei Planung darf das Modell einen vollständigen, sachlich relevanten Datensatz bekommen: Regeln/Revision, Ziel-/Vorperiode, gespeicherte Slots und geplante Zusatzportionen, aktuelle Rezepte einschließlich Zutaten/Notizen/Metadaten, Familienprofile und aufgelöste Anwesenheit. Keine willkürliche Rezept-Vorauswahl nach einem deterministischen Score. Nicht benötigte Bilder/Binärdaten und unfreigegebene Kalender gehören nicht dazu. Überschreitet der Datensatz sichere Transport-/Kontextgrenzen, kontrolliert in gekennzeichnete Teile zerlegen oder abbrechen; niemals unbemerkt abschneiden.

**Ein verzögerter Toolaufruf allein isoliert den Kontext nicht:** Toolantworten können in der Conversation-Historie bleiben. Empfehlung ist deshalb eine eigene kurzlebige Planungsunterhaltung mit demselben Gemma-Modell, sauber getrennt von gewöhnlichen Alexa-Conversation-IDs. Der vorhandene Conversation Agent/Assist Router muss das unterstützen; die MCP-Integration kann fremde Agent-Historien nicht eigenmächtig löschen. Wenn diese Trennung nicht möglich ist, wird die garantierte Entlastung nach einer Planung nicht behauptet; vor Implementierung einen getesteten Host-/Routerweg wählen.

Planungsdaten sind an Aufrufer, Zweck (`create_period`, `replace_day`, `suggest_day`), genaue Periode/Slots, Konfigurationsrevision, Ablaufzeit und Eingabefingerprints gebunden. Ein Vorschlagskontext kann nicht in einen Schreibkontext umgewandelt werden. Die Integration validiert Modellzuweisungen gegen diesen Kontext; weder Modell noch Rezepttext dürfen Regeln, Kalender-Allowlist oder Schreibumfang aufweiten. Bei langsamer Planung kommt ein klarer Bearbeitungsstatus statt einer verfrühten Erfolgsmeldung; Fortsetzung/Wiederholung muss dieselbe Vorgangsidentität verwenden.

## 9. Direkte Speicherung und Konfliktschutz

Vor dem Schreiben: aktuelle Konfigurationsrevision, Rezepte, Anwesenheit, geplante Zusatzportionen und Zielslots erneut prüfen. Ein Hash erfasst nur fachlich relevante Werte; Kalender-/Rezepttexte sind keine Versionsautorität. Kontextablauf oder relevante Änderungen führen zu `context_stale`/`concurrent_change`, ohne blind neu zu schreiben.

Für neue Slots `POST /api/v1/meals/apply-plan` mit `skip_occupied: true`, ohne `replace_existing`, einem assignment je Datum/Typ und stabilem `Idempotency-Key`. Die Integration weist doppelte Slots bereits vor REST ab: Yuvomi lässt mehrere Zuweisungen in denselben vorher leeren Slot sonst zu. Die Route verarbeitet ihren Aufruf atomar; `skipped` muss als Konflikt/Teilabdeckung gemeldet werden und darf keine Portionsabhängigkeit offenlassen. Bei voneinander abhängigen Koch-/Aufwärmzuweisungen erst nach Lesen des tatsächlichen Ergebnisses als konsistent bestätigen. Eine unvollständig gespeicherte Abhängigkeitsgruppe wird gesperrt und sichtbar, nicht automatisch nochmals geschrieben oder blind rückgängig gemacht.

Explizite Tagesänderung erlaubt gezielte Ersetzung, aber die API setzt Grenzen: Ein einzelnes `PUT /meals/:id` kann Rezept/Notizen ändern, ersetzt jedoch im Nicht-Serienpfad **keine Zutaten**. `apply-plan` mit `replace_existing: true` ersetzt Zutaten atomar, löscht dabei aber **alle** Mahlzeiten im genannten Datum/Typ und legt neue IDs an. Dafür nur ein eindeutig autorisierter Slot, nach erneutem vollständigem Abgleich; niemals die gesamte Woche mit replace_existing schreiben. Mehrere vorhandene Einträge erfordern Rückfrage.

Yuvomi 2.79.0 besitzt hier keine atomare Erwartungsprüfung/If-Match. Eine fremde Änderung zwischen Abgleich und Ersetzung kann deshalb nicht vollständig ausgeschlossen werden. **Architekturentscheidung:** Für diesen privaten Familienassistenten ist das verbleibende Konfliktrisiko ausdrücklich akzeptiert. Gezielt nochmals lesen/vergleichen und genau einen Slot über apply-plan ersetzen; keine weitere Bestätigungsrunde und keine neue serverseitige CAS-API. Ein vorab bemerkter Konflikt wird gemeldet. Eine fremde Änderung im anschließenden Zeitfenster bleibt ein dokumentiertes Restrisiko. Kein mehrstufiges Löschen/Neuanlegen und kein `scope=series`. Journal, Idempotenz und Timeoutbarrieren bleiben verpflichtend.

Yuvomi-GET auf Wochen kann Wiederholungsinstanzen materialisieren. „Lesen“ bedeutet daher keine garantierte SQLite-Schreibfreiheit auf dem Server. Diese serverseitige Bestandsbildung wird nicht mit einem von HA neu erstellten Menüplan verwechselt; Annotationen und Tests müssen diese Besonderheit berücksichtigen.

## 10. Idempotenz, Journal und Einkaufssynchronisation

Schreibabsichten werden vor I/O dauerhaft vorbereitet. Wiederholungen mit gleichem Vorgang liefern den belegten Ausgang; unklare Ergebnisse bleiben gesperrt und werden ausschließlich lesend geprüft. Server-Idempotenz gilt nur für POST und ist zeitlich begrenzt; sie ersetzt weder das Journal noch die Unterscheidung eines echten neuen Änderungswunsches von einem Retry. Ein Alexa-Retry kann auch eine neue HA-/Tool-ID und einen anders formulierten Modellplan haben. Die Vorgangsidentität muss deshalb vor der Modellauswahl an den Aufrufer, die aufgelöste Periode/den Tag und den ursprünglichen Auftrag gebunden werden; Payload-Hash allein reicht nicht.

HA-intern pro Planungsperiode/überlappenden Slots serialisieren; bei überlappenden geplanten Zusatzportionen dieselbe Sperrdomäne verwenden. Andere Yuvomi-Clients nehmen daran nicht teil. Eine atomare apply-plan-Transaktion ist keine globale Exactly-once-Garantie und keine atomare Transaktion über Plan und Einkauf.

Einkaufssynchronisation bleibt ein separater Ablauf:

1. Benutzer fordert Vorratsprüfung/Übertragung ausdrücklich an. Aktuellen Yuvomi-Plan, echte Zutaten, ausgewählte Zielliste und erlaubte Vorratsinformationen lesen. Unbekannte Bestände/Packungsgrößen nicht als Null auslegen; Unklarheiten zeigen.
2. Nur den Kochbedarf einmal je Quellslot berücksichtigen. Bereits beim Planen skalierte eigene Mahlzeitzutaten nicht erneut skalieren; Faktor/Quellenfingerprint gegen den Notizblock prüfen. Aufwärmportionen nicht nochmals als Zutatenbedarf buchen. Allgemeines Resten erzeugt keinen erfundenen Bedarf.
3. Vorschau mit Mengen, Einheiten, Kategorien, vorhandenen Beständen, Packungsannahmen und verbleibenden Unsicherheiten ausgeben. Ein allgemeines Einkaufs-ensure ist keine Synchronisation.
4. Separate vertrauenswürdige Bestätigung an Vorschauhash, Plan-/Konfigurationsrevision, Aufrufer und Zielliste binden. Vor dem Schreiben dieselben Quellen erneut prüfen. Ein vom Modell gesetztes Boolesches `confirmed` ist keine Bestätigung; vorhandene HA-Optionsbestätigung gezielt wiederverwenden/erweitern.
5. Stabile Synchronisationsidentität pro Planrevision, Kochslot/Zutat und Zielliste mit dauerhaftem abgeschlossenem Beleg. Gleiche Synchronisation wird auch nach Neustart nicht nochmals addiert. Unklare Teilaktionen blockieren erneute Buchung.
6. Bei geänderter Planrevision nicht nochmals die gesamte Zutatenliste addieren: frühere Synchronisationsbelege berücksichtigen, Differenz vorschlagen und erneut bestätigen. Negative/unklare Differenzen oder inzwischen manuell/geprüft veränderte Einkaufsartikel nicht automatisch entfernen/korrigieren. Keine Rückabwicklung fremder Einkaufsbeiträge.

Der aktuelle begrenzte Ausführungsjournal-Ring ist allein kein dauerhaftes Sync-Gedächtnis: erledigte Vorgänge können nach Ablauf verdrängt werden. Deshalb kompakte abgeschlossene Synchronisationsbelege getrennt von diesem Ring erhalten, ohne Rezeptkatalog. Keine automatische Beleglöschung, die einen alten Plan wieder buchbar macht; Kapazitätsgrenzen blockieren sicher oder erfordern bewusstes Archivieren. Speicheraufteilung und Migrationsschritte stehen im Implementierungsplan.

## 11. Zusätzliche HA-LLM-API: untersuchen, nicht implementieren

Die aktuelle `assist`-Anbindung bleibt für 1.4.4 erhalten. HA 2026.10.2 kann mehrere APIs kombinieren; eine eigene auswählbare Yuvomi-API ist technisch möglich, isoliert aber weder automatisch Gesprächshistorien noch spart sie bei identischen Werkzeugen Tokens. Empfehlung: zunächst Beschreibungen optimieren; eine optionale zusätzliche API erst nach eigener Freigabe mit bewusstem Expositionsmodus und Migration entwickeln. Neue Planungswerkzeuge bleiben standardmäßig deaktiviert. Details, Agent-/Routerbefunde und Grenzen: [LLM_API_ARCHITECTURE_1.4.4.md](LLM_API_ARCHITECTURE_1.4.4.md).

## 12. Abnahme vor Freigabe

Das Modell muss echte Wochenvorschläge unter den vollständigen Regeln liefern; Integrationstests prüfen deterministische Grenzen und erlauben keine versteckten Generator-Fallbacks. Testmatrix, API-Belegstufen, Kontext-/Tokenvergleich und offene Freigabeentscheidungen: [PLAN_1.4.4.md](PLAN_1.4.4.md), [TOOL_CONTEXT_ANALYSIS_1.4.4.md](TOOL_CONTEXT_ANALYSIS_1.4.4.md).

Diese Spezifikation ersetzt den früheren Ablauf „Menüvorschlag → Bestätigung → Speicherung“ für eindeutige Menüaufträge. **Nur die getrennte Einkaufsübertragung behält Vorschau und gesonderte Bestätigung.**
