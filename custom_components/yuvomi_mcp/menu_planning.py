"""Gemma chooses meals; this engine validates and journals bounded REST writes."""

import asyncio
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from time import monotonic
from uuid import uuid4
from zoneinfo import ZoneInfo

from .journal import MAX_JOURNAL, JournalError, now
from .meals_api import slot, snapshot
from .menu_metadata import metadata, notes_block, scale
from .planning_config import period
from .planning_context import PLANNING_PROMPT, attendance, day_range, fail, fingerprint, portions
from .recipe_engine import Recipes, result
from .shopping_api import ShoppingFailure


class MenuPlanning:
    def __init__(self, api, recipes, store, journal, calendar_reader=None, clock=monotonic, today=None):
        self.api, self.recipes, self.store, self.journal = api, recipes, store, journal
        self.calendar_reader = calendar_reader
        self.clock, self.today = clock, today
        self.lock = asyncio.Lock()
        self.contexts = {}
        self.active = True

    def allowed(self, authorized, writing=False):
        if not self.active or not authorized():
            fail("not_allowed", "Menüwerkzeug nicht mehr freigegeben.")
        if self.store is None or self.store.broken:
            fail("storage_unavailable", "Planungsspeicher nicht verfügbar.")
        if writing and (self.journal is None or self.journal.broken or self.journal.closed):
            raise JournalError("Ausführungsjournal nicht verfügbar.")

    async def close(self):
        self.active = False
        self.contexts.clear()
        async with self.lock:
            pass

    def target(self, args, config):
        today = self.today() if self.today else datetime.now(ZoneInfo(config["timezone"])).date()
        if args.get("date"):
            first = last = date.fromisoformat(args["date"])
        elif args.get("start_date"):
            first = date.fromisoformat(args["start_date"])
            start, last = period(config, first)
            if start != first:
                fail("date_unclear", "start_date muss zum konfigurierten Periodenanker passen.")
        else:
            first, last = period(config, today, args.get("period", "current"))
        if sum(k in args for k in ("date", "start_date", "period")) > 1:
            fail("date_unclear", "Genau einen Datumsbezug verwenden.")
        return first, last

    async def facts(self, config, start, end, actor):
        if config["calendars"] and self.calendar_reader is None:
            fail("calendar_not_allowed", "Kalenderadapter nicht verfügbar.")
        events = await self.calendar_reader(config, start, end, actor) if config["calendars"] else {}
        return attendance(config, start, end, events)

    async def run(self, tool, args, key, authorized, *, owner="", actor=None):
        try:
            self.allowed(authorized, writing=tool == "save_menu_plan")
            await self.store.load()
            if tool == "get_menu_plan":
                config = self.store.data["config"]
                first, last = self.target(args, config)
                rows = await self.api.meals(first, last)
                self.allowed(authorized)
                today = self.today() if self.today else datetime.now(ZoneInfo(config["timezone"])).date()
                if not args.get("date") and args.get("detail", "brief") != "full":
                    rows = [
                        r
                        for r in rows
                        if r["date"] in {today.isoformat(), (today + timedelta(days=1)).isoformat()}
                    ]
                return result({"status": "read", "start": str(first), "end": str(last), "meals": rows})
            if tool == "get_menu_planning_context":
                return await self.context(args, key, authorized, owner, actor)
            async with self.lock:
                return await self.save(args, key, authorized, owner, actor)
        except (ShoppingFailure, JournalError) as error:
            return result(
                code=error.code if isinstance(error, ShoppingFailure) else "storage_error", message=str(error)
            )
        except (ValueError, KeyError, TypeError, ArithmeticError):
            return result(
                code="invalid_planning_data",
                message="Planungsdaten unvollständig oder mehrdeutig; nichts erneut schreiben.",
            )

    async def context(self, args, request, authorized, owner, actor):
        self.contexts = {k: v for k, v in self.contexts.items() if v["expires"] > self.clock()}
        for value in self.contexts.values():
            if value["request"] == request and value["owner"] == owner:
                return result(deepcopy(value["public"]))
        if len(self.contexts) >= 16:
            fail("busy", "Zu viele aktive Planungssitzungen.")
        revision = self.store.data["revision"]
        config = deepcopy(self.store.data["config"])
        if not config["profiles"]:
            fail("planning_not_configured", "Zuerst Familienprofile in den Integrationsoptionen einrichten.")
        action = args["action"]
        if action != "create_period" and "date" not in args:
            fail("date_unclear", "Tagesänderung/Vorschlag braucht ein eindeutiges ISO-Datum.")
        if action == "create_period" and "date" in args:
            fail("date_unclear", "Wochenplanung braucht eine ganze konfigurierte Periode.")
        first, last = self.target(args, config)
        period_start, period_end = period(config, first)
        prior_start = period_start - timedelta(days=config["length_days"])
        rows = await self.api.meals(
            prior_start - timedelta(days=2), max(period_end, last) + timedelta(days=2)
        )
        candidates = deepcopy(await self.recipes.api.recipes())
        if args.get("requested_recipe"):
            candidates = [r for r in candidates if r["title"] == args["requested_recipe"]]
            if len(candidates) != 1:
                fail("recipe_unclear", "Exakter Rezeptname/Variante nicht eindeutig vorhanden.")
        facts = await self.facts(config, first - timedelta(days=2), last + timedelta(days=2), actor)
        ident = uuid4().hex
        public = {
            "context_id": ident,
            "action": action,
            "start": str(first),
            "end": str(last),
            "revision": revision,
            "prompt": PLANNING_PROMPT,
            "rules": config,
            "attendance": facts,
            "recipes": [Recipes.present(r) for r in candidates],
            "existing": [r for r in rows if str(first) <= r["date"] <= str(last)],
            "previous_recipe_ids": self.previous(rows, prior_start, period_start),
            "expires_in_seconds": 300,
            "session_requirement": "Whole-period planning requires a deliberately separate conversation; no automatic isolation.",
        }
        occupied_slots = {slot(r) for r in rows}
        public["free_slots"] = [
            {"date": str(d), "meal_type": config["meal_type"]}
            for d in day_range(first, last)
            if d.weekday() in config["days"] and (str(d), config["meal_type"]) not in occupied_slots
        ]
        public["status"] = (
            "already_planned" if action == "create_period" and not public["free_slots"] else "ready"
        )
        if action != "create_period":
            public["related_meals"] = [
                r
                for r in rows
                if first - timedelta(days=2) <= date.fromisoformat(r["date"]) <= last + timedelta(days=2)
            ]
        self.allowed(authorized)
        if self.store.data["revision"] != revision:
            fail("context_stale", "Planungskonfiguration während der Datenbeschaffung geändert.")
        self.contexts[ident] = {
            "public": deepcopy(public),
            "owner": owner,
            "request": request,
            "expires": self.clock() + 300,
            "config": config,
            "rows": rows,
            "recipes": candidates,
            "facts": facts,
            "args": deepcopy(args),
            "first": first,
            "last": last,
            "prior_start": prior_start,
            "period_start": period_start,
            "period_end": period_end,
        }
        return result(public)

    @staticmethod
    def previous(rows, first, end):
        ids = set()
        for row in rows:
            if str(first) <= row["date"] < str(end):
                block = metadata(row.get("notes"))
                ident = (
                    row.get("recipe_id")
                    or (block or {}).get("source_recipe_id")
                    or (block or {}).get("recipe_id")
                )
                if ident:
                    ids.add(ident)
        return sorted(ids)

    def prepare(self, ctx, assignments):
        config, facts = ctx["config"], ctx["facts"]
        recipes = {r["id"]: r for r in ctx["recipes"]}
        occupied = {slot(r) for r in ctx["rows"]}
        chosen, used_needs = {}, set()
        for a in assignments:
            key = a["date"], config["meal_type"]
            if key in chosen:
                fail("invalid_plan", "Doppelter Datum-/Mahlzeitslot.")
            day = date.fromisoformat(a["date"])
            if not ctx["first"] <= day <= ctx["last"] or day.weekday() not in config["days"]:
                fail("invalid_plan", "Tag außerhalb freigegebener Planungstage.")
            if ctx["args"]["action"] == "create_period" and key in occupied:
                fail("occupied", "Bestehender Menüeintrag bleibt bei Erstplanung erhalten.")
            if a["recipe_id"] not in recipes:
                fail("recipe_unclear", "Rezept gehört nicht zum gebundenen Kontext.")
            chosen[key] = a
        if ctx["args"]["action"] == "replace_day" and len(chosen) != 1:
            fail("invalid_plan", "Tagesänderung darf genau einen Slot ersetzen.")
        if ctx["args"]["action"] == "create_period":
            required = {
                (str(d), config["meal_type"])
                for d in day_range(ctx["first"], ctx["last"])
                if d.weekday() in config["days"]
            } - occupied
            if set(chosen) != required:
                fail(
                    "incomplete_plan", "Alle freien Planungstage gemeinsam zuweisen; belegte Tage auslassen."
                )
        old_needs = {}
        for row in ctx["rows"]:
            block = metadata(row.get("notes"))
            if not block:
                continue
            extras = block.get("extras", [])
            if not isinstance(extras, list):
                fail("invalid_metadata", "Ungültige Zusatzportionen in Yuvomi.")
            for extra in extras:
                need = (extra["date"], extra.get("meal_type", config["meal_type"]), extra["profile_id"])
                source = slot(row)
                if source not in chosen:
                    if need in old_needs and old_needs[need] != source:
                        fail("invalid_plan", "Zusatzbedarf in Yuvomi mehrfach zugeordnet.")
                    old_needs[need] = source
                elif need[:2] not in chosen:
                    fail(
                        "dependent_meal", "Dieser Kochtag versorgt einen anderen Tag; Änderungsumfang klären."
                    )
            if block.get("kind") == "reheat" and slot(row) not in chosen:
                source = block.get("source_date"), block.get("source_meal_type", config["meal_type"])
                if source in chosen:
                    fail(
                        "dependent_meal", "Anderer Aufwärmtag hängt von dieser Quelle ab; nicht still ändern."
                    )
        bodies = []
        previous = set(ctx["public"]["previous_recipe_ids"])
        extras_by_source = {}
        for key, a in chosen.items():
            extras = a.get("extra_servings", [])
            if a["kind"] == "reheat" and extras:
                fail("invalid_plan", "Aufwärmen erzeugt keine weiteren Zusatzportionen.")
            for extra in extras:
                target = date.fromisoformat(extra["date"])
                need = (str(target), config["meal_type"], extra["profile_id"])
                profile = facts.get(str(target), {}).get(extra["profile_id"])
                if (
                    not profile
                    or not profile["reheat"]
                    or Decimal(str(extra["servings"])) != Decimal(str(profile["portion"]))
                    or not 1 <= (target - date.fromisoformat(key[0])).days <= config["max_reheat_days"]
                    or need in used_needs
                    or need in old_needs
                ):
                    fail(
                        "invalid_plan", "Zusatzportionen: Bedarf, Abstand oder eindeutige Zuordnung ungültig."
                    )
                if (
                    need[:2] not in chosen
                    or chosen[need[:2]]["kind"] != "reheat"
                    or chosen[need[:2]].get("source_date") != key[0]
                ):
                    fail(
                        "incomplete_plan",
                        "Zusatzportion benötigt den passenden Aufwärmeintrag im selben Vorgang.",
                    )
                used_needs.add(need)
                extras_by_source.setdefault(key, []).append({**extra, "meal_type": config["meal_type"]})
        for key, a in chosen.items():
            recipe = recipes[a["recipe_id"]]
            presented = Recipes.present(recipe)
            if "metadata_error" in presented:
                fail("invalid_metadata", "Rezeptmetadaten beschädigt; nicht raten.")
            meta = (presented.get("menu_metadata") or {}).get("metadata", {})
            day = date.fromisoformat(key[0])
            kind = a["kind"]
            if a["recipe_id"] in previous - set(config["repeat_exceptions"]):
                fail("repeat_forbidden", "Rezept bereits in unmittelbar vorheriger Planungsperiode.")
            if kind == "rest" and (
                a["recipe_id"] != config["rest_recipe_id"] or day.weekday() in config["rest_excluded_days"]
            ):
                fail("invalid_plan", "Resten-Rezept/Tag ist nicht freigegeben.")
            if kind == "emergency" and a["recipe_id"] not in config["emergency_recipe_ids"]:
                fail("invalid_plan", "Kein konfiguriertes Notfallmenü.")
            if config["rest_day"] == day.weekday() and a["recipe_id"] != config["rest_recipe_id"]:
                fail("invalid_plan", "Konfigurierter fester Restentag.")
            extras = extras_by_source.get(key, [])
            recipients = {p for p, v in facts[key[0]].items() if v["present"]}
            if kind == "reheat":
                source = a.get("source_date"), config["meal_type"]
                source_a = chosen.get(source)
                source_extras = extras_by_source.get(source, [])
                if source_a is None:
                    existing_sources = [r for r in ctx["rows"] if slot(r) == source]
                    if len(existing_sources) != 1:
                        fail("invalid_plan", "Aufwärmquelle nicht eindeutig vorhanden.")
                    stored = metadata(existing_sources[0].get("notes"))
                    if not stored:
                        fail(
                            "invalid_plan",
                            "Bestehende Kochquelle hat keine bestätigbare geplante Zusatzportion.",
                        )
                    source_a = stored
                    source_extras = stored.get("extras", [])
                if (
                    source_a["recipe_id"] != a["recipe_id"]
                    or source_a["kind"] == "reheat"
                    or meta.get("wiederaufwärmbar") is not True
                    or not 1 <= (day - date.fromisoformat(source[0])).days <= config["max_reheat_days"]
                ):
                    fail("invalid_plan", "Aufwärmquelle/Rezept/Abstand nicht gültig.")
                selected = [
                    e for e in source_extras if e["date"] == key[0] and e.get("meal_type", key[1]) == key[1]
                ]
                if len({e["profile_id"] for e in selected}) != len(selected):
                    fail("invalid_plan", "Doppelter Aufwärmbedarf in gespeicherter Quelle.")
                for extra in selected:
                    person = facts[key[0]].get(extra["profile_id"])
                    if not person or Decimal(str(extra["servings"])) != Decimal(str(person["portion"])):
                        fail("invalid_plan", "Gespeicherte Zusatzportion passt nicht zum aktuellen Bedarf.")
                recipients = {e["profile_id"] for e in selected}
                needed = {p for p, v in facts[key[0]].items() if v["reheat"]}
                # A single meal slot cannot silently represent two different dishes.
                if (
                    not recipients
                    or recipients != needed
                    or {p for p, v in facts[key[0]].items() if v["present"]} - recipients
                ):
                    fail(
                        "attendance_unclear",
                        "Aufwärmportionen decken diesen Slot nicht eindeutig; mehrere Gerichte benötigen getrennte Klärung.",
                    )
                count = sum((Decimal(str(e["servings"])) for e in selected), Decimal(0))
                ingredients, native_id = [], None
                elapsed = config["reheat_time_min"]
            else:
                if any(need[:2] == key for need in old_needs):
                    fail(
                        "dependent_meal",
                        "Eine andere Kochquelle versorgt diesen Tag; Zuordnung zuerst ausdrücklich klären.",
                    )
                if "source_date" in a:
                    fail("invalid_plan", "Nur Aufwärmeinträge dürfen eine Quelle enthalten.")
                count = portions(facts[key[0]])
                if any(v["reheat"] for v in facts[key[0]].values()):
                    fail(
                        "invalid_plan",
                        "Konfigurierter Aufwärmbedarf braucht eine eindeutige Aufwärmzuordnung.",
                    )
                count += sum((Decimal(str(e["servings"])) for e in extras), Decimal(0))
                recipients |= {e["profile_id"] for e in extras}
                if extras and meta.get("wiederaufwärmbar") is not True:
                    fail("invalid_plan", "Zusatzportionen nur bei nachweislich wiederaufwärmbarem Gericht.")
                if count <= 0:
                    fail("attendance_unclear", "Kein eindeutiger Portionsbedarf.")
                ingredients = scale(
                    recipe["ingredients"], count / Decimal(str(meta.get("basisportionen", 4)))
                )
                native_id, elapsed = a["recipe_id"], meta.get("zubereitungszeit_min")
            for ident in recipients:
                profile = config["profiles"][ident]
                if (
                    a["recipe_id"] in profile.get("dislikes", [])
                    or profile["name"] in meta.get("mag_nicht", [])
                    or ident in meta.get("mag_nicht", [])
                ):
                    fail("disliked_recipe", "Gericht wird von einer betroffenen Person nicht akzeptiert.")
            limit = config["time_limits"].get(str(day.weekday()))
            if limit is not None and (elapsed is None or elapsed > limit):
                fail(
                    "time_limit",
                    "Gesamte Zubereitungs-/Aufwärmzeit erfüllt das Tageslimit nicht nachweislich.",
                )
            old = [r for r in ctx["rows"] if slot(r) == key]
            if len(old) > 1:
                fail("occupied_unclear", "Mehrere Mahlzeiten im Slot; nicht pauschal ersetzen.")
            data = {
                "v": 1,
                "kind": kind,
                "recipe_id": a["recipe_id"],
                "date": key[0],
                "meal_type": key[1],
                "servings_total": float(count),
                "extras": extras,
            }
            summary = f"{count} Portionen; Zusatzportionen: " + ", ".join(
                f"{e['profile_id']} {e['date']}: {e['servings']}" for e in extras
            )
            if kind == "reheat":
                data.update(
                    source_date=a["source_date"],
                    source_meal_type=key[1],
                    source_recipe_id=a["recipe_id"],
                    recipients=sorted(recipients),
                )
                summary = f"Aufwärmen vom {a['source_date']}: {count} Portionen; Zutaten beim Kochtag."
            else:
                data["servings_now"] = float(portions(facts[key[0]]))
            body = {
                "date": key[0],
                "meal_type": key[1],
                "title": recipe["title"],
                "recipe_id": native_id,
                "recipe_url": (old[0].get("recipe_url") if old else recipe.get("recipe_url")),
                "notes": notes_block(old[0].get("notes") if old else None, data, summary),
                "ingredients": ingredients,
            }
            if old and old[0].get("cook_user_id") is not None:
                body["cook_user_id"] = old[0]["cook_user_id"]
            bodies.append(body)
        return bodies

    async def save(self, args, key, authorized, owner, actor):
        self.allowed(authorized, writing=True)
        ctx = self.contexts.get(args["context_id"])
        if not ctx or ctx["owner"] != owner or ctx["expires"] <= self.clock():
            fail("context_stale", "Planungskontext abgelaufen oder nach Neustart nicht mehr vorhanden.")
        if ctx["args"]["action"] == "suggest_day":
            fail("not_allowed", "Vorschlag darf nicht gespeichert werden.")
        args_hash = fingerprint(args["assignments"])
        if ctx.get("completed"):
            if ctx["args_hash"] != args_hash:
                fail(
                    "context_stale", "Bereits gespeicherter Kontext darf nicht anders wiederverwendet werden."
                )
            replay = deepcopy(ctx["completed"])
            replay["replayed"] = True
            return replay
        prior_key = self.journal.data["journal"].get(key)
        if prior_key and prior_key.get("resource") != "meals":
            raise JournalError("Ausführungsschlüssel gehört zu einer anderen Ressource.")
        records = self.journal.data["journal"].values()
        if any(r.get("resource") == "meals" and r["state"] in {"prepared", "unknown"} for r in records):
            fail("execution_unconfirmed", "Menüschreibausgang unklar; Ausführungen lesend prüfen.")
        if self.store.data["revision"] != ctx["public"]["revision"]:
            fail("context_stale", "Planungskonfiguration geändert.")
        bodies = self.prepare(ctx, args["assignments"])
        intent = fingerprint([owner, ctx["args"], str(ctx["first"]), str(ctx["last"])])
        recent = [
            r
            for r in records
            if r.get("resource") == "meals"
            and r.get("intent") == intent
            and r["state"] in {"done", "observed"}
            and (
                r.get("request") == ctx["request"]
                or datetime.fromisoformat(r["created_at"])
                > datetime.now(timezone.utc) - timedelta(seconds=120)
            )
        ]
        if recent:
            prior = recent[-1]
            if prior["body"]["assignments"] != bodies:
                fail(
                    "request_unclear",
                    "Ähnlicher Menüauftrag bereits bearbeitet; neuer Änderungswunsch oder Retry unklar.",
                )
            reply = deepcopy(prior["result"])
            reply["replayed"] = True
            return reply
        fresh = await self.api.meals(
            ctx["prior_start"] - timedelta(days=2), ctx["period_end"] + timedelta(days=2)
        )
        if fingerprint(fresh) != fingerprint(ctx["rows"]):
            fail("concurrent_change", "Menübestand wurde geändert; neuen Kontext lesen.")
        fresh_recipes = {r["id"]: r for r in await self.recipes.api.recipes()}
        if any(fresh_recipes.get(r["id"]) != r for r in ctx["recipes"]):
            fail("context_stale", "Rezeptdaten inzwischen geändert.")
        facts = await self.facts(
            ctx["config"], ctx["first"] - timedelta(days=2), ctx["last"] + timedelta(days=2), actor
        )
        if facts != ctx["facts"]:
            fail("attendance_unclear", "Anwesenheit inzwischen geändert.")
        self.allowed(authorized, writing=True)
        if not bodies:
            return result(
                {"status": "already_planned", "message": "Alle Planungstage bereits belegt; nichts geändert."}
            )
        replacing = ctx["args"]["action"] == "replace_day"
        body = {"assignments": bodies, "replace_existing" if replacing else "skip_occupied": True}

        def prepare(data):
            journal = data["journal"]
            if len(journal) >= MAX_JOURNAL and key not in journal:
                fail("storage_full", "Journal voll; keine Menüschreibaktion.")
            journal[key] = {
                "id": key,
                "resource": "meals",
                "list_id": 1,
                "name": "Menüplan " + str(ctx["first"]),
                "method": "POST",
                "item_id": None,
                "body": body,
                "state": "prepared",
                "result": None,
                "intent": intent,
                "request": ctx["request"],
                "created_at": now(),
            }

        await self.journal.change(prepare)
        try:
            self.allowed(authorized, writing=True)
            if (
                self.store.data["revision"] != ctx["public"]["revision"]
                or self.clock() >= ctx["expires"]
                or self.contexts.get(args["context_id"]) is not ctx
            ):
                fail("context_stale", "Planungskontext vor Schreibbeginn geändert/abgelaufen.")
        except (ShoppingFailure, JournalError):
            await self.finish(key, "failed")
            raise
        try:
            response = await self.api.apply(bodies, key, replace=replacing)
            rows = response.get("data")
            skipped = response.get("skipped", [])
            if skipped or not isinstance(rows, list) or len(rows) != len(bodies):
                fail(
                    "execution_unconfirmed",
                    "Menüauftrag nur teilweise bestätigt; Bestand prüfen, nicht erneut schreiben.",
                )
            ids = set()
            for expected, saved in zip(bodies, rows, strict=True):
                self.api.validate(saved)
                if saved["id"] in ids or any(snapshot(saved).get(k) != v for k, v in expected.items()):
                    fail("execution_unconfirmed", "Menüantwort bestätigt den Zielzustand nicht eindeutig.")
                ids.add(saved["id"])
            reply = result(
                {
                    "status": "replaced" if replacing else "created",
                    "start": str(ctx["first"]),
                    "end": str(ctx["last"]),
                    "meal_ids": sorted(ids),
                    "count": len(rows),
                    "shopping_transferred": False,
                }
            )
            await self.finish(key, "done", reply)
        except asyncio.CancelledError:
            # prepared is already a durable barrier if cancellation prevents another save.
            raise
        except (ShoppingFailure, KeyError, TypeError, ValueError) as error:
            uncertain = (
                not isinstance(error, ShoppingFailure)
                or error.uncertain
                or error.code in {"execution_unconfirmed", "invalid_response"}
            )
            await self.finish(key, "unknown" if uncertain else "failed")
            if uncertain:
                fail(
                    "execution_unconfirmed",
                    "Menüschreibausgang nicht eindeutig. Ausführungen prüfen; nicht blind wiederholen.",
                )
            raise
        except JournalError:
            fail(
                "execution_unconfirmed",
                "Menüantwort erhalten, Journalabschluss nicht bestätigt. Keine Wiederholung.",
            )
        ctx["completed"], ctx["args_hash"] = deepcopy(reply), args_hash
        return reply

    async def finish(self, key, state, reply=None):
        def update(data):
            data["journal"][key].update(state=state, result=deepcopy(reply))

        await self.journal.change(update)

    async def reconcile(self, key):
        async with self.lock:
            if self.journal is None:
                raise JournalError("Menüjournal fehlt.")
            record = self.journal.data["journal"].get(key)
            if (
                not record
                or record.get("resource") != "meals"
                or record["state"] not in {"prepared", "unknown"}
            ):
                raise JournalError("Keine offene Menüausführung.")
            expected = record["body"]["assignments"]
            rows = await self.api.meals(min(b["date"] for b in expected), max(b["date"] for b in expected))
            if any(
                len(
                    [
                        r
                        for r in rows
                        if slot(r) == slot(b) and all(snapshot(r).get(k) == v for k, v in b.items())
                    ]
                )
                != 1
                for b in expected
            ):
                raise JournalError("Menüzustand nicht eindeutig; Schreibsperre bleibt.")
            reply = result(
                {
                    "status": "state_observed",
                    "message": "Menüzustand beobachtet; eigene Ausführung nicht bewiesen. Keine Wiederholung.",
                }
            )
            await self.finish(key, "observed", reply)
            return reply["data"]
