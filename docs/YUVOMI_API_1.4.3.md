# Geprüfter Yuvomi-Vertrag für 1.4.3

Grundlage ist der offizielle Yuvomi-Quellstand 2.79.0, Commit a6812d433fc25a0f8bf1389542e68111f9169a82. Neun unveränderte Quelldateien wurden direkt von GitHub gelesen und bytegleich mit diesem Commit verglichen; URLs und SHA-256 stehen in yuvomi_2.79.0_evidence.json. Die produktiv installierte Instanz wurde nicht abgefragt. Lokale Änderungen eines früheren Serverpatch-Projekts wurden weder als Vertragsgrundlage benutzt noch verändert.

| Funktion | Tatsächlicher Vertrag | Verwendung in HA |
| --- | --- | --- |
| Einkaufsnotizen | POST shopping/{list_id}/items und PATCH shopping/items/{id}, Feld notes; optional, null/leer löscht, maximale Textlänge 5000, str trimmt äußeren Leerraum | Öffentliches note wird bewusst auf notes abgebildet; clear explizit |
| Rezepte lesen | GET /api/v1/recipes liefert vollständige Rezepte mit ingredients, notes, recipe_url, meal_types, Quell-/Bildindikatoren | list_recipes; get_recipe filtert vollständigen Bestand nach ID |
| Einzelrezept lesen | Kein GET /api/v1/recipes/:id im geprüften Router | Kein erfundener Endpunkt |
| Rezept anlegen | POST /api/v1/recipes; title, notes, recipe_url, meal_types, ingredients | create_recipe, keine Image-/URL-Eingabe vom Modell |
| Rezept bearbeiten | PUT /api/v1/recipes/:id; title erforderlich; fehlende Notizen/URL werden null, fehlende Zutaten leere Liste | Vorher vollständig lesen; alle erhaltenden Felder gezielt zurückschreiben |
| Bilder | Nicht mitgeliefertes image_data erhält Bild beim PUT; GET liefert nur has_own_image | Bildfeld beim Schreiben auslassen, niemals löschen |
| Mahlzeittyp | breakfast/lunch/dinner/snack; fehlender Wert bedeutet serverseitig alle | Beim Erstellen ausdrücklich lunch setzen |
| Portionen | Kein eigenes Rezept-Basisportionsfeld im geprüften Router | basisportionen ausschließlich im strukturierten Notizblock; keine Skalierung |
| Zutaten | name max 200, quantity/category max 100; Server trimmt/kürzt und prüft Kategorien nicht verbindlich | HA validiert Namen/Längen statt Kürzung; geänderte Kategorien gegen echte Kategorien prüfen |
| Rechte | /recipes gehört meals; write schließt read ein; shopping-Kategorien benötigen shopping:read | Bestehender Token, feste eng begrenzte REST-Pfade |
| Provider | Gespiegelte Rezepte sind schreibgeschützt | HA lehnt Bearbeitung ab |
| Idempotenz | Globale Middleware hinter Auth/Scope/CSRF; nur POST mit Idempotency-Key | Stabiler Schlüssel für Neuanlage; persistenter Beleg für POST und PUT |

Yuvomi hat im kuratierten MCP-Kern keine Rezeptwerkzeuge. Die generische OpenAPI-Brücke kann diese REST-Pfade erreichen, würde aber unnötig breite Werkzeugrechte erfordern. Deshalb ergänzt HA lokale, fest definierte Werkzeuge und lässt unbekannte/generische MCP-Werkzeuge unverändert bestätigungspflichtig.

Ein vollständiges PUT ersetzt Zutatenzeilen und bewahrt bestehende Pantry-Zuordnungen anhand ihrer Namen; es gibt keine atomare If-Match-Vorbedingung im geprüften Handler. Der erneute HA-Lesevergleich reduziert Konflikte, kann andere Clients zwischen Vergleich und PUT aber nicht ausschließen. Dieses Restrisiko ist dokumentiert; keine Serveränderung vorgenommen.
