# Menüplanung 1.4.5

## Architektur und Verantwortung

Das Modell wählt Gerichte und bei mehreren geeigneten Quellen einen Kochtag. Das Backend berechnet Personen, Portionen, Mitnahmezuordnungen und Zutaten. Nur Yuvomi speichert Rezepte und geplante Mahlzeiten. HA speichert ausschliesslich explizit gepflegte Regeln/Profile und Ausführungsbelege, keinen Rezept-/Vorratsbestand. Kontexte sind kurzlebige Snapshots im RAM.

`planning_allocations.py` enthält die reine Zuordnung und Berechnung, `menu_planning.py` Kontext-/Konfliktprüfung und das unveränderte Journal/REST-Protokoll. `planning_config.py` validiert Regeln; `planning_wizard.py` bietet kleine HA-Optionsseiten. Die bisherige Slot-Validierung bleibt intern zur Regression des alten Vertrags erhalten; öffentliche Planungsaufrufe benötigen die neue Standardwoche. Persistente RC3-Journale und strukturierte Notizen bleiben lesbar und werden nicht gelöscht.

## Einrichtung ohne JSON

1. Vor einer später freigegebenen Installation HA-Konfiguration einschliesslich `.storage` und Yuvomi separat sichern. Dieses Paket installiert sich nicht automatisch.
2. In HA: Einstellungen → Geräte & Dienste → Yuvomi MCP → Konfigurieren → Menüplanung einrichten.
3. Beim ersten Öffnen entsteht ein neuer **Entwurf**; vorhandene alte Regeln werden nicht migriert. Erst „Entwurf speichern“ übernimmt ihn atomar. Kein bestehender Yuvomi-Eintrag wird dadurch geschrieben.
4. Unter Familienprofile Daniel, Cornelia, Aaron und Aliyah prüfen. Stabile interne IDs bleiben bei Umbenennung gleich. Vorlieben, Abneigungen, Ernährungspräferenzen und Portionsbedarf bearbeiten. Für Kochpersonen tatsächliche Yuvomi-Mitglieder auswählen: dafür benötigt der vorhandene Token zusätzlich `family:read`, niemals `family:write`.
5. Daniels Anwesenheit ist anfangs **ungeklärt**. Bewusst „ohne Kalender nicht dabei“ oder „dabei“ wählen oder passende Kalenderregeln einrichten. Sonst muss die konkrete Planung seine Anwesenheit klären; sie wird nicht erfunden.
6. Jeden Wochentag bearbeiten: frisch essende Personen, Mitnahmebedarf am Zieltag, maximale Aufbewahrungsdauer (1–2 Kalendertage), gesamte Kochzeit, Kochperson und ausgewählte Kalender. Diese Kalender benötigen zusätzlich eine Interpretationsregel.
7. Periode/Anker frei einstellen; Mittwoch bis Dienstag ist nur die Vorbelegung. Resten-/Notfallrezepte und Wiederholungsausnahmen auswählbar.
8. „Entwurf speichern“. Neue Planungskontexte verwenden diese Revision. Werkzeuge/LLM-API werden dadurch nicht freigegeben und Agenten/Router nicht geändert.

| Tag | Frisch | Mitnahmebedarf an diesem Tag | Zeit | Kochperson |
|---|---|---|---|---|
| Montag | Cornelia, Daniel nur gemäss expliziter Annahme/Kalender | – | 75 min | Cornelia |
| Dienstag | Cornelia, Aliyah, ggf. Daniel | Aaron, max. 1 Tag alt | 60 min | Cornelia |
| Mittwoch | Cornelia, Aaron, Aliyah, ggf. Daniel | – | 40 min | Cornelia |
| Donnerstag | Cornelia, ggf. Daniel | Aaron und Aliyah, max. 2 Tage alt | 60 min | Cornelia |
| Freitag | Cornelia, Aliyah, ggf. Daniel | –; Aaron isst in der Schule | 25 min | Cornelia |
| Wochenende | zunächst keine automatische Planung | – | frei | – |

Montag wird dadurch automatisch eine geeignete zusätzliche Aaron-Portion für Dienstag zugerechnet. Donnerstag kann Dienstag oder Mittwoch versorgt werden. Bei zwei geeigneten unterschiedlichen Gerichten muss das Modell die Quelle auswählen. Kein automatischer kulinarischer Zufallsentscheid.

## Kalender und Wochenabweichungen

Nur an einem Wochentag ausgewählte Kalender wirken dort. Explizite Regeln verknüpfen Ereignistitel mit Profilen und `present`, `absent`, `reheat` oder `no_reheat`. Titelvergleich ist exakt, Präfix oder enthalten, jeweils ohne Gross-/Kleinschreibung. Standardmässig muss ein Ereignis die Essenszeit überdecken; optional zählt jede Tagesüberschneidung. Ganztägige Ereignisse haben ein exklusives Enddatum. Höhere Priorität gewinnt; gleichrangige Widersprüche werden zurückgewiesen. Registry-Verweise und aktuelle HA-Entity-Leserechte werden geprüft. Fehlende Rechte oder nicht lesbare Kalender werden nicht als Anwesenheit interpretiert.

Explizite `overrides` übersteuern Standard und Kalender nur für den Kontext. Kalenderleserechte und Verfügbarkeit werden trotzdem geprüft. „Ich“ muss vorab eindeutig einem Profil zugeordnet sein; ohne Zuordnung nachfragen. Keine automatische Ableitung aus Anzeigenamen oder Tokenkonto. Pro Feld/Person/Datum ist nur eine Abweichung erlaubt. Zusätzliche Portionen über `additional_portions` angeben: das Backend addiert sie zum Tagesbedarf. `portion` setzt alternativ den absoluten Zielwert für die Person und den Tag; nicht beide kombinieren; für neue Empfänger zuerst ein Profil anlegen. Keine anonymen erfundenen Empfänger.

## Drei Werkzeuge

### Kontext

```json
{
  "action": "create_period",
  "period": "next",
  "overrides": [
    {"date": "2026-11-10", "profile_id": "member_03", "reheat": false},
    {"date": "2026-11-05", "profile_id": "member_01", "present": true}
  ]
}
```

Beispieldaten immer an die tatsächliche Zielperiode anpassen. Genau eines von `period`, `start_date`, `date` wählen. `create_period` erlaubt anschliessendes Speichern; `suggest_period` nur Prüfung. `create_day` plant nur einen freien Tag, ohne belegte Slots zu überschreiben. `replace_day` erlaubt eine ausdrücklich gewünschte Ersetzung, `suggest_day` nur einen Vorschlag. Alle Tagesaktionen benötigen ein konkretes `date`. Kontext gilt fünf Minuten, ist an Aufrufer und Konfigurationsrevision gebunden und überlebt keinen Neustart. Vollständige Wochenplanung weiterhin bewusst in separater Conversation; keine automatische Kontextisolation.

`overrides` unterstützt `present`, `reheat`, `portion` oder `additional_portions` (mit `profile_id`) sowie `cook` (Profil-ID oder null), `recipe_id` und `max_minutes` (Zahl oder null). Rezeptwünsche einer Woche als datierte Overrides; `requested_recipe` als exakten Titel nur bei Tageskontexten verwenden. Die Standardkonfiguration bleibt unverändert.

### Prüfen oder speichern

```json
{
  "context_id": "<aus tatsächlicher Antwort>",
  "assignments": [
    {"date": "2026-10-28", "recipe_id": 17},
    {"date": "2026-10-29", "recipe_id": 22}
  ],
  "reheat_sources": [
    {"date": "2026-10-29", "profile_id": "member_03", "source_date": "2026-10-28"}
  ],
  "validate_only": true
}
```

Nur ein schematischer Ausschnitt: alle freien `free_slots` mit Frischbedarf gemeinsam zuweisen; keine Mitnahme-/Aufwärmeinträge anlegen. Ein bewusst zusätzlich gewählter Kochtag ohne Frischbedarf ist erlaubt, wenn er tatsächlich zugeordnete Mitnahmeportionen vorbereitet; ein leerer Menüeintrag wird abgewiesen. IDs müssen tatsächlich im Kontext vorhanden sein. Im Normalfall genügen Datum und Rezept-ID. `reheat_sources` nur zur eindeutigen Quellenauswahl. Bei fehlender/eindeutig ungeklärter Quelle liefert `reheat_source_unclear` alle offenen Bedarfe und geeigneten `source_dates` gesammelt in `choices`. Mengen und Empfänger nicht manuell duplizieren. Die alten Eingabefelder `extra_servings`, `source_date` am Assignment und `kind: reheat` sind im neuen öffentlichen Schema nicht mehr erlaubt. Optionales `kind` für konfigurierte Resten-/Notfallgerichte.

`validate_only: true` prüft den aktuellen Snapshot, berechnet Portionen und gibt `validated_preview` zurück, ohne POST oder neue Journalbelege. Vorschlagskontexte können nie speichern. Ohne Prüfmodus wird bei ausdrücklich angeforderter Planung direkt gespeichert; keine zusätzliche Bestätigungsrunde. Erst `created`/`replaced` mit geprüften `meal_ids` rechtfertigt eine Erfolgsmeldung. `replayed` ist keine weitere Ausführung. Ein Prüfresultat reserviert keinen Slot; Speichern prüft alle Fakten erneut.

### Lesen

`get_menu_plan` liest gespeicherte Menüeinträge ohne umfangreichen Planungskontext. `date` für einen konkreten Tag; `period` plus `detail: "full"` für die gesamte Periode. `prepared_meals` zeigt am Zieltag verfügbare, bereits zugeordnete Mitnahmeportionen und ihre Kochquelle, auch ohne eigenen Kalendereintrag. Standardausgabe bleibt heute/morgen. Yuvomi kann bei GET wiederkehrende Einträge materialisieren.

## Sicherheit und Grenzen

- Nur geeignete, ausdrücklich wiederaufwärmbare und vom Empfänger akzeptierte Quellen innerhalb des Alterslimits. Eine Zuordnung je Person/Zieldatum/Mahlzeittyp; keine zweite Reservierung.
- Eine vorhandene unveränderte Quelle kann nur bereits dokumentierte Zusatzportionen liefern. Fehlende zusätzliche Mengen dort werden nicht heimlich nachgetragen: Quelle ausdrücklich ändern oder einen freien Kochtag verwenden. Quellen ausserhalb des erlaubten Schreibumfangs sind keine automatisch veränderbaren Kandidaten.
- Ganze Perioden decken ihren eigenen Mitnahmebedarf ab; am Periodenende keine neue Quelle für eine noch ungeplante Folgeperiode erzwingen. Tagesaktionen berücksichtigen verbundene Bedarfe bis zwei Tage danach. Bereits dokumentierte spätere Abhängigkeiten bleiben bei jeder Quellenänderung geschützt.
- Bei Tagesänderungen vorhandene Zusatzportionen erhalten und erneut prüfen. Ist das gewünschte Rezept ungeeignet, keine stille Substitution. Alte RC3-Aufwärmkalendereinträge bleiben bestehen; betroffene Abhängigkeiten blockieren statt stiller Bereinigung. Bei unmöglichem Änderungsumfang gezielt klären.
- Explizite Tagesrezepte übersteuern Geschmack, Wiederholung, Gesundheitsvorschläge und Kochzeit; nicht Quelleignung, Empfängerakzeptanz, Mengen- oder Konfliktsicherheit. Freitext-Vorlieben/Zutatenabneigungen werden dem Modell übergeben; keine verlässliche Allergendiagnostik oder semantische Zutatenprüfung behaupten.
- Basisportionen bleiben am Originalrezept (Standard 4). Gesamtportionen/Basis = Faktor. Nur Mahlzeitzutaten skalieren; keine Änderung der Rezeptdaten. Nicht numerisch sicher skalierbare Mengen führen weiterhin zu `quantity_unclear`.
- Yuvomis Feld „Zutaten skalieren“ ist ein GUI-Eingaberegler mit Startwert 1, kein gespeichertes Portions-/Faktorfeld. Deshalb bereits skalierte Zutaten speichern und Faktor/Portionen in den Notizen dokumentieren. Den Regler nicht nochmals auf den dokumentierten Faktor setzen: sonst droht doppelte Skalierung. Erneute manuelle Rezeptauswahl im GUI kann Namen/Notizen/Zutaten ersetzen.
- Neue Mahlzeiten verwenden die konfigurierte Standardkochperson. Bei einer Rezeptänderung bleibt die tatsächlich in Yuvomi gespeicherte Kochperson erhalten, sofern kein ausdrückliches `cook`-Override vorliegt. Eine einzelne Kochänderung verändert die Standardwoche nicht.
- Titel bleiben mit dem Originalrezept verknüpft. Kompakte Portions-/Mitnahmeannotation wird angehängt, solange Yuvomis 200-Zeichen-Limit eingehalten wird; sonst bleibt der exakte Rezepttitel und die vollständige Information in Notizen. Keine Kürzung von Marke/Variante.
- HA serialisiert Menüschreiben. Andere Clients sind nicht gesperrt. `skip_occupied`, vorheriger Bestandsvergleich, Journal und Idempotenz reduzieren Konflikte; keine Exactly-once-/CAS-Garantie. Teilantwort, Timeout oder fehlender Journalabschluss: sperren und beobachten, niemals blind wiederholen oder auf Verdacht entsperren.
- Reconciliation wiederholt keinen POST, verändert aber den HA-Journalzustand. Backup/Untersuchung zuerst; ein vollständig passender Zustand beweist nicht die eigene Schreibausführung.
- Keine neue automatische Hintergrundplanung, Einkaufsübertragung oder Assist-Router-Anpassung.

## Abnahme nach separater Installationsfreigabe

Zunächst isolierte HA-Testinstanz und Testdaten verwenden. Standardwoche und Kochidentitäten konfigurieren, Vorschlag mit fünf freien Kochtagen prüfen, Aaron-Zuordnung Montag→Dienstag und Kinderzuordnung Dienstag/Mittwoch→Donnerstag kontrollieren. Daniel einmal mit und einmal ohne explizite Anwesenheit prüfen. Erst danach einen ausdrücklich gewünschten Speichervorgang ausführen und die gesamte Periode samt Zutaten, Kochpersonen und `prepared_meals` lesen. Tagesrezept und Kochperson ändern; Abhängigkeiten, Originalrezepte und bestehende andere Tage vergleichen. Retry darf keine neue Addition/zweite Einträge erzeugen. Timeout/Neustart nur mit Testserver simulieren, nicht durch absichtliche Produktionsunterbrechung.


## Rückkehr zu RC3

Die neue Standardwoche wird nicht rückwärts migriert. RC3 kann die neue Planungskonfiguration mit `week` nicht lesen und blockiert diesen Bereich sicher. Deshalb vor Einrichtung eine Sicherung behalten. Bei einer später nötigen Rückkehr zunächst offene Ausführungen und den Yuvomi-Zustand prüfen; gegebenenfalls nur die alte **Planungskonfiguration** gezielt aus der Sicherung wiederherstellen. Das unabhängige Ausführungsjournal niemals durch einen älteren Stand ersetzen oder löschen, sobald Schreibversuche stattgefunden haben. Neu erzeugte Yuvomi-Einträge werden durch einen Code-Rollback nicht rückgängig gemacht. Diese Schritte erst nach separater Freigabe und vorzugsweise in der isolierten Testinstanz durchführen.
