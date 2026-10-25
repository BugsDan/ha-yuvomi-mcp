# GitHub und HACS: BugsDan/ha-yuvomi-mcp

## Stand und Architektur

Das öffentliche Repository besteht. 1.4.2 ist die erste öffentliche Baseline; ein Tag und Release werden erst nach gesonderter Freigabe erstellt. Die MIT-Lizenz bleibt erhalten. Keine externe Grafik oder Serverquellcodes werden mitveröffentlicht.

Die HACS-Struktur ist custom_components/yuvomi_mcp. hacs.json liegt im Repository-Stamm, verlangt mindestens HA 2026.10.2 und blendet den Default-Branch für Installationen aus. zip_release=false: HACS liest ausschließlich die Integration aus dem gewählten Release-Tag. Die bisherigen ZIP-Dateien haben ein anderes Ziel, nämlich die manuelle Installation, und werden nicht als flaches HACS-Asset ausgegeben. Es wird kein persistent_directory benötigt: die erhaltenen Zustände liegen in HA .storage außerhalb des Integrationscodes.

## Quellbaum vor einem Commit prüfen

Das öffentliche Repository und main bestehen bereits. Nur freigegebene Quelldateien übertragen, keine privaten Entwicklungsverzeichnisse oder alten ZIPs. Vor jedem Commit `git diff --cached` prüfen und `python tools/check_repository.py --staged` ausführen; der Check liest tatsächliche Index-Blobs. Kein eigener PAT oder produktiver HA-/Yuvomi-Token für CI nötig. Secret-Scanning und Push-Protection sind ergänzende, vom Betreiber zu prüfende Repository-Einstellungen.

## Erstes Release v1.4.2

1. Actions unter main prüfen: Python-3.12-Tests, Linux/Python-3.14-Tests mit HA 2026.10.2, lokale Publikationsprüfung, HACS Action und hassfest. Rote Checks beheben; keine Validierung als bestanden behaupten, solange GitHub sie nicht ausgeführt hat.
2. Erst danach lokal Versionen prüfen: manifest.version = const.VERSION = project.version = 1.4.2; docs/RELEASE_1.4.2.md vorhanden. `python tools/check_repository.py --tag v1.4.2` muss bestehen.
3. Nach bewusster Freigabe einen annotierten Tag v1.4.2 auf den geprüften Commit setzen und pushen. Das macht die Tag-Quelle öffentlich, ist also bereits eine Veröffentlichungshandlung. Nicht während dieser Vorbereitung ausführen.
4. Der Tag-Workflow ruft dieselben Prüfungen erneut auf, kontrolliert Tag/Version und baut manuelles Installations-ZIP, Source-ZIP und versionierte Prüfsummen. Nur bei Erfolg erzeugt er mit dem automatisch bereitgestellten kurzlebigen GitHub-Token einen **Entwurf**, niemals automatisch ein veröffentlichtes Release.
5. Draft und Assets prüfen, HACS-Tauglichkeit des getaggten Quellbaums kontrollieren, dann ausdrücklich im GitHub-UI veröffentlichen. Erst dieses veröffentlichte Release v1.4.2 ist der vorgesehene HACS-Installations-/Updatepunkt. Tags und veröffentlichte Assets danach nicht verschieben oder still ersetzen.

Das Repository muss für den eigenen HACS-Einsatz nicht zuerst in den HACS-Standardkatalog aufgenommen werden. Die Nutzung als benutzerdefiniertes Repository ist vorgesehen. Eine spätere Aufnahme in den Standardkatalog ist ein separater Antrag. Ein originales lokales brand/icon.png ist vorbereitet; HACS prüft diesen Pfad vor einem Fallback auf das zentrale Brands-Repository. Keine fremde Brand-PR wurde erstellt.

## Manuelle Installation ohne Konfigurationsverlust übernehmen

1. Vollständiges HA-Backup einschließlich Config Entries, Konfiguration, Integrationsordner und .storage erstellen; Yuvomi separat wie üblich sichern. Offene/unklare Journale nicht löschen. Keine Einkaufsaktion während des Codewechsels starten.
2. Existierenden Config Entry **yuvomi_mcp behalten**. Nicht entfernen, nicht neu anlegen, Domain nicht umbenennen. Tokens und Werkzeugfreigaben gehören zu diesem Entry, dessen ID auch den Journalspeicher bindet.
3. In HACS das veröffentlichte Repository als Typ Integration hinzufügen, Yuvomi MCP öffnen und Version 1.4.2 erneut herunterladen. HACS scannt vorhandenen manuell installierten Code nicht zuverlässig als eigene Installation; das erneute Herunterladen stellt die Verwaltung her.
4. Die HACS-Installation ersetzt Code unter custom_components/yuvomi_mcp. Sie soll keine HA-.storage-Dateien und keine Yuvomi-Artikel verändern. Falls HACS den existierenden Ordner ablehnt: Vorgang stoppen und die Meldung prüfen; nicht Config Entry oder Journale löschen und nicht auf Verdacht Daten bereinigen.
5. HA neu starten. Vorhandene Integration, dieselbe Entry-ID, URL/Token, ausgewählte Werkzeuge und Journalzustände prüfen. Einen neuen Assist-Kontext für die aktuellen Werkzeugbeschreibungen beginnen. Shopping-Tests auf einer bewusst gewählten Testliste durchführen (docs/ABNAHME.md); Aufgaben/Kalender ebenfalls prüfen.
6. HACS muss Yuvomi MCP anschließend als heruntergeladen in Version 1.4.2 führen. Es gibt keine zusätzliche Migration von 1.4.2 auf dieselbe veröffentlichte Version. Frühere manuelle Entwicklungsstände bleiben über den vorhandenen [Speicheradapter](STORAGE_COMPATIBILITY.md) unterstützt.

Keine zweite Integration und kein zweites Konto werden dafür angelegt. Kein YAML-Umbau. Ein Backup des bisherigen Codes sollte außerhalb custom_components liegen, damit HA nicht eine zweite Kopie entdeckt.

## Spätere Updates, z.B. 1.4.3

- Funktionsänderung und passende Regressionen entwickeln; Versionsfelder gezielt gemeinsam auf 1.4.3 setzen. Keine globale Textersetzung, die Test-/Bibliotheksversionen verändert.
- docs/RELEASE_1.4.3.md und CHANGELOG ergänzen, vorhandene Zustände kompatibel halten, Tests/Publikationscheck und CI abwarten.
- Geprüften Commit nach main übertragen, anschließend Tag v1.4.3 setzen/pushen. Draft prüfen und veröffentlichen.
- In HACS das Update herunterladen und HA neu starten. Vorher Backup, nachher kurze Funktionsprüfung. Config Entries und Freigaben nicht neu anlegen. Neue Werkzeuge bleiben ausdrücklich freizugeben.
- Ein reiner Tag ohne veröffentlichtes Release oder ein unvollständiger Draft erscheint nicht als der gewünschte stabile HACS-Updatepfad.

## Nachweise und Grenzen

Prüfungen laufen ohne produktive HA-/Yuvomi-Verbindungen. Für jeden Release-Commit müssen Unit-Tests, echter HA-Testjob, HACS und hassfest in [GitHub Actions](https://github.com/BugsDan/ha-yuvomi-mcp/actions/workflows/tests.yml) erfolgreich sein. HACS-Übernahme und tatsächliche Installation bleiben eine separate Abnahme durch den Betreiber.

Offizielle Quellen (geprüft bei dieser Vorbereitung):

- HACS-Struktur/Manifest: https://www.hacs.dev/docs/publish/integration/
- hacs.json/Release-Tags: https://www.hacs.dev/docs/publish/start/
- HACS Action: https://www.hacs.dev/docs/publish/action/
- Benutzerdefinierte Repositories: https://www.hacs.dev/docs/faq/custom_repositories/
- Bereits manuell installierte Elemente: https://www.hacs.dev/docs/faq/existing_elements/
- Lokaler Brand-Validator: https://github.com/hacs/integration/blob/main/custom_components/hacs/validate/brands.py
