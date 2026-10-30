# Geprüfter Yuvomi-Vertrag für Menüplanung 1.4.5

Statische Prüfung am unveränderten offiziellen Quellstand **2.79.0**, Commit `a6812d433fc25a0f8bf1389542e68111f9169a82`. Die relevanten lokalen Dateien wurden gegen die Git-Objekte dieses Commits verglichen, Hashes/URLs stehen in [yuvomi_2.79.0_planning_evidence.json](yuvomi_2.79.0_planning_evidence.json). Kein Zugriff auf produktive Server oder Daten. Lokale Shopping-Patches des separaten Serverprojekts wurden nicht als Vertragsgrundlage verwendet oder verändert.

| Bedarf | Tatsächlicher Vertrag | Umsetzung |
|---|---|---|
| Vollständiger Menübestand | `GET /api/v1/meals?week=YYYY-MM-DD`, `data`, `weekStart`, `weekEnd`; Wochenstart haushaltsabhängig, mehrere Einträge pro Datum/Typ möglich | Bounded Wochenlesen, IDs prüfen, Zielslots eindeutig validieren; GET kann Wiederholungen materialisieren |
| Gemeinsam anlegen | `POST /api/v1/meals/apply-plan`, `assignments`, `skip_occupied: true` | Journal vor POST; keine belegten Slots überschreiben |
| Gezielt ersetzen | Gleiche Route mit `replace_existing: true`, nicht mit skip kombinierbar | Genau ein ausdrücklich erlaubter Datum-/Mahlzeitslot; ursprüngliche ID wird serverseitig ersetzt, kein Serienauftrag |
| Mahlzeit und Rezept | Assignment enthält unabhängig `title` und `recipe_id`; `createMealRecord` speichert beides direkt | Exakter Originalrezept-Link plus eigener Mahlzeittitel; JSON-Feldreihenfolge beeinflusst dies nicht |
| Portionen/Faktor | Kein natives Portions-/Skalierungsfeld der Route | Versionierte strukturierte Mahlzeitnotizen; Zutaten bereits mit Gesamtportionen/Basisportionen skaliert |
| GUI-Skalierung | `public/pages/meals.js`: Eingabe `modal-recipe-scale` startet mit 1; Rezeptauswahl/Regler rechnet clientseitig Zutaten und setzt Titel/Notizen | Nicht als persistierten Faktor interpretieren. Keine zweite Skalierung. Manuelle Rezept-Neuauswahl kann HA-Annotation/Zutaten ersetzen |
| Reale Kochperson | Assignment `cook_user_id`: positive existierende Haushaltsmitglied-ID oder null; Server prüft Mitgliedschaft | Profil explizit mit realer ID verbinden, bei Kontext und vor POST Verzeichnis prüfen; keine geratenen IDs |
| Mitglieder lesen | `GET /api/v1/family/members`, `data[]` mit `id`, `display_name` und weiteren personenbezogenen Feldern | Nur ID/Name weiterverwenden; übrige Felder verwerfen. Enges zusätzliches Recht `family:read`, kein administratives Schreibrecht |
| Berechtigungen | Mahlzeiten/Rezepte: meals read/write; Mitglieder: family read | Bestehenden Token verwenden; keine automatische Scoperweiterung oder Werkzeugfreigabe |
| Idempotenz | Globale POST-Middleware mit `Idempotency-Key` | Vorhandenen stabilen Ausführungsschlüssel behalten; Journal und Reconciliation nicht ersetzen |

Die Route verarbeitet die tatsächlichen Neuanlagen in einer Datenbanktransaktion. `skip_occupied` kann aber eine Teilmenge überspringen, wenn ein anderer Client inzwischen Slots belegt hat. Eine solche Antwort ist kein bestätigter vollständiger Plan. HA markiert den Ausgang unklar, erhält die Schreibsperre und wiederholt nicht automatisch. Es gibt keine serverseitige atomare If-Match-/CAS-Vorbedingung gegen fremde Änderungen; auch gezieltes Ersetzen hat deshalb ein verbleibendes Konkurrenzfenster.

Massgebliche Quellen: [apply-plan und createMealRecord](https://github.com/ulsklyc/yuvomi/blob/a6812d433fc25a0f8bf1389542e68111f9169a82/server/routes/meals.js), [Kochidentitäten](https://github.com/ulsklyc/yuvomi/blob/a6812d433fc25a0f8bf1389542e68111f9169a82/server/services/meal-cook.js), [Mitgliederliste](https://github.com/ulsklyc/yuvomi/blob/a6812d433fc25a0f8bf1389542e68111f9169a82/server/routes/family.js), [GUI-Regler und Rezeptauswahl](https://github.com/ulsklyc/yuvomi/blob/a6812d433fc25a0f8bf1389542e68111f9169a82/public/pages/meals.js).
