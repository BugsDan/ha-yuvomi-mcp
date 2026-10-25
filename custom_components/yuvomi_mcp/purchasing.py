"""Deterministic shopping planner using only current Yuvomi state and a durable write barrier."""

import asyncio
import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from uuid import uuid4

from .journal import MAX_JOURNAL, JournalError, now, text
from .quantities import add_or_replace, quantity_key
from .shopping import normalized_name, resolve_category
from .shopping_api import ShoppingFailure


def response(items, code=None, message=None):
    failed = any(i.get("error") for i in items) or code is not None
    payload = {"items": items}
    if message:
        payload["message"] = message
    result = {
        "isError": failed,
        "items": items,
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
    }
    if code:
        result["code"] = code
    return result


class Purchasing:
    def __init__(self, api, journal):
        self.api = api
        self.journal = journal
        self.locks = {}
        self.active = True

    def allowed(self, authorized):
        if not self.active or not authorized():
            raise ShoppingFailure("not_allowed", "Einkaufswerkzeug ist nicht mehr freigegeben.")
        if self.journal is None or self.journal.broken:
            raise JournalError("Journalspeicher ist nicht sicher verfügbar. Keine Schreibaktionen.")

    async def close(self):
        self.active = False
        # Drain in-flight writes before HA reload creates a second Store owner.
        for lock in list(self.locks.values()):
            async with lock:
                pass
        if self.journal is not None:
            await self.journal.close()

    def blocked(self, list_id):
        return [
            j
            for j in self.journal.data["journal"].values()
            if j["list_id"] == list_id and j["state"] in {"prepared", "unknown"}
        ]

    async def run(self, arguments, request_key, authorized, *, bulk=False, owner=""):
        items = arguments.get("items", []) if bulk else [arguments]
        results = []
        in_flight_name = None
        try:
            self.allowed(authorized)
            if not isinstance(items, list) or not 1 <= len(items) <= 20:
                raise ShoppingFailure("invalid_arguments", "Ein bis zwanzig Einkaufsartikel erforderlich.")
            lists = await self.api.lists()
            requested = arguments.get("list")
            choices = (
                [row for row in lists if row["name"] == requested.strip()]
                if requested
                else sorted(lists, key=lambda r: r["id"])[:1]
            )
            if len(choices) != 1:
                raise ShoppingFailure(
                    "list_unclear", "Zielliste fehlt oder ist mehrdeutig. Exakten Listennamen angeben."
                )
            list_id = choices[0]["id"]
            if list_id not in self.locks:
                if len(self.locks) >= 128:
                    raise ShoppingFailure("busy", "Zu viele verschiedene Einkaufslisten.")
                self.locks[list_id] = asyncio.Lock()
            async with self.locks[list_id]:
                self.allowed(authorized)
                # Replay complete requests before reading or changing current
                # state. The exact same invocation must never reactivate twice.
                prior = [
                    self.journal.data["journal"].get(self._key(request_key, i)) for i in range(len(items))
                ]
                if all(j and j["state"] in {"done", "observed"} for j in prior):
                    return response([j["result"] for j in prior])
                if self.blocked(list_id):
                    statuses = [
                        j["result"]
                        if j and j["state"] in {"done", "observed"}
                        else {
                            "name": items[i].get("name", ""),
                            "error": "execution_unconfirmed"
                            if j and j["state"] in {"prepared", "unknown"}
                            else "not_executed",
                        }
                        for i, j in enumerate(prior)
                    ]
                    return response(
                        statuses,
                        "execution_unconfirmed",
                        "Ein früherer Schreibausgang dieser Liste ist unklar. In den Integrationsoptionen Ausführung prüfen.",
                    )
                categories, rows = await asyncio.gather(self.api.categories(), self.api.items(list_id))
                self.allowed(authorized)
                # Validate/plan every item before the first write. Ambiguity or
                # unsafe arithmetic cannot leave half of a spoken list saved.
                plans, preflight = [], []
                seen = set()
                for i, item in enumerate(items):
                    if prior[i] and prior[i]["state"] in {"done", "observed"}:
                        plans.append({"replay": prior[i]["result"]})
                        preflight.append(prior[i]["result"])
                        seen.add(normalized_name(prior[i]["name"]))
                        continue
                    try:
                        identity = normalized_name(text(item.get("name")))
                        if identity in seen:
                            raise ShoppingFailure(
                                "product_unclear",
                                "Dasselbe Produkt wurde mehrfach genannt. Menge zusammenfassen oder Wunsch präzisieren.",
                            )
                        seen.add(identity)
                        plan = await self.plan(item, rows, categories)
                        plan["intent"] = (
                            sha256(
                                json.dumps(
                                    [owner, list_id, identity, quantity_key(plan["requested_quantity"])],
                                    ensure_ascii=False,
                                    separators=(",", ":"),
                                ).encode()
                            ).hexdigest()
                            if item.get("operation", "ensure") != "set"
                            else None
                        )
                        recent = self.recent(plan, list_id)
                        if recent:
                            previous = recent.get("result") or {}
                            target = next((r for r in rows if r["id"] == previous.get("item_id")), None)
                            if (
                                target is None
                                or target["id"] != plan["item_id"]
                                or normalized_name(target["name"]) != plan["identity"]
                                or target["is_checked"]
                                or target["quantity"] != previous.get("quantity")
                            ):
                                raise ShoppingFailure(
                                    "execution_unconfirmed",
                                    "Ähnliche Anfrage wurde bereits verarbeitet, der Listenstand hat sich geändert. Nicht erneut addiert; Zustand prüfen.",
                                )
                            replay = {**previous, "category": target["category"], "replayed": True}
                            plans.append({"replay": replay, "source": recent, "plan": plan})
                            preflight.append(replay)
                            continue
                        plans.append(plan)
                        preflight.append({"name": item.get("name", ""), "error": "not_executed"})
                    except (ShoppingFailure, JournalError) as err:
                        code = err.code if isinstance(err, ShoppingFailure) else "invalid_arguments"
                        entry = {"name": item.get("name", ""), "error": code, "message": str(err)}
                        if code in {"category_required", "invalid_category"}:
                            entry["valid_categories"] = [c["name"] for c in categories]
                        preflight.append(entry)
                        plans.append(None)
                if None in plans:
                    error = next(i for i in preflight if i.get("error") not in {None, "not_executed"})
                    return response(
                        preflight,
                        error["error"],
                        "Vorprüfung fehlgeschlagen; keine neuen Schreibaktionen. Betroffene Artikel korrigieren und Aufruf erneut senden.",
                    )
                for index, plan in enumerate(plans):
                    if "replay" in plan:
                        if "source" in plan:
                            alias = {
                                **plan["plan"],
                                "method": None,
                                "body": None,
                                "intent_created_at": plan["source"].get(
                                    "intent_created_at", plan["source"]["created_at"]
                                ),
                            }
                            await self._record(
                                self._key(request_key, index),
                                list_id,
                                alias,
                                state="done",
                                result=plan["replay"],
                            )
                        results.append(plan["replay"])
                        continue
                    self.allowed(authorized)
                    key = self._key(request_key, index)
                    body = plan["body"]
                    if body is None:
                        item_result = self._result(plan, "already_present", plan["item_id"])
                        await self._record(key, list_id, plan, state="done", result=item_result)
                    else:
                        if plan["method"] == "PATCH":
                            current = await self.api.items(list_id)
                            target = next((r for r in current if r["id"] == plan["item_id"]), None)
                            if target is None or any(target.get(k) != v for k, v in plan["before"].items()):
                                raise ShoppingFailure(
                                    "concurrent_change",
                                    "Artikel wurde inzwischen geändert. Nichts überschrieben; Anfrage neu prüfen.",
                                )
                        # Disk acknowledgement is mandatory before network I/O.
                        await self._record(key, list_id, plan)
                        try:
                            self.allowed(authorized)
                        except (ShoppingFailure, JournalError):
                            await self._finish(key, "failed")
                            raise
                        in_flight_name = plan["name"]
                        try:
                            written = (
                                await self.api.create(list_id, body, key)
                                if plan["method"] == "POST"
                                else await self.api.update(list_id, plan["item_id"], body)
                            )
                        except asyncio.CancelledError:
                            # The prepared record is already durable. Do not
                            # require another await while cancellation unwinds.
                            raise
                        except ShoppingFailure as err:
                            await self._finish(key, "unknown" if err.uncertain else "failed")
                            results.append({"name": plan["name"], "error": err.code, "message": str(err)})
                            results.extend(
                                {"name": items[i].get("name", ""), "error": "not_executed"}
                                for i in range(index + 1, len(items))
                            )
                            return response(results, err.code, str(err))
                        item_result = self._result(
                            plan,
                            "created" if plan["method"] == "POST" else plan["status"],
                            written["id"],
                        )
                        await self._finish(key, "done", item_result)
                        in_flight_name = None
                    results.append(item_result)
                return response(results)
        except (ShoppingFailure, JournalError) as err:
            code = err.code if isinstance(err, ShoppingFailure) else "storage_error"
            if in_flight_name:
                code = "execution_unconfirmed"
                results.append(
                    {
                        "name": in_flight_name,
                        "error": code,
                        "message": "Schreibvorgang konnte nicht dauerhaft quittiert werden. Zustand prüfen; nicht wiederholen.",
                    }
                )
            results.extend(
                {"name": item.get("name", ""), "error": "not_executed"} for item in items[len(results) :]
            )
            return response(results, code, str(err))

    def recent(self, plan, list_id):
        if not plan.get("intent") or not plan["before"] or plan["before"]["is_checked"]:
            return None
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=120)
        for record in reversed(list(self.journal.data["journal"].values())):
            if (
                record["list_id"] != list_id
                or record["state"] not in {"done", "observed"}
                or normalized_name(record["name"]) != plan["identity"]
                or datetime.fromisoformat(record.get("intent_created_at", record["created_at"])) <= cutoff
            ):
                continue
            if record.get("intent") == plan["intent"]:
                return record
            # Preserve the conservative repeat barrier for pre-1.4.2 additions.
            if (
                "intent" not in record
                and record.get("delta")
                and quantity_key(record["delta"]) == quantity_key(plan["requested_quantity"])
            ):
                return record
        return None

    @staticmethod
    def _key(request_key, index):
        return sha256(f"{request_key}:{index}".encode()).hexdigest()

    @staticmethod
    def _result(plan, status, item_id):
        return {
            "name": plan["name"],
            "item_id": item_id,
            "status": status,
            "category": plan["category"],
            "quantity": plan["quantity"],
            "old_quantity": plan["old_quantity"],
            "new_quantity": plan["quantity"],
            "action": plan["action"],
            "replacement_reason": plan["replacement_reason"],
            "quantity_defaulted": plan["defaulted"],
        }

    async def plan(self, args, rows, categories):
        name = text(args.get("name"))
        identity = normalized_name(name)
        matches = [r for r in rows if normalized_name(r["name"]) == identity]
        opened = [r for r in matches if not r["is_checked"]]
        checked = [r for r in matches if r["is_checked"]]
        if len(opened) > 1 or (not opened and len(checked) > 1):
            raise ShoppingFailure(
                "product_unclear", "Mehrere gleichnamige Yuvomi-Artikel. Bitte klären; nichts bereinigt."
            )
        existing = opened[0] if opened else (checked[0] if checked else None)
        if existing:
            # Yuvomi wins, even over a malformed model suggestion. Never rename it.
            category = existing["category"]
        else:
            if not args.get("category"):
                raise ShoppingFailure(
                    "category_required",
                    "Für diesen neuen Artikel eine Kategorie nachliefern. Gültig: "
                    + json.dumps([c["name"] for c in categories], ensure_ascii=False),
                )
            category = resolve_category(args["category"], categories)
            if category is None:
                raise ShoppingFailure(
                    "invalid_category",
                    "Kategorie ungültig oder mehrdeutig. Gültig: "
                    + json.dumps([c["name"] for c in categories], ensure_ascii=False),
                )
        operation = args.get("operation", "ensure")
        if operation not in {"ensure", "set", "increase"}:
            raise ShoppingFailure("invalid_arguments", "Unbekannte Mengenoperation.")
        quantity = args.get("quantity")
        if quantity is not None:
            if (
                not isinstance(quantity, str)
                or not quantity.strip()
                or len(quantity) > 256
                or any(ord(c) < 32 for c in quantity)
            ):
                raise ShoppingFailure("quantity_unclear", "Ungültige Mengenangabe.")
            # Yuvomi quantities are free text. Preserve the supplied value;
            # only increase() parses quantities for arithmetic below.
        if operation == "set" and quantity is None:
            raise ShoppingFailure("quantity_unclear", "Welche Gesamtmenge soll auf der Liste stehen?")
        defaulted = quantity is None
        requested_quantity = quantity if quantity is not None else "1"
        old_quantity = existing["quantity"] if existing else None
        reason = None
        if opened:
            if operation == "set":
                quantity = requested_quantity
                action = "replaced" if quantity != old_quantity else "unchanged"
                reason = "explicit_set" if action == "replaced" else None
                status = "quantity_set" if action == "replaced" else "already_present"
            else:
                quantity, action, reason = add_or_replace(
                    old_quantity, requested_quantity, defaulted=defaulted
                )
                status = action
            body, method = {"quantity": quantity}, "PATCH"
            if operation == "set" and action == "unchanged":
                body, method = None, None
        elif existing:
            quantity = requested_quantity
            body, method, status = {"is_checked": False, "quantity": quantity}, "PATCH", "reactivated"
            action = status
        else:
            quantity = requested_quantity
            body = {"name": name, "quantity": quantity, "category": category}
            method, status, action = "POST", "created", "created"
        return {
            "name": existing["name"] if existing else name,
            "identity": identity,
            "category": category,
            "body": body,
            "method": method,
            "status": status,
            "item_id": existing["id"] if existing else None,
            "quantity": quantity,
            "old_quantity": old_quantity,
            "requested_quantity": requested_quantity,
            "action": action,
            "replacement_reason": reason,
            "defaulted": defaulted,
            "delta": requested_quantity if operation != "set" else None,
            "before": {k: existing[k] for k in ("name", "quantity", "category", "is_checked")}
            if existing
            else None,
        }

    async def _record(self, key, list_id, plan, *, state="prepared", result=None):
        def update(data):
            journal = data["journal"]
            # Bounded retention; unresolved writes are never evicted.
            if key not in journal and len(journal) >= MAX_JOURNAL:
                completed = next(
                    (
                        k
                        for k, v in journal.items()
                        if v["state"] not in {"prepared", "unknown"}
                        and datetime.fromisoformat(v["created_at"])
                        < datetime.now(timezone.utc) - timedelta(hours=48)
                    ),
                    None,
                )
                if completed is None:
                    raise JournalError("Journal ist voll. Offene Ausführungen zuerst prüfen.")
                del journal[completed]
            journal[key] = {
                "id": key,
                "list_id": list_id,
                "name": plan["name"],
                "method": plan["method"],
                "item_id": plan["item_id"],
                "body": deepcopy(plan["body"]),
                "state": state,
                "result": result,
                "attempt_id": uuid4().hex,
                "created_at": now(),
                "delta": plan.get("delta"),
                "intent": plan.get("intent"),
                "intent_created_at": plan.get("intent_created_at", now()),
                "old_quantity": plan["old_quantity"],
                "action": plan["action"],
                "replacement_reason": plan["replacement_reason"],
            }

        await self.journal.change(update)

    async def _finish(self, key, state, result=None):
        def update(data):
            data["journal"][key].update(state=state, result=result)

        await self.journal.change(update)

    async def reconcile(self, key):
        """Admin read-only review. Never resend a POST/PATCH to find its outcome."""
        journal = self.journal.data["journal"].get(key)
        if not journal or journal["state"] not in {"prepared", "unknown"}:
            raise JournalError("Keine offene Ausführung.")
        list_id = journal["list_id"]
        lock = self.locks.setdefault(list_id, asyncio.Lock())
        async with lock:
            journal = self.journal.data["journal"].get(key)
            if not journal or journal["state"] not in {"prepared", "unknown"}:
                raise JournalError("Ausführung wurde inzwischen abgeschlossen.")
            rows = await self.api.items(list_id)
            if journal["method"] == "PATCH":
                matches = [
                    r
                    for r in rows
                    if r["id"] == journal["item_id"]
                    and all(r.get(k) == v for k, v in journal["body"].items())
                ]
            else:
                matches = [
                    r
                    for r in rows
                    if not r["is_checked"] and all(r.get(k) == v for k, v in journal["body"].items())
                ]
            if len(matches) != 1:
                raise JournalError(
                    "Gewünschter Zustand nicht eindeutig beobachtet. Liste bleibt gesperrt; nichts wurde wiederholt."
                )
            await self._finish(
                key,
                "observed",
                {
                    "name": journal["name"],
                    "status": "state_observed",
                    "item_id": matches[0]["id"],
                    "category": matches[0]["category"],
                    "quantity": matches[0]["quantity"],
                    "old_quantity": journal.get("old_quantity"),
                    "new_quantity": matches[0]["quantity"],
                    "action": "state_observed",
                    "message": "Zustand beobachtet; eigene Ausführung nicht bewiesen. Keine Wiederholung.",
                },
            )
            return deepcopy(self.journal.data["journal"][key]["result"])
