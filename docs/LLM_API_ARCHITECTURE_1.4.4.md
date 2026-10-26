# Separate Yuvomi-LLM-API – Architekturprüfung für HA 2026.10.2

> Umsetzung vom 26.10.2026: Lokale Implementierung ausdrücklich freigegeben; eigene LLM-API jetzt enthalten. Ältere „nur Analyse“-/„später freigeben“-Passagen unten dokumentieren den vorausgehenden Entscheidungsstand. Verbindlicher tatsächlicher Umfang, Grenzen, Konfiguration und neue Referenzmessungen: [SETUP_1.4.4.md](SETUP_1.4.4.md), [TEST_REPORT_1.4.4.md](TEST_REPORT_1.4.4.md). Kein Push/Tag/Release oder produktiver Eingriff.


**Nur Untersuchung, Stand 25.10.2026.** Keine API registriert, keine Agenten-/Routeroptionen verändert. Eine eigene API wird in 1.4.4 ohne weitere ausdrückliche Freigabe **nicht** implementiert. Bestehender lokaler Integrationsstand: 1.4.3.

## 1. Quellen und Aussagegrenzen

Maßgeblich ist der Originalquellcode **home-assistant/core, Tag 2026.10.2**, nicht eine Annahme aus aktuellen Entwicklerdokumenten. Quellenhashes stehen in [MENU_API_EVIDENCE_1.4.4.json](MENU_API_EVIDENCE_1.4.4.json).

- [helpers/llm.py](https://github.com/home-assistant/core/blob/2026.10.2/homeassistant/helpers/llm.py): Registry, `API`, `APIInstance`, `async_get_api`, `MergedAPI`, `NamespacedTool`.
- [components/llm/__init__.py](https://github.com/home-assistant/core/blob/2026.10.2/homeassistant/components/llm/__init__.py): Plattformabfrage und Assist-Zusammenstellung.
- [conversation/chat_log.py](https://github.com/home-assistant/core/blob/2026.10.2/homeassistant/components/conversation/chat_log.py): API-Auswahl und Prompt-/Werkzeugübergabe.
- [OpenAI-Konfiguration](https://github.com/home-assistant/core/blob/2026.10.2/homeassistant/components/openai_conversation/config_flow.py), [Ollama-Konfiguration](https://github.com/home-assistant/core/blob/2026.10.2/homeassistant/components/ollama/config_flow.py) und [Gemini-Konfiguration](https://github.com/home-assistant/core/blob/2026.10.2/homeassistant/components/google_generative_ai_conversation/config_flow.py): mehrfache API-Auswahl.

Zusätzlich lokal gelesen: `ha-assist-router/reference/prompt_compatibility/local/{config_flow.py,conversation.py,manifest.json}` (Local OpenAI LLM 1.12.1), `ha-assist-router/custom_components/assist_router/conversation.py` und aktuelle `ha-yuvomi-mcp/custom_components/yuvomi_mcp/llm.py`. Das sind lokale Prüfstände, **kein Nachweis der tatsächlich produktiv installierten Agent-/Routerversion oder deren Optionswerte**. Keine produktive Instanz wurde kontaktiert. Eine spätere Live-Abnahme erfolgt bewusst separat.

## 2. Was HA tatsächlich unterstützt

**Mehrere APIs sind möglich.** `llm.async_get_api(hass, api_id, llm_context)` akzeptiert einen String oder eine Liste. Bei genau einer API wird deren Instanz verwendet, bei mehreren eine `MergedAPI`. Die geprüften HA-Core-Agenten bieten `CONF_LLM_HASS_API` als Mehrfachauswahl an. Das ist ein unterstützter Core-Weg; ein eigener Agent kann dennoch Einschränkungen haben.

**Die lokale Local-OpenAI-Referenz unterstützt diesen Weg ebenfalls:** Konfigurationsauswahl `multiple=True`, Liste registrierter APIs über `llm.async_get_apis`, Weitergabe der ausgewählten IDs an `chat_log.async_provide_llm_data`. Nicht mehr vorhandene IDs werden dort herausgefiltert. Bei einer entladenen optionalen API können deshalb ihre Werkzeuge fehlen, ohne dass automatisch zu Assist zurückgeschaltet wird. Bei fehlender API nie einen Schreibauftrag als erledigt melden. Verhalten nach Registrierung/Reload und tatsächlichen produktiven Versionsstand vor Migration testen.

**Kombination ist keine unsichtbare Vereinigung:** `MergedAPI` fügt die Prompts zusammen und versieht jedes Tool mit einem weiteren Namensraum aus dem slugifizierten **API-Anzeigenamen**. `NamespacedTool` delegiert den Aufruf an das ursprüngliche Werkzeug; dessen Backendname/Argumente bleiben erhalten, das gegenüber dem Modell sichtbare Tool heißt jedoch anders. Ein unveränderter eigener Name `yuvomi_mcp__add_shopping_item` wird beispielsweise um den API-Namensraum ergänzt. Namenslängen, stabile und eindeutige API-Namen sowie hart codierte Promptverweise testen. API-IDs müssen eindeutig sein; auch Anzeigenamen/Namensräume müssen praktisch kollisionsfrei gewählt werden. Keine automatische Deduplizierung identischer Werkzeuge aus zwei APIs annehmen.

Smart-Home-Werkzeuge und Yuvomi können damit parallel verfügbar sein. Ob und welche Smart-Home-Werkzeuge tatsächlich erscheinen, hängt von den übrigen Integrationen und Entitätsfreigaben ab. Eine eigene Familien-API soll keine Smart-Home-Werkzeuge oder neue Entity-Freigaben hinzufügen. Fehlende Entity-Freigaben bedeuten nicht automatisch einen vollständig leeren Assist-Prompt.

## 3. Gegenüberstellung

| Variante | Kontext und Verhalten | Kompatibilität / Aufwand |
| --- | --- | --- |
| Bisher nur assist | Bestehende aktivierte Yuvomi-Werkzeuge plus Beiträge weiterer Assist-Plattformen; gemeinsamer Yuvomi-Prompt | Keine Migration, heutiger Router-/Agentenweg bleibt erhalten |
| Nur zusätzliche Yuvomi-API, im Agenten nicht ausgewählt | Kein Beitrag dieser API zum betreffenden Modellaufruf | Registrierung allein spart keine Tokens und ändert keinen bestehenden Agenten |
| Eigene Yuvomi-API allein ausgewählt | Nur deren freigegebene Werkzeuge/kurzer Prompt; keine automatisch beigefügten Assist-Werkzeuge | Kann Grundlast verringern, wenn tatsächlich unnötige Assist-Beiträge entfallen; identische Yuvomi-Definitionen kosten weiterhin Kontext |
| assist plus Yuvomi-API, bisheriger Yuvomi-Assist-Beitrag bleibt | Yuvomi zweimal erreichbar, zusätzliche Prompts und Namensräume | Nicht empfehlen: Doppeldefinitionen, mehr Kontext, schlechtere Werkzeugwahl |
| assist plus Yuvomi-API, Yuvomi aus Assist bewusst entfernt | Smart Home und Familie parallel, zusätzliche Namespaces/Merge-Prompt | Unterstützbar, aber explizite Migration aller betroffenen Agenten nötig; keine garantierte Tokenersparnis |
| Separater Planungsagent mit eigener Conversation | Vollständige Planungsdaten können außerhalb gewöhnlicher Gespräche bleiben | Eigene API allein erzeugt diese Isolation nicht; Agent-/Routerweg muss separat unterstützt und getestet sein |

Im aktuellen Betrieb werden Smart-Home-Befehle direkt über Alexa bearbeitet und keine HA-Entitäten für Assist exponiert. Eine allein ausgewählte Familien-API könnte verbleibende unnötige Beiträge anderer Assist-Plattformen einsparen. Deren tatsächlicher Anteil an **6604 vollständigen Prompt-Tokens** ist aber unbekannt. Ohne echten A/B-Vergleich keinen festen Gewinn behaupten.

## 4. Mögliche spätere Registrierung

Eine schmale `llm.API`-Unterklasse liefert über `async_get_api_instance(llm_context)` eine `APIInstance` mit denselben freigegebenen `YuvomiTool`-Adaptern, kurzem Prompt und passendem Schema-Serializer. Registry-Anbindung über `llm.async_register_api`; deren Rückruffunktion über `entry.async_on_unload` abmelden. Keine Überschreibung der Assist-API, kein Patch am HA-Core und kein eigener MCP-Server nötig.

Vorgeschlagene stabile ID je Config Entry: `yuvomi_family_<entry_id>`; eindeutiger stabiler Anzeigename, besonders bei mehreren Entries. So liefert eine API nur die Runtime ihres Entries. Bestehende Toolnamen intern erhalten, keine zweite Purchasing-/Recipe-/Journalinstanz. Parameterprüfung, Rechte, bestätigungspflichtige unbekannte Tools und Idempotenz bleiben im gemeinsamen Runtime-Aufruf. Registrierung oder API-Auswahl autorisieren keine zusätzlichen Werkzeuge.

Die Integration muss bewusst zwischen Exposition über Assist und Exposition über die eigene API unterscheiden können. Dafür später einen **expliziten Expositionsmodus** je Entry vorsehen: Default unverändert `assist`, optional nach Benutzerentscheidung `dedicated`. Die bestehende Allowlist bleibt identisch; der Modus verschiebt nur den Träger der bereits freigegebenen Werkzeuge. Keine automatische Modusänderung, auch nicht bei Registrierung oder Entdeckung einer API. Gleichzeitige doppelte Exposition nicht als empfohlene Migrationslösung freigeben. Wenn mehrere Agenten dasselbe Entry verwenden, müssen vor Umschaltung alle ihre bewussten API-Auswahlen erhalten; andernfalls verlieren Legacy-Agenten den Werkzeugzugriff.

Die eigene API darf nicht pauschal alle LLM-Plattformen unter assist einsammeln: sie liefert ausschließlich die für dieses Yuvomi-Entry freigegebenen Werkzeuge. Neue Planungswerkzeuge bleiben aus, bis in den Integrationsoptionen bewusst gewählt. Keine zusätzlichen generischen REST-Schreibrechte oder Kalenderfreigaben.

## 5. Auswirkungen auf Assist Router und Gesprächskontext

Der geprüfte Router wählt einen Conversation-Agenten und ruft `conversation.async_converse` mit dessen `agent_id`, bestehender `conversation_id`, HA-Kontext und komponiertem Zusatzprompt auf. Er wählt **keine LLM-API je Nachricht**. Bleibt derselbe Agent mit derselben API-Auswahl bestehen, ist dafür keine Routeränderung nötig. Eine andere API-Auswahl ist eine Option am Zielagenten, kein neues Routerprotokoll.

Der Router behält ausdrücklich dieselbe Conversation-ID bei und blockiert einen unerwarteten Wechsel durch den Zielagenten. Deshalb darf die MCP-Integration keine neue Conversation-ID zurückgeben oder heimlich fremde Historien löschen. Eine kurzlebige isolierte Planungsunterhaltung benötigt einen gesondert geprüften Host-/Routerablauf, etwa bewusst gestartete eigene Planungssitzung. Einfach einen zweiten Agenten auszuwählen oder eine API umzubenennen trennt den ChatLog bei derselben Conversation-ID nicht zuverlässig.

Ein zusätzlicher Familienagent kann später organisatorisch sinnvoll sein. Semantisches Routing nach „Menüplanung“ oder API-Umschaltung pro Auftrag sind im geprüften Routerweg jedoch nicht nachgewiesen. Kein automatischer Wechsel nach bereits begonnener Schreibaktion und kein Fallback auf einen zweiten Agenten bei Timeout. Die bestehende Router-Sicherheitslogik bleibt unangetastet.

## 6. Empfehlung, Migration und Testbedarf

**Für 1.4.4 die bestehende Assist-Plattform beibehalten.** Zuerst die geprüfte Beschreibungsoptimierung und verzögertes Laden der Planungsdaten umsetzen, nach eigener Implementierungsfreigabe. Eine eigene API ist hauptsächlich eine saubere organisatorische und manuelle Auswahlgrenze; sie ist keine Voraussetzung für Menüplanung und kein garantierter Token-Sparmechanismus. Ihre Umsetzung bleibt außerhalb des aktuellen Freigabeumfangs.

Falls später gewünscht: (1) Konfiguration/Storage sichern und verwendete Agenten erfassen; (2) API-ID-/Reload-/Auswahlverhalten in Test-HA prüfen; (3) gezielt dedizierten Expositionsmodus und Agentenauswahl konfigurieren, Toolallowlist unverändert lassen; (4) Assist-only, eigene API-only und bewusste Kombination testen; (5) echten vollständigen Prompt messen und Werkzeugaufrufe prüfen; (6) bei Problemen explizit auf assist und bisherigen Agentenstand zurückstellen. Keine automatische Migration von Config Entries, Tokens, Listen, Journal oder Agenten.

Regressionen: neue/alte Entries, kein aktives Tool, mehrere Entries/API-Namensräume, identische oder lange Namen, wiederholter Reload/Unload, API vor/nach Agentenstart verfügbar, fehlende API, rückgehaltenes Tool nach Rechteentzug, unbekannte Toolbestätigung, unveränderte Einkauf-/Rezept-/Aufgaben-/Terminaufrufe, doppelte Exposition verhindert sowie unveränderte Retry-/Journalbarrieren. Tokenvergleich nur mit identischer Systemprompt-/Modell-/Allowlistkonfiguration; eine API-Variantenmessung separat kennzeichnen. Kein Test dieser Untersuchung hat eine produktive Registrierung vorgenommen.
