# Veröffentlichungsprüfung: ha-yuvomi-mcp / 1.4.2

## Ergebnis und Umfang

Vorbereitet für das noch anzulegende öffentliche Repository https://github.com/BugsDan/ha-yuvomi-mcp. Anwendungsversion und Domain bleiben 1.4.2 bzw. yuvomi_mcp. Kein Repository auf GitHub, keine Commits, Tags, Pushes oder Releases erzeugt; keine produktive HA-/Yuvomi-Verbindung und keine Installation durchgeführt. Der verbundene GitHub-Zugang wurde nicht benutzt.

Der vorgesehene Quellbaum besteht ausschließlich aus den durch tools/repository_files.py ausgewählten Dateien. Ein sauberes Review-ZIP entsteht mit tools/prepare_repository.py; es enthält keine Git-Historie. Vorhandene ältere lokale Release-Archive sind nicht der geprüfte Veröffentlichungsquellbaum und sollten nicht ungeprüft hochgeladen werden.

## Vorbereitete Änderungen

- hacs.json: Namen, HA-Mindestversion 2026.10.2, README-Darstellung, Installation aus dem Release-Quellbaum, ausgeblendeter Default-Branch.
- Manifest: Dokumentations-/Issue-Links für BugsDan/ha-yuvomi-mcp, @BugsDan als codeowner und sortierte Metadaten. Version, Domain, Requirements und Entry-Format erhalten.
- Originale lokale Brand-Grafik als 256×256-RGBA-PNG und editierbare SVG-Quelle. Keine Fremdgrafik, keine eingebetteten Personen-/Standortmetadaten; Lizenz MIT.
- .gitignore/.gitattributes, CODEOWNERS, CONTRIBUTING, SECURITY und Drittanbieterhinweise.
- README und GITHUB_HACS.md für Erstveröffentlichung, Draft-Release, benutzerdefiniertes HACS-Repository und Übernahme vorhandener Config Entries.
- Tests: Python 3.12 und Linux/Python 3.14 mit HA 2026.10.2; zusätzlich HACS Action und hassfest. Rechte standardmäßig nur contents:read, keine PR-Kommentare und keine produktiven Zugangsdaten.
- Release-Workflow: vMAJOR.MINOR.PATCH-Tag, Versionsprüfung, wiederverwendete Prüfungen, Build und ausschließlich Release-Entwurf. Nur dieser Job erhält contents:write; Veröffentlichung bleibt ein bewusster menschlicher Schritt.
- Publikationswerkzeuge: explizite Dateiauswahl, lokale Metadaten-/Tagprüfung, Hygieneprüfung und Prüfung tatsächlich gestagter Git-Blobs. Build umfasst nun auch Brand-Assets und Repository-Metadaten.

## Datenhygiene

Die bisherige interne Serveradresse wurde aus dem Einrichtungsvorschlag, den Tests und dem Live-Test-Hilfsprogramm entfernt. Der neutrale Default lautet jetzt http://yuvomi.example:3015/mcp und ist nur ein Beispiel. Der optionale Live-Test verlangt eine ausdrücklich angegebene URL und bleibt lesend. Er wurde nicht gegen eine Installation ausgeführt. Bestehende HA-Entries lesen weiterhin ihre gespeicherte URL und sind von dieser Vorschlagsänderung unberührt.

Manuelle Sichtung und automatischer Scan der vorgesehenen Dateien ergaben keine erkannten echten API-Token, privaten Schlüssel, persönlichen Benutzerpfade oder privaten Server-IPs. Absichtliche synthetische Test-Token und Loopback-HTTP-Testserver bleiben enthalten; sie enthalten keine Zugangsdaten einer Installation. Der gewünschte öffentliche Maintainer-Handle @BugsDan und offizielle Projektlinks sind bewusst enthalten.

Ausgeschlossen: .venv, Test- und Lint-Caches, temporäre Testverzeichnisse einschließlich deren temporärer Git-Indizes, dist und alte ZIPs, reference mit heruntergeladenen Upstreamquellen, lokale Agent-/Editor-Dateien, .storage, Konfigurationen, Backups, Logs und Secret-Dateien. Keine zusätzliche Historie aus einem anderen Projekt wird importiert.

Grenzen: Mustererkennung und manuelle Sichtung sind kein mathematischer Nachweis der Geheimnisfreiheit und kein vollständiger Ersatz für Secret-Scanning. Vor dem ersten Commit staged diff und Index prüfen; vor späteren Pushes auch die Git-Historie berücksichtigen. Der Index-Test beweist, dass ein noch gestagtes synthetisches Secret trotz bereinigter Arbeitskopie erkannt wird. Findings werden nur als Datei/Zeile/Typ ausgegeben, nicht mit dem Secret selbst.

## Funktionsgleichheit und Testresultate

Vergleich gegen das bisherige lokale 1.4.2-Source-ZIP: 12 Laufzeitmodule bytegleich. const.py unterscheidet sich semantisch ausschließlich im anonymisierten Einrichtungsvorschlag; VERSION und alle übrigen Konstanten bleiben gleich. Einkaufslogik, Kategorien, Journal, Retry-/Idempotenzschutz, Mengen, Assist-Werkzeuge und Optionsverhalten wurden nicht verändert. Metadaten und neue Brand-Dateien beeinflussen keine gespeicherte Konfiguration.

Ein versehentlich durch den früheren Versionswechsel entstandener Dev-Pin pytest-asyncio==1.4.2 war auf PyPI nicht verfügbar. Er ist auf die tatsächlich vorhandene und bisher benutzte Testversion 1.4.0 korrigiert. Keine neue Laufzeitabhängigkeit.

- **373 lokale Tests bestanden, 1 HA-spezifisches Modul übersprungen.** Alle bisherigen 352 Tests bestehen weiter; 21 Publikations-/Paketierungsprüfungen ergänzt.
- Ruff-Lint und Formatprüfung erfolgreich.
- Publikationscheck mit Tag v1.4.2: keine Findings; falsche Tags werden abgewiesen.
- Beide Workflow-Dateien lokal als YAML geparst; Trigger, lesende Standardrechte und gebundener Draft-Job geprüft.
- Offizielle HA-2026.10.2-Quellverträge erneut geprüft, Hashnachweise in ha_api_evidence.json aktualisiert/bestätigt. Keine produktive HA-API kontaktiert.
- Review-ZIP: nur ausgewählte Dateien; CRC, Dateigrenzen, Inhalt und Hygiene werden vor Übergabe erneut geprüft. Die Tests prüfen außerdem Brand- und Metadateneinschluss in den Release-Archiven.

Nicht als bestanden behauptet: tatsächliche GitHub-Action-Ausführung, Linux-HA-Plattformtests, HACS-/hassfest-Prüfung gegen ein existierendes öffentliches Repository und HACS-Übernahme auf HA. Diese Schritte benötigen das spätere Repository bzw. die Betreiberabnahme. Lokale YAML-/Metadatenprüfungen sind keine Zertifizierung durch HACS.

## Nächste Freigabepunkte

1. Diese Änderungen und die MIT-Lizenzwahl prüfen.
2. Erst danach ausdrücklich Repository-Erstellung und Upload freigeben.
3. GitHub-Checks abwarten; anschließend Tag v1.4.2 und den erzeugten Draft prüfen und Veröffentlichung ausdrücklich ausführen.
4. Erst nach veröffentlichtem Release die manuelle HA-Installation gemäß GITHUB_HACS.md in HACS übernehmen. Kein Config Entry und kein Journal wird dafür gelöscht.
