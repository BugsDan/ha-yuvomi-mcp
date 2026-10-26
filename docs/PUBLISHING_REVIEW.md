# Historische Veröffentlichungsprüfung der Baseline 1.4.2

Dieser Bericht dokumentiert die abgeschlossene Baseline-Prüfung, nicht die aktuellen 1.4.3-Codeänderungen. Inzwischen bestehen Tag v1.4.2 und ein unveröffentlichter geprüfter Release-Entwurf. Für den lokalen Stand 1.4.3 gilt [TEST_REPORT_1.4.3.md](TEST_REPORT_1.4.3.md).

## Umfang

Das öffentliche Repository [BugsDan/ha-yuvomi-mcp](https://github.com/BugsDan/ha-yuvomi-mcp) besteht. 1.4.2 ist die erste öffentliche Baseline. Die damalige Bereinigung korrigierte ausschließlich zwei HA-Testdoubles/Importkontexte und die Dokumentation. Dabei blieben alle Dateien unter custom_components, Versionsfelder, Laufzeitabhängigkeiten und gespeicherte Konfigurationen unverändert.

Die erste HA-CI-Ausführung 40206049922 fand zwei Fehler im Testaufbau. Der isolierte Setup-Import erhält nun den echten Paketkontext; die synchrone redact-Methode verwendet einen synchronen Mock. Keine Tests oder Assertions entfernt, keine Fehler ignoriert und keine Laufzeitfunktion angepasst.

## Öffentliche Baseline und Kompatibilität

README, CHANGELOG, Release- und Abnahmedokumentation beschreiben 1.4.2 als ersten öffentlichen Stand. Historische Release-Dateien interner Entwicklungsstände sind entfernt. Notwendige Hinweise zum vorhandenen Speicheradapter stehen separat in STORAGE_COMPATIBILITY.md. Dessen Entfernung ist nicht sicher begründbar: bestehende manuelle Installationen können noch alte Speicher samt offenen Journalvorgängen haben. Migrationscode und zugehörige Regressionen bleiben erhalten.

Die Notizanforderungen für 1.4.3 stehen in PLAN_1.4.3.md. Kein neues Werkzeug, kein note-Schema und keine Versionsanhebung in dieser Bereinigung.

## Datenhygiene und Prüfungen

Nur die durch tools/repository_files.py ausgewählten Dateien veröffentlichen. Vor dem Commit staged diff, `git diff --cached --check` und `python tools/check_repository.py --staged --tag v1.4.2` prüfen. Der Index-Scan prüft die tatsächlichen Blobs und gibt mögliche Secrets niemals im Klartext aus. Mustererkennung ersetzt keine sorgfältige Sichtung oder ergänzendes Secret-Scanning.

Ausgeschlossen bleiben .venv, Caches, temporäre Testverzeichnisse, dist, alte ZIPs, reference, lokale Agent-/Editor-Dateien, .storage, Konfigurationen, Backups, Logs und Secret-Dateien. Synthetische Testtoken und Loopback-Testserver enthalten keine Zugangsdaten einer Installation. Öffentlicher Maintainer-Handle und Projektlinks sind beabsichtigt.

Lokale Prüfung am 25.10.2026: 373 Tests bestanden, genau das HA-Testmodul mangels HA unter Windows/Python 3.12 übersprungen. Ruff-Lint, Formatprüfung und Publikations-/Versionscheck erfolgreich. Der CI-Job installiert zwingend echtes HA 2026.10.2 unter Linux/Python 3.14 und führt auch diese Tests aus. HACS und hassfest laufen als separate Jobs. Maßgeblicher Nachweis für den zu veröffentlichenden Commit: [GitHub Actions](https://github.com/BugsDan/ha-yuvomi-mcp/actions/workflows/tests.yml); alle vier Jobs müssen erfolgreich sein. Lint, Format, Paketierung und Versionskonsistenz gehören ebenfalls zur Prüfung.

## Verbleibende Abnahme

Noch keine produktive HA-/Yuvomi-Verbindung, Installation oder Modell-/Alexa-Abnahme. HACS-Installation und Übernahme einer bestehenden manuellen Einrichtung sind nach veröffentlichtem Release vom Betreiber auf gesichertem System zu prüfen. Nicht durch CI garantierbar: globale Exactly-once-Semantik gegenüber externen Clients und fehlerfreie Modellentscheidungen. Die dokumentierten Journalbarrieren und das begrenzte Retry-Fenster bleiben erhalten.

Tag, Release-Entwurf und Veröffentlichung erst nach gesonderter Freigabe. Anleitung: GITHUB_HACS.md.
