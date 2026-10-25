# Anforderungen für 1.4.3: Einkaufsnotizen

Status: geplant, noch nicht implementiert. Anwendung, Werkzeugschemata und Versionsfelder bleiben auf 1.4.2. Kein zusätzliches Produktgedächtnis in HA.

## Verhalten

- Optionales `note`-Feld beim Hinzufügen einzelner Artikel und pro `items[]`-Element im Sammelwerkzeug. Nur ausdrücklich übergebene Notizen schreiben; ausgelassenes Feld erhält vorhandene Notizen unverändert.
- Notizen bestehender Artikel gezielt ergänzen, ersetzen oder löschen können. Ergänzen erhält vorhandenen Text; Ersetzen/Löschen erfordert eine ausdrückliche Operation. Leerer Text darf nicht beiläufig als Löschauftrag interpretiert werden; die endgültigen Schemas müssen Abwesenheit, Ersetzen und Löschen eindeutig trennen.
- Reine Notizänderung ist eine eigene Operation: keine Mengenaddition, kein Default +1, keine Neuanlage, Reaktivierung oder Kategorieänderung. Der Notizpfad darf nicht versehentlich die ensure/increase-Logik auslösen.
- Beim normalen Einkaufsauftrag ohne Notiz bleiben bestehende Notizen erhalten, auch bei Reaktivierung. Ein vorhandener Notiztext darf nicht stillschweigend durch eine Modellangabe überschrieben werden; vorhandener Text plus neue Angabe erfordert einen ausdrücklich gewählten Ergänzungs-/Ersetzungsmodus.
- Unicode und Umlaute erhalten; Leertext, Länge und Steuerzeichen anhand des tatsächlichen Yuvomi-Vertrags validieren. Keine HTML-Verarbeitung oder Modellaufrufe im Backend.

## Technische Klärung vor Implementierung

Zuerst im offiziellen Yuvomi-2.79.0-Quellcode prüfen, ob und unter welchem Feld GET/POST/PATCH Notizen unterstützen, welche Grenzen gelten und wie Löschen dargestellt wird. Hier wird kein ungeprüfter REST-Vertrag vorausgesetzt. Falls der Server dies nicht unterstützt, keine Scheinfunktion oder HA-Ersatzdatenbank einführen; Einschränkung dokumentieren.

Gezielten Notizpfad mit denselben shopping:read/write-Rechten und festen REST-Endpunkten entwerfen. Neue Werkzeuge gegebenenfalls nur nach ausdrücklicher Freigabe; keine generischen REST-Schreibrechte. Einzel-/Sammelaufrufe sollen denselben Notizprozessor nutzen. Unveränderte bisherige Aufrufe müssen kompatibel bleiben.

Notizoperationen einschließlich Modus und Zieltext in Ausführungsidentität, Journal und Zustandsabgleich berücksichtigen. Derselbe Retry darf weder Menge noch Notiz nochmals ergänzen. Mehrdeutige Artikel vor dem Schreiben ablehnen. Vor PATCH aktuellen Bestand einschließlich Notizen prüfen; fremde Änderungen nicht unbemerkt überschreiben. Ohne serverseitige atomare Vorbedingungen bleibt ein Parallelitätsrest zwischen Prüfung und Schreiben. Unklare Schreibausgänge wie bisher sperren und nur lesend prüfen.

## Abnahmekriterien und Tests

- Neu mit/ohne note; Einzel- und Sammelwerkzeug; Unicode und Freitext.
- Vorhandene Notiz bei ausgelassenem Feld und normaler Mengenaktion unverändert.
- Explizites Ergänzen, Ersetzen und Löschen; leer/ausgelassen eindeutig unterschieden.
- Reiner Notizauftrag lässt Menge, Kategorie und Einkaufsstatus unverändert, auch bei abgehakten Artikeln.
- Identische Retries, neue kurzfristige Retry-IDs, parallele Aufträge, Neustart und Timeout führen nicht zu doppelter Ergänzung oder Mengenaddition.
- Fremde Änderungen und mehrdeutige IDs sicher behandeln; gemischte Sammelaufrufe melden klare Einzelergebnisse und stoppen bei unklarem Ausgang.
- Bestehende Tests für Mengen, Kategorien, Journal, Freigaben, Aufgaben und Kalender bestehen unverändert.

Erst nach Implementierung und Prüfung Versionsfelder gemeinsam auf 1.4.3 erhöhen und separate Release-Dokumentation erstellen.
