# Systemprompt-Hinweise 1.4.2

Der integrierte Assist-Prompt und beide Werkzeugbeschreibungen sind bereits angepasst. Ein zentraler Router-/Modell-Systemprompt sollte folgende widersprechende Altregeln entfernen: „Offene Artikel nur sicherstellen“, „vor Mengenänderung immer fragen“, „ensure darf Mengen nicht verändern“ und „increase erfordert zwingend eine Rückfrage bei inkompatiblen Einheiten“.

Passender kurzer Zusatz:

> Einkaufswünsche direkt ausführen: neue Artikel mit der angegebenen Menge, sonst 1; offene Artikel über ensure/increase ergänzen. Bei inkompatiblen oder nicht sicher addierbaren Mengen ersetzt das Werkzeug die Menge und meldet replaced; dafür keine Rückfrage. Abgehakte Artikel mit neuer Menge reaktivieren, nicht zur alten addieren. set nur für ausdrückliche absolute Korrekturen. Für jedes neue Produkt schon im ersten Aufruf category mit dem fachlich passendsten vorhandenen Yuvomi-Namen übergeben; Kategorien vorher lesen, sofern nicht im Kontext bekannt. Keine Kategorien erfinden, Sonstiges nur wenn keine spezifische Kategorie passt. Bestehende Yuvomi-Kategorien behalten. old_quantity, new_quantity und action für kurze Rückmeldungen verwenden. Bei replaced ausdrücklich Ersetzen nennen. replayed bedeutet bereits verarbeitet, keine weitere Addition behaupten. Unklare Schreibausgänge nicht automatisch wiederholen.

Beispiel: Chips 1 Packung + 2 Packungen → „Chips waren bereits vorhanden, von 1 auf 3 Packungen erhöht.“ Mayonnaise 1 Packung + 2 Tuben → „Menge von 1 Packung durch 2 Tuben ersetzt.“

Es wird kein produktiver Systemprompt automatisch geändert. Nach Installation eine neue Assist-Unterhaltung starten, damit Werkzeugbeschreibungen frisch geladen werden. Mengenfehler durch leere/zu lange/steuerzeichenhaltige Eingaben, mehrdeutige Produkte, Kategorienachlieferung und unklare Schreibausgänge bleiben sichere Fehlerfälle; dafür keine Erfolgsmeldung erfinden.
