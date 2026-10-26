# Yuvomi MCP 1.4.4-rc2

**Pre-Release / Release Candidate, keine stabile Version 1.4.4.**

Gegenüber v1.4.4-rc1 ausschließlich Zeit-/Promptoptimierung, Regressionstests,
Dokumentation und erforderliche CI-/RC-Paketierungsanpassungen:

- Yuvomi-eigenen hochpräzisen Zeitstempel aus Assist- und Dedicated-Prompt entfernt.
  Home Assistants aktuelle Zeit-/Datumszeile bleibt erhalten, falls kein Zeitwerkzeug angeboten wird.
- Statischer Kern mit Ergebniswahrheit und Sicherheitsleitlinien; Einkaufs-, Rezept- und
  Menühinweise abhängig von den bereits freigegebenen Werkzeugen.
- Keine neuen Werkzeuge oder automatischen Freigaben. Bestehende Namen, Parameterschemas,
  API-Modi, Berechtigungen, Bestätigungen, Konfigurationen, Journal, Idempotenz,
  Backend-Validierungen und Menüplanungslogik bleiben unverändert.
- Der Release-Workflow akzeptiert zusätzlich streng geprüfte `-rcN`-Suffixe und erstellt
  weiterhin nur einen Draft; bei RC-Tags ausdrücklich als Pre-Release. Alle CI-Prüfungen bleiben aktiv.

Der statische Yuvomi-Regelblock bei Standardwerkzeugen sinkt von 4255 auf 2305 UTF-8-Bytes
(45,83 %). Das ist **keine gemessene Token- oder KV-Cache-Ersparnis**.
Die vom Betreiber gemeldeten **3864 vollständigen Prompt-Tokens** für „hallo“ mit
Familienprompt v2.4 gehören zu **RC1**, nicht zu RC2. RC2 wird erst nach Installation durch
den Betreiber mit identischer Konfiguration gemessen.

## Installation und Abnahme

- Home Assistant mindestens **2026.10.2**; HA-Zeitzone **Europe/Zurich** prüfen.
- Vor Installation ein vollständiges HA-Backup erstellen. In HACS Pre-Release-/Beta-Versionen
  für dieses Repository auswählen und `v1.4.4-rc2` installieren.
- `zip_release: false`: HACS installiert den Tag-Quellbaum. Manifest und Assets tragen weiterhin
  die Basisversion **1.4.4**; Git-Tag und GitHub-Kennzeichnung unterscheiden RC1 und RC2.
- ZIP für manuelle Installation, separates Source-ZIP und SHA256SUMS werden mit dem vorhandenen
  Paketbauer erzeugt. Vor manueller Installation Prüfsummen vergleichen.
- Keine produktive Installation wurde durch diesen Auftrag vorgenommen. `main` bleibt unverändert.

## Verbleibende Grenzen

Home Assistants Zeit-Fallback ist weiterhin dynamisch. Wechselnde Werkzeuglisten, Familien-/Agentenprompt,
Chat-Template, History, Slot-Zuordnung und Cache-Einstellungen können die KV-Wiederverwendung beeinflussen.
Neue Conversations garantieren weder einen leeren noch einen passenden warmen Server-Cache.

Empfohlen: je RC Modell einmal neu laden, „hallo“ in neuer Conversation als Kaltmessung,
danach mindestens fünf neue Conversations ohne erneuten Reload als Warmmessung.
Prompt-Tokens, neu evaluierte Tokens und explizite KV-Cache-Tokens getrennt erfassen;
`graphs reused` ist kein KV-Cache-Nachweis. Gleiche Freigaben, APIs, Familienprompt v2.4 und Modelleinstellungen verwenden.

[Technische Analyse und vollständige Messanleitung](TIME_CONTEXT_AND_CACHE.md)
beschreibt Herkunft, Alternativen und reproduzierbaren strukturellen Vergleich.
Die GitHub-Actions-Läufe auf dem Release-Commit enthalten Unit-/Regressionstests,
echte HA-2026.10.2-Tests mit Python 3.14, Ruff, Formatprüfung, Repository-/Paketprüfung,
HACS, hassfest und Secret-Scan. Die Veröffentlichung erfolgt erst nach erfolgreicher CI.
