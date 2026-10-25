# Speicherkompatibilität bestehender manueller Installationen

Diese Hinweise gelten für frühere interne Entwicklungsstände. Eine Neuinstallation der ersten öffentlichen Version 1.4.2 benötigt keine historische Migration.

## Warum der Adapter erhalten bleibt

Manuell installierte Entwicklungsstände können noch Schema-1-Speicher mit Produktkatalog und Ausführungsjournal besitzen. Deren Abwesenheit in bestehenden Installationen ist nicht nachgewiesen. Ein Entfernen des Lesepfads könnte offene oder unklare Schreibvorgänge verlieren oder deren Wiederholungsschutz umgehen. Deshalb bleiben journal.py, persistence.py und ihre Migrationstests unverändert.

Der vollständige Schema-1-Speicher wird einmalig atomar unter `.storage/yuvomi_mcp.<Entry-ID>.catalog_archive_v1` archiviert und zurückgelesen. Erst nach bestätigter Archivierung wird das Journal in den aktiven Schema-2-Speicher übernommen. Sämtliche Journalzustände und Ergebnisdaten bleiben erhalten. Das Archiv wird niemals als aktives Produktwissen genutzt.

Bei Archivierungsfehlern, Konflikten, unbekannten Formaten oder abweichender Yuvomi-URL bleiben die Daten erhalten und Einkaufsaktionen gesperrt. Aufgaben und Kalender bleiben verfügbar. Die äußere HA-Store-Version bleibt 1, die interne Datenversion 2. Aktuelle Schema-2-Journale brauchen keine Migration; frische Installationen erzeugen kein Altkatalogarchiv.

## Betrieb und Rückweg

Config Entries, Tokens und Freigaben behalten ihre Identität. Kein Migrationsschritt schreibt nach Yuvomi. Speicher und Archive nicht manuell bereinigen. Bei Problemen vollständiges Backup und Ausführungszustände prüfen.

Ein Altkatalogarchiv ist kein laufendes Journalbackup. Ältere Entwicklungsstände verstehen Schema 2 möglicherweise nicht. Ein Rückweg erfordert eine konsistente vollständige Sicherung und Prüfung der seitdem erfolgten Yuvomi-Schreibaktionen; niemals einen veralteten Journalstand über neuere Vorgänge zurückspielen.
