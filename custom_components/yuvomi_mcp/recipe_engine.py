"""Serialized recipe writes with durable transaction receipts, not a recipe database."""

import asyncio
import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256

from .const import RECIPE_READS
from .journal import MAX_JOURNAL, JournalError, now
from .recipes import recipe_body, recipe_snapshot, split_notes
from .shopping_api import ShoppingFailure


def result(data=None, *, code=None, message=None):
    payload = data if data is not None else {"message": message}
    return {
        "isError": code is not None,
        **({"code": code} if code else {}),
        "data": payload,
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
    }


class Recipes:
    def __init__(self, api, journal):
        self.api, self.journal = api, journal
        self.lock = asyncio.Lock()
        self.active = True

    def allowed(self, authorized, *, writing=False):
        if not self.active or not authorized():
            raise ShoppingFailure("not_allowed", "Rezeptwerkzeug nicht mehr freigegeben.")
        if writing and (self.journal is None or self.journal.broken or self.journal.closed):
            raise JournalError("Ausführungsjournal nicht verfügbar; keine Rezeptschreibaktion.")

    async def close(self):
        self.active = False
        async with self.lock:
            pass

    @staticmethod
    def present(row):
        value = deepcopy(row)
        try:
            _, block = split_notes(row.get("notes"))
            value["menu_metadata"] = block
        except ShoppingFailure:
            value["metadata_error"] = "invalid_metadata"
        return value

    async def run(self, tool, args, key, authorized, *, owner=""):
        writing = tool not in RECIPE_READS
        attempted = False
        try:
            self.allowed(authorized, writing=writing)
            if not writing:
                rows = await self.api.recipes()
                self.allowed(authorized)
                if tool == "get_recipe":
                    row = next((r for r in rows if r["id"] == args["recipe_id"]), None)
                    if row is None:
                        raise ShoppingFailure("recipe_not_found", "Rezept-ID nicht gefunden.")
                    return result(self.present(row))
                return result([self.present(r) for r in rows])
            async with self.lock:
                self.allowed(authorized, writing=True)
                prior = self.journal.data["journal"].get(key)
                if prior and prior.get("resource") != "recipes":
                    raise JournalError("Ausführungsschlüssel gehört zu einem anderen Werkzeug.")
                if prior and prior["state"] in {"done", "observed"}:
                    return deepcopy(prior["result"])
                records = self.journal.data["journal"].values()
                if any(
                    r.get("resource") == "recipes" and r["state"] in {"prepared", "unknown"} for r in records
                ):
                    raise ShoppingFailure(
                        "execution_unconfirmed",
                        "Früherer Rezeptschreibausgang unklar. Ausführungen prüfen; nicht erneut schreiben.",
                    )
                rows = await self.api.recipes()
                intent = sha256(
                    json.dumps(
                        [owner, tool, args], ensure_ascii=True, sort_keys=True, separators=(",", ":")
                    ).encode()
                ).hexdigest()
                cutoff = datetime.now(timezone.utc) - timedelta(seconds=120)
                recent = next(
                    (
                        r
                        for r in reversed(list(records))
                        if r.get("resource") == "recipes"
                        and r.get("intent") == intent
                        and r["state"] in {"done", "observed"}
                        and datetime.fromisoformat(r.get("intent_created_at", r["created_at"])) > cutoff
                    ),
                    None,
                )
                if recent:
                    current = next((r for r in rows if r["id"] == recent.get("item_id")), None)
                    if current is None or recipe_snapshot(current) != recent["body"]:
                        raise ShoppingFailure(
                            "concurrent_change",
                            "Ähnlicher Rezeptauftrag bereits verarbeitet; aktueller Zustand abweichend. Nicht erneut geschrieben.",
                        )
                    replay = deepcopy(recent["result"])
                    replay["replayed"] = True
                    await self.record(
                        key,
                        tool,
                        recent["name"],
                        recent["item_id"],
                        recent["body"],
                        intent,
                        state="done",
                        reply=replay,
                        intent_time=recent.get("intent_created_at", recent["created_at"]),
                    )
                    return replay
                existing = (
                    next((r for r in rows if r["id"] == args.get("recipe_id")), None)
                    if tool == "update_recipe"
                    else None
                )
                if tool == "update_recipe" and existing is None:
                    raise ShoppingFailure("recipe_not_found", "Rezept-ID nicht gefunden.")
                body = await recipe_body(args, existing, self.api)
                if any(
                    r["title"] == body["title"] and (not existing or r["id"] != existing["id"]) for r in rows
                ):
                    raise ShoppingFailure(
                        "recipe_exists",
                        "Dieser exakte Rezepttitel existiert bereits. ID lesen und gezielt bearbeiten; Variante nicht umbenennen.",
                    )
                recipe_id = existing["id"] if existing else None
                self.allowed(authorized, writing=True)
                if existing:
                    fresh = next((r for r in await self.api.recipes() if r["id"] == recipe_id), None)
                    if (
                        fresh is None
                        or recipe_snapshot(fresh) != recipe_snapshot(existing)
                        or fresh.get("provider_account_id") != existing.get("provider_account_id")
                        or fresh.get("source") != existing.get("source")
                    ):
                        raise ShoppingFailure(
                            "concurrent_change", "Rezept wurde inzwischen geändert; nichts überschrieben."
                        )
                if existing and recipe_snapshot(existing) == body:
                    reply = result({"status": "unchanged", "recipe": self.present(existing)})
                    await self.record(
                        key, tool, body["title"], recipe_id, body, intent, state="done", reply=reply
                    )
                    return reply
                await self.record(key, tool, body["title"], recipe_id, body, intent)
                try:
                    self.allowed(authorized, writing=True)
                except (ShoppingFailure, JournalError):
                    await self.finish(key, "failed")
                    raise
                attempted = True
                try:
                    saved = await self.api.save(recipe_id, body, key)
                except ShoppingFailure as error:
                    await self.finish(key, "unknown" if error.uncertain else "failed")
                    raise
                reply = result(
                    {"status": "updated" if existing else "created", "recipe": self.present(saved)}
                )
                await self.finish(key, "done", reply, item_id=saved["id"])
                return reply
        except (ShoppingFailure, JournalError) as error:
            code = (
                error.code
                if isinstance(error, ShoppingFailure)
                else ("execution_unconfirmed" if attempted else "storage_error")
            )
            return result(code=code, message=str(error))

    async def record(
        self, key, tool, name, recipe_id, body, intent, *, state="prepared", reply=None, intent_time=None
    ):
        def change(data):
            journal = data["journal"]
            if key not in journal and len(journal) >= MAX_JOURNAL:
                expired = next(
                    (
                        k
                        for k, r in journal.items()
                        if r["state"] not in {"prepared", "unknown"}
                        and datetime.fromisoformat(r["created_at"])
                        < datetime.now(timezone.utc) - timedelta(hours=48)
                    ),
                    None,
                )
                if expired is None:
                    raise JournalError("Journal voll; offene Ausführungen zuerst prüfen.")
                del journal[expired]
            journal[key] = {
                "id": key,
                "resource": "recipes",
                "list_id": 1,
                "name": name,
                "method": "PUT" if tool == "update_recipe" else "POST",
                "item_id": recipe_id,
                "body": deepcopy(body),
                "state": state,
                "result": deepcopy(reply),
                "intent": intent,
                "intent_created_at": intent_time or now(),
                "created_at": now(),
            }

        await self.journal.change(change)

    async def finish(self, key, state, reply=None, *, item_id=None):
        def change(data):
            record = data["journal"][key]
            record.update(state=state, result=deepcopy(reply))
            if item_id is not None:
                record["item_id"] = item_id

        await self.journal.change(change)

    async def reconcile(self, key):
        """Observe only; uncertain recipe writes are never resent."""
        if self.journal is None or not self.active:
            raise JournalError("Rezeptjournal nicht verfügbar.")
        async with self.lock:
            record = self.journal.data["journal"].get(key)
            if (
                not record
                or record.get("resource") != "recipes"
                or record["state"] not in {"prepared", "unknown"}
            ):
                raise JournalError("Keine offene Rezeptausführung.")
            rows = await self.api.recipes()
            matches = [
                r
                for r in rows
                if (record["item_id"] is None or record["item_id"] == r["id"])
                and recipe_snapshot(r) == record["body"]
            ]
            if len(matches) != 1:
                raise JournalError("Rezeptzustand nicht eindeutig beobachtet; Schreibsperre bleibt.")
            reply = result(
                {
                    "status": "state_observed",
                    "recipe": self.present(matches[0]),
                    "message": "Zustand beobachtet; eigene Ausführung nicht bewiesen. Keine Wiederholung.",
                }
            )
            await self.finish(key, "observed", reply, item_id=matches[0]["id"])
            return {
                "message": "Rezeptzustand beobachtet; eigene Ausführung nicht bewiesen. Keine Wiederholung."
            }
