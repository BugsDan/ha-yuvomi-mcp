# Menüplanung: geprüfte Vorschläge und verlustfreie Konfiguration

> Für den lokalen 1.4.5-Stand gilt vorrangig [SETUP_1.4.5.md](SETUP_1.4.5.md). Die nachfolgenden älteren Entwurfs-/RC3-Regeln zu eigenen Aufwärmeinträgen und manuellen Zusatzportionen gelten nicht für den neuen cooking_only-Vertrag.

Lokaler Entwicklungsstand auf `dev/planning-reliability`, Grundlage v1.4.4-rc3
(`896e523157be158e5366cb6ad486db4c342e7a1e`). Keine Versionsanhebung, Commits,
Pushes, Tags, Veröffentlichung oder produktive Installation. Keine Änderungen am Router,
Yuvomi-Server oder Einkaufssynchronisation.

## Befund nach Priorität

| Beobachtung | RC3-Vertrag / tatsächliche Lücke | Lokale Verbesserung |
| --- | --- | --- |
| Planung ohne Werkzeugaufruf und erfundene Gerichte | Freitext verlässt das Modell ohne Backend-Prüfung. Der zentrale Planungsprompt wird erst nach Kontextabruf sichtbar. Die permanente Routinganweisung war zu schwach. | Kurze verbindliche Routinganweisung bei freigegebenen Menüwerkzeugen; ausführliche Regeln weiterhin zentral im Planungskontext. Ohne Kontext keine Behauptung verifizierter Yuvomi-Planung. |
| Nachfrage nach bereits konfigurierten Regeln | Unzureichende Handlungsanweisung, kein fehlender Datenbestand im Werkzeug. | Kontext zuerst lesen; nur fehlende/widersprüchliche Fakten gezielt erfragen. Allgemeine Rezeptideen ausdrücklich von konkreter Yuvomi-Planung trennen. |
| Falsche Portionssummen im Text | `prepare()` berechnete Mengen bereits korrekt; freie Textvorschläge durchliefen diese Funktion nicht. | Schreibfreie validierte Vorschau verwendet dieselbe Funktion und liefert berechnete Summen zurück. |
| Vier Basisportionen pro Person | Backend summierte bereits `portion` pro anwesendem Profil und skalierte Zutaten durch `count / basisportionen`. | Zentraler Prompt mit konkretem Beispiel 3 anwesende + 2 spätere Portionen = 5, nicht 12. |
| Unaufwärmbares Gericht / fehlende oder doppelte Extras | Bereits vor dem POST verhindert: Aufwärmbarkeit, Quelle, Abstand, Personenbedarf und eindeutige Extra-Zuordnung werden geprüft. | Dieselben Ablehnungen auch vor Ausgabe einer geprüften Vorschau. |
| Zeitlimit überschritten, dennoch „alle Regeln erfüllt“ | `elapsed > limit` bzw. unbekannte Zeit bei gesetztem Limit war bereits ein Fehler. Freitextbehauptung war ungeprüft. | Prüfung vor Vorschlagsbestätigung über Backend; Prompt verbietet Erfolgsbehauptung nach Ablehnung. |
| Wenig Abwechslung innerhalb derselben Periode | RC3 prüfte nur die unmittelbar vorherige Periode, nicht doppelte Kochtage innerhalb der aktuellen. | Wiederholte Kochrezept-ID innerhalb der aktuellen Periode abweisen, einschließlich anderer bereits belegter Slots. Aufwärmen bleibt zulässig; bestehende `repeat_exceptions` erlauben konfigurierte Resten-/Notfall-Ausnahmen. |
| `mag_nicht`: ID versus Anzeigename | Beide exakten Schreibweisen wurden bereits erkannt. Unbekannte Bezüge wurden jedoch ignoriert; mehrdeutige Namen nicht eigens ausgewiesen. | Exakte Zuordnung muss genau ein Profil ergeben, sonst `profile_unclear`. Keine automatische Umbenennung, unscharfe Namensauflösung oder Rezeptmigration. |
| `period` und `start_date` gleichzeitig | Bereits als `date_unclear` abgewiesen, aber Beschreibung/Fehlerkorrektur waren zu unkonkret. | Gegenseitiger Ausschluss ausdrücklich im Schema und zentralen Prompt; Fehlermeldung nennt die zu entfernenden Alternativen. |
| Formulareingaben nach Fehler weg | Reales UI-Problem: Fehlerpfad baute die Felder aus dem gespeicherten Stand neu auf. | Reiner Form-Builder mit Deep-Copies der eingereichten Werte; feldbezogene Meldungen und konkrete Profil-IDs. Kein persistierter Zwischenstand. |

## Ablauf mit unverändert drei Werkzeugnamen

### Vorschlag für eine ganze Periode, noch nicht speichern

```json
{"action":"suggest_period","period":"current"}
```

An `get_menu_planning_context` senden. `period`, `start_date` und `date` sind Alternativen;
höchstens einen davon verwenden. `suggest_period` und `create_period` verwenden die tatsächlich
konfigurierte Periode und deren Planungstage; keine erfundene Montag-Sonntag-Woche.
Tagesvorschläge verwenden weiterhin `suggest_day` plus `date`, gezielte Änderungen `replace_day`.

Der Kontext enthält reale Rezept-IDs, Regeln und Anwesenheit, aber jetzt zusätzlich
`validation_status="context_only"` und `write_permitted=false` für Vorschlagsmodi.
`status="ready"` bedeutet ausschließlich, dass Kontext verfügbar ist, nicht dass ein Plan geprüft wäre.

Das Modell wählt Rezepte und ordnet Extras zu. Danach ruft es das bestehende Werkzeug
`save_menu_plan` mit `context_id`, vollständigen `assignments` und **`validate_only=true`** auf.
Das ist trotz des bestehenden Werkzeugnamens ein reiner Prüfpfad:

- Alle normalen Regeln und die frischen Rezepte, Mahlzeiten, Kalender-/Anwesenheitsdaten,
  Konfigurationsrevision, Aufruferbindung und Ablaufzeit werden überprüft.
- Keine `apply-plan`-Anfrage, keine neuen Journaleinträge, keine Veränderung von Kontext oder Rezeptdaten.
- Antwort bei Erfolg: `status="validated_preview"`, `validation_status="validated"`, `saved=false`.
- Pro Mahlzeit: Datum, exakte Rezept-ID/Titel, Art, `servings_total`, beim Kochen `servings_now`,
  Extras mit Profil-/Zieldatum sowie beim Aufwärmen `source_date` und Empfänger.
- Nur diese berechneten Werte als geprüft wiedergeben. Ein Fehler ist kein geprüfter Plan.
- Vorschlagskontexte lehnen echte Speicheraufrufe auch dann ab, wenn das Modell anschließend
  versehentlich `validate_only` weglässt. Zum später ausdrücklich gewünschten Speichern
  einen neuen schreibfähigen `create_period`-/`replace_day`-Kontext abrufen und neu prüfen.

`validate_only=false` bzw. ausgelassen behält für schreibfähige Kontexte den bestehenden
Speicherpfad. Bestehende Aufrufe bleiben gültig. Keine zusätzlichen Werkzeuge oder automatischen
Freigaben. Für eine geprüfte Vorschau muss auch das bestehende `save_menu_plan` freigegeben sein.
Ein verfügbares Journal bleibt Voraussetzung, damit offene/unklare Schreibvorgänge nicht übergangen werden.

Vorschau-Aufrufe verwenden bewusst nicht den flüchtigen Schreib-Ergebniscache: Eine identische
erneute Vorschau prüft die Aktualität neu, statt nach Regeländerungen ein altes „validiert“ zu liefern.
Idempotenz, Journale und Wiederherstellung echter Schreibaktionen bleiben erhalten.

### Bedeutung und Grenzen einer Backend-Bestätigung

Die Integration kann **nicht** verhindern, dass ein Conversation Agent ohne Werkzeugaufruf
einen frei erfundenen Text ausgibt oder selbst einen Status behauptet. Sie hat keine Kontrolle
über diesen Ausgabepfad. Stärkere Prompts verbessern die Anleitung, garantieren aber keine
Modellbefolgung. Nur ein tatsächliches erfolgreiches ToolResult belegt die Backend-Validierung.
Ein vollständig abgesicherter Anzeige-Badge oder ein Antwortfilter benötigte Agent-/Router-Unterstützung;
das wurde hier ausdrücklich nicht eingeführt.

Eine Vorschau gilt für die geprüften Zuweisungen und den damaligen Datenstand, nicht unbegrenzt.
Kontexte verfallen weiterhin nach 300 Sekunden und bei Neustart; längere Reasoning-Durchläufe
oder spätere Bestätigung können einen neuen Abruf erfordern. Ganzwochenplanung weiterhin
bewusst in separater Conversation. Keine automatische History-Isolation oder Hintergrundplanung.

## Bestehende und ergänzte Backend-Sicherheit

- Alle freien Slots einer ganzen Periode müssen gemeinsam zugewiesen werden. Belegte Slots
  werden bei Erstplanung und Vorschlag geschützt. Explizites `replace_day` betrifft nur einen Slot.
- Aufwärmbedarf und Anwesenheit sind getrennte Merkmale. Eine einzige Mahlzeit kann nicht
  stillschweigend zwei verschiedene Gerichte für anwesende Personen und Aufwärmempfänger darstellen.
  Nicht eindeutig darstellbare Fälle werden weiterhin zur Klärung zurückgewiesen.
- Ein Extra muss dem konfigurierten Profilbedarf entsprechen, ein akzeptiertes aufwärmbares
  Gericht haben und genau einmal mit einem passenden Aufwärmeintrag verknüpft sein.
- Kochportionen = Summe aktueller anwesender Portionsbedarfe + Summe zugeordneter Extras.
  Reheat-Einträge erzeugen keine zweiten Zutaten. Die Rezeptbasis ist nur der Skalierungsnenner.
- IDs und Anzeigenamen in `mag_nicht` werden exakt aufgelöst. Geänderte, unbekannte oder
  doppelte Anzeigenamen benötigen Klärung; vorhandene Konfigurationen werden nicht umgeschrieben.
- Zeitlimits beziehen sich auf die gesamte Koch-/Aufwärmzeit. Unbekannte Zeiten belegen keine
  Limit-Einhaltung. Die unmittelbar vorherige Planungsperiode bleibt die Wiederholungsreferenz.
- Zusätzliche Abwechslung innerhalb derselben Periode kann bei zu wenigen zulässigen Rezepten
  eine Planung unlösbar machen. Keine automatische Lockerung; gezielt Rezeptbestand/Regeln klären.

**Teilweise Speicherung:** Ein ungültiger Plan wird vollständig vor dem ersten POST abgewiesen.
Yuvomi 2.79.0 verarbeitet `apply-plan` in einer Transaktion, kann bei `skip_occupied` aber durch
gleichzeitige Änderungen neu belegte Slots auslassen und andere anlegen. Zwischen letzter
Bestandsprüfung und POST besteht weiterhin ein Rennen mit anderen Clients. Das lässt sich
ohne serverseitige Vorbedingung nicht vollständig verhindern. Bereits vorhandenes Verhalten:
`execution_unconfirmed`, Journalstatus `unknown`, keine Erfolgsmeldung, keine blinde Wiederholung,
lesende Wiederherstellungsprüfung. Keine nachträglichen automatischen Lösch-/Kompensationsaktionen.
Die Vorschau selbst sendet keinen POST; bestehende Yuvomi-GETs können serverseitig weiterhin
wiederkehrende Mahlzeiten materialisieren, wie bereits im bisherigen Lesewerkzeugvertrag dokumentiert.

## Konfigurationsoberfläche

Umgesetzt, Priorität 1:

- Alle eingereichten Werte werden als Formulardefaults wiedergegeben, einschließlich verschachtelter
  Profile/Kalender, Zeitlimits, ausgewählter Entities und erweiterter Einstellungen.
- Kandidaten und Formwerte sind Deep-Copies; weder Fehlerbehandlung noch Registry-Bindung verändern
  den gespeicherten Zustand versehentlich. Nur erfolgreiches atomisches Speichern erhöht die Revision
  und verwirft alte Planungskontexte.
- Ungültige IDs wie `Ehemann` und `Kind 1` werden benannt, mit Beispiel `kind_1` und Hinweis auf den
  separaten Anzeigenamen. Fehlermeldungen markieren das betreffende sichtbare Feld; Unterfelder im
  erweiterten Objekt werden diesem zugeordnet. Speicherausfälle erhalten die Eingaben ebenfalls.
- HA-Store-Schema 1, Konfigurationsschlüssel, Profil-IDs, Config Entries und Werkzeugfreigaben bleiben
  erhalten. Kein automatisches Erzeugen/Umbenennen von Profilen und keine Migration.

Realistische nächste Schritte, Priorität 2, **bewertet, nicht als neuer Editor implementiert**:

| Bereich | Mit HA OptionsFlow möglich | Grenze / sichere Umsetzung |
| --- | --- | --- |
| Familienmitglieder | Auswahlschritt und Formular je Mitglied, Textname, NumberSelector für `portion`, Mehrfachauswahl für Anwesenheits-/Aufwärmtage | Stabile IDs erhalten; Löschen/Umbenennen bei Kalenderbezügen nicht still durchführen. |
| Wochentage | SelectSelector mit deutschen Labels und Mehrfachauswahl | Zwischen UI-Strings und vorhandenen Integer-Tagen 0–6 umwandeln; kein neues Speicherformat. |
| Tageszeitlimits | Formular mit sieben Zahlenfeldern und aktiv/deaktiviert je Limit | Fehlendes Limit von Null-Minuten-Limit unterscheiden. |
| Kalenderregeln | Eigene Unterformulare, EntitySelector und Auswahl vorhandener Profile/Effekte | Nur explizite Entity-Allowlist; Registry-ID und Berechtigungsprüfung erhalten. |
| Datum/Uhrzeit | DateSelector und TimeSelector verfügbar | Vorhandene YYYY-MM-DD-/HH:MM-Verträge an der UI-Grenze erhalten. |
| Erweiterte Regeln | Separater Menüschritt, optionale Objektansicht für Experten | Versions-/Referenzvalidierung weiterhin zentral; keine generische Weboberfläche notwendig. |

Die verfügbaren Selector-Klassen wurden im vorhandenen HA-Referenzcode geprüft. OptionsFlow kann
mehrere Schritte/Formulare zeigen, aber keine beliebige dynamische Tabellen-/Drag-and-drop-Oberfläche
ersetzen. Ein geführter Editor ist realistisch, benötigt jedoch eigene atomische Bearbeitungszustände
und Referenztests. Hier bleiben die Objektfelder mit klareren Hinweisen und verlustfreien Fehlerpfaden.

## Tests und nächste Abnahme

Neue Regressionen prüfen ungültige IDs und Felder, vollständigen Eingabeerhalt/Deep-Copies,
Revision und Reload, exklusive Datumsparameter, gesperrte Vorschlagskontexte, Besitzerbindung,
fehlende/doppelte Extras, Aufwärmbarkeit, drei plus zwei = fünf Portionen, Abneigungen nach
ID/Name sowie unbekannte/mehrdeutige Bezüge, Abwechslung, Ausnahmen, Zeitlimitfehler am späteren
Tag ohne Teil-POST und ungecachte Vorschau nach Konfigurationsänderung.

Echte HA-Laufzeittests sind ergänzt für Formular-Defaults, Fehlermarkierung, Korrektur/Speicherung/
Reload und die Vorschau über echte LLM-API-Klassen. Diese sind lokal mangels HA-Laufzeit nicht
ausführbar; kein Ersatz durch HA-Mocks. Ohne Commit-/Push-Freigabe wird keine neue GitHub-CI ausgelöst.
Die frühere grüne RC3-CI belegt nicht diese lokalen Änderungen.

Lokales Endergebnis: **559 Tests bestanden, keine fehlgeschlagen, zwei HA-Testmodule mangels
installierter HA-Laufzeit übersprungen**. Ruff, Formatprüfung, Repository-Check (112 Dateien,
keine Funde) und die Paket-/Publikationstests innerhalb der vollständigen Suite erfolgreich.
Die beiden neuen echten HA-Tests sind vorbereitet, wurden hier aber ausdrücklich nicht ausgeführt.

Manuelle Abnahme nach gesonderter Freigabe in einer Testinstallation:

1. Vier Familienprofile mit ungültigen IDs eingeben; sämtliche Werte müssen erhalten bleiben.
   IDs korrigieren, speichern und Integration/HA neu laden; gespeicherte Regeln prüfen.
2. Den natürlichsprachlichen Auftrag „Plane unsere Mittagessen für die aktuelle Woche … aber
   speichere noch nichts“ mit Gemma und GPT-OSS wiederholen. Kontextabruf muss vor einer Nachfrage
   nach konfigurierten Fakten erfolgen; `suggest_period` und `validate_only=true` im Trace prüfen.
3. Ausgabe der Portionssummen und Extras direkt gegen das Backend-ToolResult vergleichen.
   Kein gespeicherter Plan; keine POST-Anfrage und kein neuer Ausführungsbeleg für die Vorschau.
4. Nicht aufwärmbares Gericht, Zeitüberschreitung, abgelehntes Gericht, Doppelzuordnung und
   doppelte Datumsparameter absichtlich testen. Modell muss korrigieren oder gezielt fragen,
   statt denselben ungültigen Aufruf oder eine falsche Erfolgsbehauptung zu wiederholen.
5. Erst auf ausdrücklichen Speicherwunsch neuen schreibfähigen Kontext verwenden. Gleichzeitige
   externe Slotänderung/Timeout gesondert prüfen; unklare Ergebnisse dürfen keinen Retry auslösen.
6. Tokenverbrauch und Laufzeiten neu messen. Der größere, nur bei Planung geladene Regeltext
   ist beabsichtigt; keine gemessene Verbesserung der Modellbefolgung oder Geschwindigkeit behaupten.
