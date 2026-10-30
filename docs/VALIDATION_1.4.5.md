# Lokale Abnahme 1.4.5

Stand: 30.10.2026. Lokaler Entwicklungskandidat auf `dev/planning-reliability`, Basis `896e523157be158e5366cb6ad486db4c342e7a1e` (veröffentlichtes v1.4.4-rc3). Kein Commit, Push, Tag, Release oder produktiver Zugriff. Bereits vorhandene unveröffentlichte Planungsverbesserungen wurden als Grundlage weitergeführt.

## Etappen und Ergebnisse

1. Yuvomi-Vertrag lesend gegen offizielle 2.79.0-Git-Objekte geprüft. Mitgliedschaft, Mahlzeittitel und GUI-Skalierung separat nachvollzogen; [API-Belege](YUVOMI_API_1.4.5.md).
2. Bestehende Planungs-/Zuverlässigkeitsregression nach Backend-Erweiterung: **74 bestanden**.
3. Neue Cooking-only-Regression einschliesslich Ein-/Zweitagesquellen, ausschliesslichem Mitnahmebedarf, Konflikten, Overrides und Neustartbarrieren: zunächst **26**, danach **40** neue Fälle bestanden.
4. Nach abschliessender Präzisierung der Anwesenheitsprüfung bei Tagesaktionen: **602 bestanden, 0 fehlgeschlagen, 2 übersprungene HA-Testmodule** in der gesamten lokalen Suite. Darin **43 neue Backend-/Vertragsfälle** für 1.4.5. Vorhandene Tests wurden nicht deaktiviert; bisherige Runtime-Vorschautests wurden auf die bewusst neu einzurichtende Standardwoche angepasst, ihre Sicherheitsassertions bleiben erhalten.
5. Ruff und Formatprüfung: erfolgreich. Repository-/Versions-/HACS-Metadaten-/Publikationsprüfung: keine Befunde. `git diff --check`: erfolgreich. Paketbau und Byte-/SHA-256-Prüfung erfolgen über den vorhandenen reproduzierbaren Paketbauer.

Reproduzierbare Befehle im Projekt (Python mit vorhandenen Testabhängigkeiten):

```text
python -m pytest -q -ra --basetemp=.test-tmp-145-release-candidate --junitxml=.test-tmp-145-release-candidate/results.xml
python -m ruff check custom_components tests tools
python -m ruff format --check custom_components tests tools
python tools/check_repository.py --tag v1.4.5
git diff --check
python tools/build_release.py
```

Der rohe lokale JUnit-Bericht bleibt im ignorierten Testverzeichnis, nicht im öffentlichen Quellpaket. Die ZIPs enthalten nur die explizite Publikationsdateiliste; keine HA-Stores, Zugangsdaten, Testtempverzeichnisse oder Git-Daten.

## Was lokal nicht bestätigt ist

Die Windows-Testumgebung besitzt Python 3.12 und kein importierbares Home Assistant. `tests/test_ha_runtime.py` und `tests/test_homeassistant.py` werden deshalb am Modulimport übersprungen. **Keine erfolgreiche echte HA-2026.10.2-Laufzeitprüfung für diesen neuen Stand behaupten.** Vorherige RC3-CI-Ergebnisse sind kein Nachweis für 1.4.5.

Ein echter HA-Test für die neuen Selectors, erhaltene fehlerhafte Eingaben, atomaren Entwurfsspeicher und Wiederherstellung wurde ergänzt. Der bestehende Test der realen LLM-API mit schreibgebundenem Prüfkontext wurde auf die neue Standardwoche umgestellt. Es werden keine HA-Objekte durch Mocks ersetzt; entfernte Yuvomi-Daten bleiben isolierte Testadapter. Diese HA-Tests müssen unter Linux/Python 3.14 mit HA 2026.10.2 tatsächlich ausgeführt werden.

Die lokale HACS-Prüfung betrifft Metadaten, Verzeichnis-/Paketlayout und Versionsregeln des Repository-Prüfers. **Die offizielle HACS-Action, hassfest und Gitleaks wurden für den ungepushten Stand nicht ausgeführt.** Sie bleiben zusammen mit der echten HA-Laufzeitabnahme verpflichtende CI-Gates. Der bestehende Workflow wurde lediglich um den zukünftigen Branch `test/v1.4.5` ergänzt, nicht ausgeführt. Sein HA-Job verlangt weiterhin null übersprungene Tests.

## Bekannte Grenzen und nächste Freigabe

- Neue Standardwoche ausdrücklich konfigurieren; keine automatische Migration der alten Regeln. Bestehende Einkaufs-/Rezeptdaten, Tokens, Freigaben und offene Journale bleiben erhalten.
- Kochidentitäten benötigen tatsächliche Yuvomi-Mitglieder und lesenden `family`-Scope. Kein ID-Raten und keine automatische Tokenänderung.
- Freitext-Ernährungswünsche bleiben Modellaufgabe, keine Allergensicherheitsgarantie. Explizite Rezept-ID-Abneigungen und eindeutige Rezeptmetadaten werden deterministisch geprüft.
- Bestehende RC3-Aufwärmeinträge werden nicht entfernt; abhängige Änderungen blockieren sicher. Fremde Änderungen im REST-Konkurrenzfenster und Teilantworten bleiben Journal-/Reconciliation-Fälle.
- Der GUI-Skalierungsregler bleibt 1; tatsächliche Zutaten werden einmal korrekt skaliert gespeichert. Manuelle Rezept-Neuauswahl kann Notizen/Annotationen/Zutaten ersetzen.
- Vollständige Planung weiterhin in bewusst separater Conversation, Kontextgültigkeit fünf Minuten. Keine automatische Isolation und keine Routeränderung.

Empfohlen: lokalen Diff und Vertrag prüfen, danach separat einen CI-Testbranch/Push freigeben. Erst nach grüner echter HA-/HACS-/hassfest-Abnahme in einer isolierten Testinstallation Kochpersonen, Kalender, fünf Kochtage, Mitnahmezuordnungen, Mengen, Titel und Tagesänderungen prüfen. Produktionsinstallation und Veröffentlichung benötigen weiterhin ausdrückliche Freigabe.
