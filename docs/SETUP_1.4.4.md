# Einrichtung und Abnahme 1.4.4

## Sicherung und unveränderte Standards

Lokale Prüfversion, keine produktive Installation erfolgt. Vor einer später ausdrücklich freigegebenen Installation vollständiges HA-Backup und Sicherung des bisherigen custom_components/yuvomi_mcp-Verzeichnisses erstellen. Config Entries, Tokens, enabled_tools und der bestehende Journalstore bleiben erhalten. Der Expositionsmodus fehlt bei Altinstallationen und bedeutet dann unverändert assist. Keine Werkzeugfreigabe wird ergänzt.

Der neue atomare HA-Store yuvomi_mcp.<entry_id>.planning, interne Version 1, enthält nur Konfiguration/Revision. Er wird erst bei bewusster Optionsbearbeitung oder Menüaktion gelesen. Kein Rezept-/Vorratskatalog. Unbekannte Speicherversionen und andere URL-Bindungen werden nicht überschrieben. Bestehende offene Shopping-/Recipe-Belege bleiben erhalten; meals ist ein neuer Journaltyp unter demselben Schema 2. Für Downgrade zuerst alle meals-Belege sichern/klären: ältere Versionen können diesen Typ sicher ablehnen; Journal nie manuell löschen. Die 512er-Journalgrenze kann Menüschreiben blockieren, kein stilles Entfernen unklarer Vorgänge.

## Eigene LLM-API bewusst auswählen

1. Integration → Konfigurieren → LLM-API auswählen. assist ist der unveränderte Standard; dedicated stellt Yuvomi ausschliesslich über die eigene API bereit.
2. Im gewünschten Local-OpenAI-Conversation-Agent die API **Yuvomi MCP Familie** bewusst auswählen. Agenten werden durch die Integration nicht verändert. Ohne bewusste Auswahl fehlen nach dedicated-Umschaltung dessen Tools.
3. Nur gewünschte Werkzeuge in den Integrationsoptionen freigeben. Moduswechsel erweitert die Liste nicht. Für Familienorganisation allein ist Assist zusätzlich nicht nötig; bei Kombination bleiben andere Assist-Beiträge vorhanden. HA ergänzt beim Kombinieren API-Namensräume.
4. Rückkehr: Modus assist und die vorherige Agentenauswahl wiederherstellen. Änderungen an bereits gehaltenen Werkzeugen werden bei Aufruf erneut geprüft.

API-ID ist stabil je Entry; der kurze Anzeigename ist wegen der erzwungenen Einzelinstanz eindeutig und hält kombinierte Standard-Werkzeugnamen unter üblichen Providergrenzen. Registrierung/Abmeldung wird an den Entry-Lebenszyklus gebunden. Tatsächliche Auswahl im installierten Agenten nach Reload bleibt ein realer HA-Abnahmepunkt; der lokale Local-OpenAI-Referenzstand 1.12.1 unterstützt Mehrfachauswahl und HA-API-Übergabe.

## Planungskonfiguration über HA

Konfigurieren → Menüplanung. Kein YAML nötig. Einfache Angaben haben eigene Felder; komplexe Listen/Regeln werden zunächst über validierte HA-Objektfelder gepflegt. Das ist eine bewusst einfache Erstoberfläche, noch kein komfortabler Assistent pro Familienmitglied/Kalenderregel.

Zeitzone Europe/Zurich; Periodenanker standardmässig 21.10.2026 (Mittwoch), Dauer 7 Tage, Einkaufstag 2 (Mittwoch), Planungstage 0–4 (Montag–Freitag), lunch um 12:00. Andere Anker/Längen bis 31 Tage/Tage sind zulässig. Anker und Länge bestimmen die Perioden; der Einkaufstag allein verschiebt keinen bereits gespeicherten Anker. Bei gewünschtem anderen Periodenbeginn Anker bewusst anpassen. Tageszeitlimits meinen die gesamte Koch-/Back-/Wartezeit. Vier ist die Basis des Rezepts, keine Mindestportionenzahl.

Beispiel für das Feld profiles (stabile IDs selbst wählen, keine realen Namen vorgeschrieben):

```json
{
  "person": {"name": "Person", "days": [0,1,2,3,4], "portion": 1, "dislikes": [], "preferences": "Mag Gemüse"},
  "kind_a": {"name": "Kind A", "days": [0,1,2,4], "portion": 1, "reheat_days": [3], "dislikes": [], "preferences": ""}
}
```

reheat_days beschreibt zusätzlichen Aufwärmbedarf am Zieltag auch bei Abwesenheit zuhause. Gemma ordnet ein akzeptiertes, wiederaufwärmbares Gericht vom vorherigen oder vorletzten Kalendertag zu. Beispiel Mittwoch 3 + Donnerstag 2 = 5 kochen, Rezeptbasis 4 → Faktor 5/4. Zutaten werden nur am Kochtag gespeichert. Keine Erfassung tatsächlich verzehrter Portionen oder Restenbestände.

Zeitlimits als Objekt mit Tagesnummern, z.B. `{"0":45,"2":60}`. Fehlender Tag bedeutet kein Limit. Das erweiterte Feld enthält:

```json
{
  "days": [0,1,2,3,4],
  "rest_recipe_id": null,
  "rest_day": null,
  "rest_excluded_days": [],
  "emergency_recipe_ids": [],
  "repeat_exceptions": [],
  "reheat_time_min": null
}
```

Rezept-IDs stammen aus Yuvomi. rest_day null erlaubt flexible Auswahl, fester Tag 0–6 nur mit gewähltem Resten-Rezept. repeat_exceptions darf nur bewusst ausgewählte Resten-/Notfall-IDs enthalten. Resten benötigt keinen Beweis vorhandener Reste. reheat_time_min nur setzen, wenn die tatsächliche gesamte Aufwärmzeit als gültige Familienvorgabe bekannt ist; bei Zeitlimit ohne belegte Dauer wird nicht geraten.

Kalender-Allowlist separat mit dem HA-Entity-Selector auswählen. calendars zunächst `{}`. Beispielregel für eine ausdrücklich gewählte Entity:

```json
{
  "abwesenheit": {
    "entity": "calendar.familie", "profiles": ["person"],
    "match": "Abwesend", "match_mode": "exact",
    "effect": "absent", "priority": 10, "required": true, "whole_day": false
  }
}
```

Nur calendar_entities ausgewählte Entities sind erlaubt. effects: present/absent/reheat/no_reheat; Literalsuche exact/prefix/contains ohne semantische Deutung. Höchste Priorität gewinnt je Wirkung; gleichrangiger Widerspruch → Rückfrage. Kein Ereignis → feste Profilregel. Erforderlicher Kalender fehlt → Fehler. Soweit registriert wird die Registry-ID gespeichert; Umbenennung/Neuanlage erfordert bewusste Prüfung im Editor. Aktueller Aufrufer braucht Entity-Leserechte; ohne Benutzerkontext kein stiller Adminzugriff. Ganztägiges Ende exklusiv; mehrdeutige/ungültige Sommerzeitstunde wird abgewiesen.

## Drei Menüwerkzeuge bewusst freigeben

get_menu_plan braucht meals:read; Kontext liest zusätzlich Rezepte und bei konfigurierten Regeln erlaubte HA-Kalender. save_menu_plan braucht meals:write (serverseitig inklusive read). Keine zusätzlichen generischen REST-Rechte und kein shopping-/pantry-Schreiben. Der Server entscheidet Tokenrechte; sie werden nicht durch die Toolfreigabe ersetzt.

- „Was gibt es morgen?“: get_menu_plan mit explizitem ISO-Datum. Keine Rezept-, Profil- oder Kalenderabfrage. Ganze Woche nur mit detail=full auf ausdrücklichen Wunsch; kurze Wochenabfrage liefert heute/morgen innerhalb der Periode.
- Ganze Wochenplanung: **bewusst neue separate Conversation starten**, get_menu_planning_context mit action=create_period, period=next; Gemma wählt, save_menu_plan speichert den validierten Plan. Keine automatische Isolation oder Änderung einer Conversation-ID.
- „Plane am Donnerstag Carbonara“: Datum eindeutig auflösen; action=replace_day, date und exakter requested_recipe. Der zurückgegebene Rezeptkontext enthält nur die exakte Variante. Der Server-Rezeptbestand wird intern vollständig gelesen; Familien-/Regelkontext bleibt auf relevante Tage begrenzt. Bei mehreren Varianten Rückfrage. Ohne konkretes Rezept muss die relevante Auswahl mitgeliefert werden; das kann mehr Kontext beanspruchen.
- Reine Alternativvorschläge: suggest_day; Speichern wird damit verweigert.

Der Kontext ist an Aufrufer und Scope gebunden und läuft nach 300 Sekunden ab; nach Neustart neuen Kontext verlangen. Modellantworten wählen genaue IDs/Datumszuweisungen. Jede freie konfigurierte Mahlzeit der Zielperiode muss abgedeckt sein, belegte Slots auslassen. Hard-Rule-Fehler gezielt korrigieren, keine versteckte deterministische Rezeptwahl. Eindeutige neue Pläne/Tagesänderungen brauchen keine weitere Bestätigung. Unbekannte/generische Tools behalten ihre bisherige Bestätigung.

Ein einzelner Mahlzeitslot kann nicht still mehrere unterschiedliche Gerichte für zuhause/auswärts darstellen. Neue Zusatzportionen und zugehörige Aufwärmtage werden gemeinsam innerhalb des autorisierten Planumfangs gespeichert. Bereits eindeutig dokumentierte Kochquellen können lesend genutzt werden; nicht dokumentierte vorhandene Reste werden nicht geraten. Abhängige andere Tage bei Tagesänderung werden nicht heimlich umgeschrieben. Für neue Zusatzbedarfe ausserhalb der Zielperiode muss der Umfang bewusst geklärt werden. Über Periodengrenzen bleibt die vorherige-Perioden-Regel wirksam; nur konfigurierte Ausnahmen erlauben Wiederholung.

Am Aufwärmeintrag fehlen native recipe_id und Zutaten, damit Yuvomis GUI-Transfer kein zweites vollständiges Rezept überträgt. Herkunft/Titel/Portionen stehen im Notizblock; Rezept-/Bildbutton fehlt dafür. Kochtag behält Rezeptverknüpfung und skalierte eigene Zutaten. Freie manuelle Notizen bleiben erhalten. Beschädigte Blöcke/Überlänge werden nicht still überschrieben. GUI-Neuverknüpfung oder manuelle Änderung ist eine relevante Quellenänderung.

## Wiederholungen und unklare Ergebnisse

Innerhalb der Integration werden Menüschreibaktionen serialisiert. POST apply-plan verwendet Idempotency-Key, vor I/O liegt ein persistenter prepared-Beleg vor. prepared/unknown blockiert weitere Menüschreibaktionen auch nach Neustart. Konfigurieren → Ausführungen prüft ausschliesslich lesend; state_observed ist keine bewiesene eigene Ausführung. Keine automatische Wiederholung oder Rückabwicklung bei Teilfehlern.

HA-Kontext und Tool-ID sind keine garantierte ursprüngliche Alexa-Request-ID über jede erneute Anfrage hinweg. Derselbe aktive Kontext liefert sein Ergebnis erneut; ein ähnlicher bereits abgeschlossener Auftrag erhält zusätzlich eine konservative 120-Sekunden-Barriere. Es wird keine vollständige Exactly-once-Garantie über neue Alexa-Anfragen/andere Clients behauptet. Journalgrenzen und Server-TTL bleiben relevant. Nach Timeout tatsächlichen Zustand/Beleg prüfen. Tagesersetzung liest erneut und ersetzt genau einen Datum-/Typ-Slot; das akzeptierte verbleibende Race-Fenster zu fremden Clients bleibt bestehen.

Die zentrale Planungskonfiguration, PLANNING_PROMPT, Datenaufbereitung, Validierung und Speicherung sind ohne Conversation-Session aufrufbar. Ein virtueller Schalter, HA-Automation oder Hintergrunddienst ist nicht implementiert. Lange Modellplanung kann über Alexa auslaufen; ganze Wochen daher zunächst in separater Text-/Planungssitzung. Keine automatische Fertigmeldung über ungetestete Kanäle.

## A/B/C-Test mit Gemma

Aktuelle Betreiberreferenz: Assist mit neun Werkzeugen **6390**, Assist deaktiviert **2792** vollständige Prompt-Tokens; Differenz **3598** umfasst alle zusätzlichen Assist-Beiträge. Frühere 6604/ungefähre 9800 sind historische Referenzen, kein identischer aktueller Vergleich.

1. A: bisherigen lokalen/gesicherten Integrationsstand mit neun genannten Werkzeugen und bisherigen Beschreibungen messen; Systemprompt und Konfiguration sichern. Falls A seit der letzten Messung abweicht, A neu messen statt 6390 voraussetzen.
2. B: 1.4.4, Modus assist, dieselben neun Tools, unveränderter Agent-/Router-Systemprompt, Rezept-/Menütools weiter aus.
3. C: 1.4.4, dedicated, im gleichen Agenten allein „Yuvomi MCP Familie“ auswählen, dieselben neun Tools. Diese notwendige API-Auswahl ist der einzige zusätzliche Variablenwechsel gegenüber B.

Vor jedem Vergleich Modell neu laden; immer neue Conversation, exakt „hallo“, gleiche GGUF-/Modell-/Template-/Inferenzkonfiguration. Tatsächliche Input-/Prompt-Tokens aus LM-Studio-Serverlogs erfassen; Completion getrennt. A−B misst Beschreibungsänderungen, B−C die geänderte API-Zusammenstellung. Keine Schätzung als Messung und nicht 3598 pauschal als API-Ersparnis ausgeben. Werkzeugsnapshots: [AB_TOOL_DEFINITIONS_1.4.4.json](AB_TOOL_DEFINITIONS_1.4.4.json). Gewöhnlicher Yuvomi-Basisprompt bleibt bei den neun Tools unverändert; Planungsregeln werden erst bei bewusst freigegebener Menüaktion geladen.

Zusätzlich gleiche Gemma-Fälle prüfen: Kategorien, Mengen/Notizen, Aufgaben/Termine, exakte Rezeptvarianten, Menüabfrage, explizite Tagesänderung, Wochenplanung und unklare Ausgänge. Nach einer Planungsunterhaltung tatsächliche Kontexttrennung prüfen; eine neue API ist keine automatische Historienisolation.
