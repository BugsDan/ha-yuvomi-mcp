# Kategorieprüfung 1.4.2

Bestehende Yuvomi-Artikel behalten immer ihre aktuelle Kategorie. Für neue Artikel ist eine ausdrücklich mitgelieferte Kategorie erforderlich; sie wird gegen die aktuellen Yuvomi-Kategorien geprüft. Eindeutige Unicode-/Schreibkorrekturen liefern den aktuellen Originalnamen, mehrdeutige oder ungültige Angaben erreichen den REST-Schreiber nicht. Kein impliziter Sonstiges-Fallback.

Sammelwerkzeug: `category` ist innerhalb jedes `items[]`-Objekts sichtbar und beschrieben. Einzelwerkzeug: gleiches Feld auf oberster Ebene. Der Schema-Roundtrip über probatio ist getestet. Kategorienachlieferung meldet pro betroffenem Artikel `valid_categories`; die Vorprüfung schreibt weder Artikel noch Produktdaten. Eine fehlgeschlagene Kategorienabfrage sperrt Schreibaktionen.

Es gibt keine HA-Kategoriehistorie und keine automatische Bestätigung. Manuelle Yuvomi-Änderungen sind beim nächsten neuen Vorgang maßgeblich. Ein identischer wiederholter Vorgang liefert seinen historischen Journalbeleg zurück, ohne erneut zu schreiben.
