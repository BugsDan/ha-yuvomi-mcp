# CI-Abnahme 1.4.4

Stand: 26.10.2026. Repository: BugsDan/ha-yuvomi-mcp, ausschliesslich Branch [test/v1.4.4](https://github.com/BugsDan/ha-yuvomi-mcp/tree/test/v1.4.4).

## Ergebnis des vollständigen Code-Prüfstands

Geprüfter Code-Commit: [3645d2d](https://github.com/BugsDan/ha-yuvomi-mcp/commit/3645d2ddaa7fcb2e37c25ee110596d74cbd6072f).

[Alle fünf Jobs erfolgreich](https://github.com/BugsDan/ha-yuvomi-mcp/actions/runs/40303828438):

| Job | Bestanden | Fehlgeschlagen | Übersprungen | Ergebnis |
| --- | ---: | ---: | ---: | --- |
| Unit-/Regression, Python 3.12 | 502 | 0 | 2 | Erfolgreich; zwei HA-Testmodule ohne installiertes HA erwartungsgemäss übersprungen |
| Echtes HA 2026.10.2 / Python 3.14.8 | 526 | 0 | 0 | Erfolgreich; Skip-Sperre im Workflow bestanden |
| HACS | – | – | – | Erfolgreich |
| hassfest | – | – | – | Erfolgreich |
| Gitleaks Secret-Scan | – | – | – | Erfolgreich, keine Leaks |

Die beiden Testsuiten überlappen; ihre Zahlen sind keine addierbare Zahl einzigartiger Tests. Im HA-Job laufen auch sämtliche Unit-/Regressionstests. Auswertbare JUnit-Berichte werden pro Lauf als Artefakte gespeichert. Ruff, Format, Quellenvertragprüfung, Repository-/Indexscan und reproduzierbarer Paketbau gehören zum erfolgreichen Workflow.

Der Dokumentations-Endstand wird danach nochmals durch denselben Workflow geprüft. Aktueller Nachweis und gegebenenfalls zusätzlicher manueller Vollhistorienlauf: [Testbranch-Läufe](https://github.com/BugsDan/ha-yuvomi-mcp/actions?query=branch%3Atest%2Fv1.4.4). Ein push-getriggerter Gitleaks-Lauf untersucht den jeweiligen Push; ein workflow_dispatch-Lauf untersucht mit vollständig ausgecheckter Historie den vollständigen Git-Verlauf. Konkrete finale Lauf-/Commit-Links werden im Abschlussbericht genannt.

## Echte HA-Laufzeitprüfung

Die CI installiert homeassistant==2026.10.2 und startet die Tests mit echtem HomeAssistant, Event Loop, Loader, ConfigEntries/ConfigEntry, LLM-API-Registry, API-Zusammenführung, SelectSelector, Conversation-ChatLog, atomarem HA-Store, Auth-Manager sowie Geräte-/Entitäts-/Service-Registry. Diese Komponenten werden in den neuen Laufzeittests nicht durch Mocks ersetzt. Der externe MCP-Dienst wird als isolierter lokaler HTTP-Server bereitgestellt, nicht als produktive Yuvomi-Instanz.

Nachgewiesen:

- API registrieren, über Registry finden, abmelden und erneut registrieren; echte ConfigEntry-Unload-Callbacks.
- Auswählbare API-IDs im echten HA-Selector; Übergabe an ChatLog wie beim geprüften Local-OpenAI-Vertrag.
- Assist plus eigene API über echte MergedAPI, zusätzliche Namensräume, Werkzeugaufruf über echten HTTP-Transport; dedicated allein ohne Assist-Beiträge.
- Reversibilität assist/dedicated, kein doppelter Yuvomi-Träger, alte Toolinstanzen gesperrt, Freigaben bei jedem Aufruf erneut geprüft.
- Alte Config-Entry-Optionen ohne exposure_mode unverändert, keine automatische Erweiterung der Allowlist.
- Atomare echte HA-Store-Speicherung und Wiederherstellung von Planungskonfiguration und offenem meals-Beleg.
- Echte Benutzerberechtigungen: nicht berechtigter Benutzer und fehlender Kontext abgelehnt, berechtigter Benutzer erhält nur den ausdrücklich ausgewählten Kalender; Kontext wird an den echten Service-Aufruf weitergereicht.

Bestehende HA-Klassen-/Optionsflow-Tests bleiben zusätzlich erhalten. Menüregeln, Wiederholungen, Portionen, Reaktivierung/Einkauf, Journal, Idempotenz, Speicherfehler, parallele Aufrufe, Timeouts und Wiederherstellung sind in der vollständigen Regression enthalten. Keine Tests deaktiviert, keine Assertions zur Umgehung eines Fehlers entfernt.

## Korrekturen während der CI-Abnahme

1. Tests-Workflow um den erlaubten Testbranch, JUnit-Artefakte, explizite HA-Skip-Sperre, Paketbau und Gitleaks ergänzt. Release-Workflow unverändert.
2. Für echte Conversation-Tests fehlende optionale HA-Abhängigkeiten installiert. Versionen werden aus dem Manifest der tatsächlich installierten HA-Version 2026.10.2 gelesen, statt andere Versionen zu raten.
3. Fehlende echte Loader-Initialisierung ergänzt; zwei ältere Registry-/Setup-Fixtures von nicht hashbarem SimpleNamespace auf echte HomeAssistant-Instanzen umgestellt.
4. Zusätzlichen Kalender-Berechtigungstest beibehalten und dessen echten Geräte-/Entitätsregistry-Bootstrap vervollständigt.

Die Korrekturen betreffen CI/Testaufbau. Fachlicher Produktivcode, Sicherheitsgarantien und Version 1.4.4 wurden dafür nicht geändert. Keine produktiven Zugriffe.

## Laufhistorie

| Lauf | Befund |
| --- | --- |
| [40302285888](https://github.com/BugsDan/ha-yuvomi-mcp/actions/runs/40302285888) | HA-Collection durch fehlendes hassil blockiert; übrige Jobs erfolgreich |
| [40302658951](https://github.com/BugsDan/ha-yuvomi-mcp/actions/runs/40302658951) | HA: 522 bestanden, 3 Fixture-Fehler, 0 Skips; übrige Jobs erfolgreich |
| [40303051460](https://github.com/BugsDan/ha-yuvomi-mcp/actions/runs/40303051460) | Sämtliche Jobs erfolgreich; HA: 525/0/0 |
| [40303435695](https://github.com/BugsDan/ha-yuvomi-mcp/actions/runs/40303435695) | Zusätzlicher Auth-Test brauchte Registry-Bootstrap; HA: 525 bestanden, 1 Fixture-Fehler; übrige Jobs erfolgreich |
| [40303828438](https://github.com/BugsDan/ha-yuvomi-mcp/actions/runs/40303828438) | Sämtliche Jobs erfolgreich; HA: 526/0/0 inklusive echtem Berechtigungstest |

## Grenzen und manuelle Abnahme

- Gemma-Werkzeugwahl, echte LM-Studio-Prompt-Tokens A/B/C und tatsächliche Auswahl im installierten Local-OpenAI-Agenten bleiben manuelle Tests. Die CI ruft kein produktives Modell auf.
- Ganze Wochenplanung braucht weiterhin eine bewusst separate Conversation. Keine automatische Historienisolation, kein virtueller Schalter und kein Hintergrundplanungsdienst.
- Gezielte Tagesänderungen und GUI-Darstellung/Transferverhalten der Aufwärmeinträge vor Produktivfreigabe in einer Testinstallation prüfen. Das ausdrücklich akzeptierte Konkurrenzfenster gegenüber anderen Clients bleibt.
- Keine getrennte Einkaufssynchronisation exponiert: Pantry-/Produkt-/Packungsvertrag und dauerhafte Beitrags-/Differenzbelege bleiben offen. Planung bucht keinen Einkauf.
- HA-eigene HTTP-DeprecationWarning und Hinweise zu älteren Action-Node-Zielversionen sind nicht fehlgeschlagene Tests. Pflege der vorhandenen Action-Versionen bleibt eine spätere Wartungsaufgabe; keine unsicheren Opt-outs gesetzt.
- main bleibt bei 65af2df8698df4eb15ecedd55a18ccb89b7aff04. Keine Tags, Releases, Merges oder produktiven Installationen wurden erstellt/geändert. Keine Änderung am Assist Router und keine automatische Aktivierung von Tools oder Agenten-APIs.
