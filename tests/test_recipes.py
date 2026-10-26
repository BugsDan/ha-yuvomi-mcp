"""Recipe metadata, narrow REST, opt-in, durable retries and no shopping transfer."""

import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock

import aiohttp
import probatio
import pytest
from test_client import CompatibleResponse, aioresponses
from test_journal import MemoryStore, make_journal
from test_purchasing import API as ShoppingFake
from test_purchasing import CATEGORIES

from custom_components.yuvomi_mcp.client import MCPClient
from custom_components.yuvomi_mcp.const import DEFAULT_TOOLS, RECIPE_READS, RECIPE_WRITES
from custom_components.yuvomi_mcp.journal import JournalError
from custom_components.yuvomi_mcp.purchasing import Purchasing
from custom_components.yuvomi_mcp.recipe_engine import Recipes
from custom_components.yuvomi_mcp.recipes import (
    END,
    START,
    RecipeAPI,
    merged_notes,
    recipe_snapshot,
    split_notes,
)
from custom_components.yuvomi_mcp.runtime import Runtime
from custom_components.yuvomi_mcp.shopping_api import ShoppingFailure

METADATA = {
    "wiederaufwärmbar": True,
    "zubereitungszeit_min": 45,
    "gesundheit": 4,
    "gesundheit_begruendung": "Gemüse und Hülsenfrüchte; wenig zugesetzter Zucker.",
}
CREATE = {
    "title": "Curry – Variante mit Käse",
    "ingredients": [{"name": "Käse", "quantity": "200 g", "category": "Sonstiges"}],
    "metadata": METADATA,
    "notes": "Langsam köcheln.\nNicht pürieren.",
}


def recipe(ident=1, **overrides):
    return {
        "id": ident,
        "title": "Curry – Variante mit Käse",
        "notes": "GUI-Notiz behalten",
        "recipe_url": "https://example.com/rezept",
        "meal_types": ["dinner"],
        "ingredients": [
            {"id": 2, "name": "Käse", "quantity": "200 g", "category": "Sonstiges", "pantry_item_id": 42}
        ],
        "source": "native",
        "provider_account_id": None,
        "has_own_image": True,
        **overrides,
    }


class API:
    def __init__(self, rows=None):
        self.rows = deepcopy(rows or [])
        self.writes = []
        self.error = None
        self.after = None
        self.read_hook = None
        self.reads = 0
        self.category_reads = 0
        self.delay = 0

    async def categories(self):
        self.category_reads += 1
        return deepcopy(CATEGORIES)

    async def recipes(self):
        self.reads += 1
        if self.read_hook:
            self.read_hook(self)
        return deepcopy(self.rows)

    async def save(self, ident, body, key):
        if self.delay:
            await asyncio.sleep(self.delay)
        self.writes.append((ident, deepcopy(body), key))
        if self.error:
            raise self.error
        if ident:
            saved = next(r for r in self.rows if r["id"] == ident)
            saved.update(deepcopy(body))
        else:
            saved = recipe(max([r["id"] for r in self.rows], default=0) + 1, **deepcopy(body))
            self.rows.append(saved)
        if self.after:
            self.after()
        return deepcopy(saved)


async def engine(rows=None, store=None):
    api = API(rows)
    journal = await make_journal(store)
    return Recipes(api, journal), api, journal


async def call(service, args=None, key="request", tool="create_recipe", authorized=lambda: True):
    return await service.run(
        tool, deepcopy(CREATE if args is None else args), key, authorized, owner="family"
    )


async def test_create_defaults_structured_metadata_and_exact_variant():
    service, api, journal = await engine()
    reply = await call(service)
    assert not reply["isError"]
    saved = api.rows[0]
    assert saved["title"] == CREATE["title"] and saved["meal_types"] == ["lunch"]
    plain, block = split_notes(saved["notes"])
    assert plain == CREATE["notes"]
    assert block["metadata"] == {**METADATA, "basisportionen": 4, "mag_nicht": []}
    assert block["gesundheit_herkunft"] == "ki_vorschlag"
    assert saved["ingredients"] == CREATE["ingredients"]
    assert journal.data["journal"]["request"]["resource"] == "recipes"
    assert api.writes[0][2] == "request"


async def test_resten_is_ordinary_recipe_and_custom_servings_are_stored_not_scaled():
    service, api, _ = await engine()
    args = {
        **CREATE,
        "title": "Resten",
        "ingredients": [],
        "metadata": {**METADATA, "basisportionen": 6, "mag_nicht": ["Kind A"]},
    }
    assert not (await call(service, args))["isError"]
    assert api.category_reads == 0 and api.rows[0]["ingredients"] == []
    assert split_notes(api.rows[0]["notes"])[1]["metadata"]["basisportionen"] == 6


@pytest.mark.parametrize(
    "args",
    [
        {**CREATE, "metadata": {**METADATA, "gesundheit": 6}},
        {**CREATE, "metadata": {**METADATA, "basisportionen": True}},
        {**CREATE, "metadata": {**METADATA, "gesundheit_begruendung": " "}},
        {**CREATE, "metadata": {k: v for k, v in METADATA.items() if k != "wiederaufwärmbar"}},
        {**CREATE, "notes": START},
        {**CREATE, "title": " Curry "},
        {**CREATE, "ingredients": [{"name": "Reis", "quantity": "1 kg", "category": "Invented"}]},
    ],
)
async def test_invalid_recipe_never_writes(args):
    service, api, _ = await engine()
    assert (await call(service, args))["isError"]
    assert not api.writes


@pytest.mark.parametrize(
    "mode,expected", [(None, "GUI-Notiz behalten\nZusatz"), ("replace", "Zusatz"), ("clear", None)]
)
async def test_recipe_note_edit_preserves_ingredients_url_image_meal_type(mode, expected):
    original = recipe()
    service, api, _ = await engine([original])
    args = {"recipe_id": 1}
    if mode:
        args["notes_mode"] = mode
    if mode != "clear":
        args["notes"] = "Zusatz"
    reply = await call(service, args, tool="update_recipe")
    assert not reply["isError"]
    saved = api.rows[0]
    assert saved["notes"] == expected
    assert saved["title"] == original["title"] and saved["meal_types"] == ["dinner"]
    assert saved["recipe_url"] == original["recipe_url"] and saved["has_own_image"]
    assert [{k: i[k] for k in ("name", "quantity", "category")} for i in original["ingredients"]] == saved[
        "ingredients"
    ]
    assert "image_data" not in api.writes[0][1]
    assert api.category_reads == 0


async def test_metadata_merge_preserves_plain_notes_and_unspecified_fields():
    notes = merged_notes(None, CREATE, creating=True)
    service, api, _ = await engine([recipe(notes=notes)])
    args = {"recipe_id": 1, "metadata": {"mag_nicht": ["Papa"]}}
    assert not (await call(service, args, tool="update_recipe"))["isError"]
    plain, data = split_notes(api.rows[0]["notes"])
    assert plain == CREATE["notes"] and data["metadata"]["mag_nicht"] == ["Papa"]
    assert data["metadata"]["basisportionen"] == 4 and data["metadata"]["gesundheit"] == 4
    assert merged_notes(api.rows[0]["notes"], {}) == api.rows[0]["notes"]


@pytest.mark.parametrize("notes", [START + "broken" + END, START + "{}" + END + START, END + START])
async def test_malformed_managed_block_is_readable_but_cannot_be_overwritten(notes):
    service, api, _ = await engine([recipe(notes=notes)])
    read = await call(service, {}, tool="list_recipes")
    assert read["data"][0]["metadata_error"] == "invalid_metadata"
    reply = await call(service, {"recipe_id": 1, "notes": "Zusatz"}, tool="update_recipe")
    assert reply["code"] == "invalid_metadata" and not api.writes


async def test_same_title_refused_but_exact_variants_are_distinct():
    service, api, _ = await engine([recipe()])
    assert (await call(service))["code"] == "recipe_exists" and not api.writes
    assert not (await call(service, {**CREATE, "title": "Curry – Variante ohne Käse"}, key="variant"))[
        "isError"
    ]
    assert len(api.rows) == 2


async def test_provider_recipe_edit_refused():
    service, api, _ = await engine([recipe(source="mealie", provider_account_id=2)])
    reply = await call(service, {"recipe_id": 1, "title": "Neu"}, tool="update_recipe")
    assert reply["code"] == "recipe_read_only" and not api.writes


async def test_concurrent_change_and_revocation_prevent_put():
    service, api, _ = await engine([recipe()])

    def change(api):
        if api.reads == 2:
            api.rows[0]["notes"] = "Anderer Client"

    api.read_hook = change
    assert (await call(service, {"recipe_id": 1, "notes": "Neu"}, tool="update_recipe"))[
        "code"
    ] == "concurrent_change"
    assert not api.writes
    service, api, _ = await engine([recipe()])
    assert (
        await call(service, {"recipe_id": 1, "notes": "Neu"}, tool="update_recipe", authorized=lambda: False)
    )["code"] == "not_allowed"
    assert not api.writes


async def test_recipe_append_persistent_replay_parallel_new_ids_and_changed_state():
    store = MemoryStore()
    service, api, _ = await engine([recipe()], store)
    api.delay = 0.01
    args = {"recipe_id": 1, "notes": "Zusatz"}
    first, second = await asyncio.gather(
        call(service, args, key="a", tool="update_recipe"), call(service, args, key="b", tool="update_recipe")
    )
    assert not first["isError"] and second["replayed"]
    restored = Recipes(api, await make_journal(store))
    assert await call(restored, args, key="a", tool="update_recipe") == first
    assert (await call(restored, args, key="c", tool="update_recipe"))["replayed"]
    assert len(api.writes) == 1 and api.rows[0]["notes"] == "GUI-Notiz behalten\nZusatz"
    api.rows[0]["notes"] = "Fremde Änderung"
    assert (await call(restored, args, key="d", tool="update_recipe"))["code"] == "concurrent_change"
    assert len(api.writes) == 1


@pytest.mark.parametrize("tool", ["create_recipe", "update_recipe"])
async def test_recipe_timeout_restart_and_reconciliation_never_resend(tool):
    store = MemoryStore()
    service, api, journal = await engine([recipe()] if tool == "update_recipe" else [], store)

    def timeout():
        raise ShoppingFailure("execution_unconfirmed", "timeout", uncertain=True)

    api.after = timeout
    args = {"recipe_id": 1, "notes": "Zusatz"} if tool == "update_recipe" else CREATE
    assert (await call(service, args, tool=tool))["code"] == "execution_unconfirmed"
    restored = Recipes(api, await make_journal(store))
    assert (await call(restored, args, key="new", tool=tool))["code"] == "execution_unconfirmed"
    assert "beobachtet" in (await restored.reconcile("request"))["message"]
    assert not (await call(restored, args, tool=tool))["isError"]
    assert len(api.writes) == 1
    # Recipe uncertainty cannot masquerade as a shopping-list barrier.
    shopping = Purchasing(ShoppingFake(), journal)
    assert not shopping.blocked(1)


async def test_uncertain_create_absent_stays_blocked_and_unrelated_reads_work():
    service, api, _ = await engine()
    api.error = ShoppingFailure("execution_unconfirmed", "timeout", uncertain=True)
    assert (await call(service))["isError"]
    with pytest.raises(JournalError):
        await service.reconcile("request")
    assert not (await call(service, {}, tool="list_recipes"))["isError"]
    assert len(api.writes) == 1


async def test_storage_failure_before_and_after_write_never_false_success():
    store = MemoryStore()
    service, api, journal = await engine(store=store)
    store.fail = True
    assert (await call(service))["code"] == "storage_error" and not api.writes
    store = MemoryStore()
    service, api, journal = await engine(store=store)
    api.after = lambda: setattr(store, "fail", True)
    assert (await call(service))["code"] == "execution_unconfirmed"
    assert journal.data["journal"]["request"]["state"] == "prepared" and len(api.writes) == 1


async def test_recipe_opt_in_schema_and_call_time_revoke_without_generic_mcp():
    client = AsyncMock()
    purchasing = Purchasing(None, await make_journal())
    selected = set(DEFAULT_TOOLS)
    runtime = Runtime(client, {}, lambda: selected, purchasing=purchasing)
    assert not ((RECIPE_READS | RECIPE_WRITES) & runtime.enabled())
    args = {}
    reply = await runtime.call("list_recipes", args, call_id="r", scope="s", owner="o")
    assert reply["code"] == "not_allowed"
    api = API([recipe()])
    runtime.recipes = Recipes(api, runtime.journal)
    selected.add("list_recipes")
    assert not (await runtime.call("list_recipes", args, call_id="r", scope="s", owner="o"))["isError"]
    selected.remove("list_recipes")
    assert (await runtime.call("list_recipes", args, call_id="r", scope="s", owner="o"))[
        "code"
    ] == "not_allowed"
    selected.add("create_recipe")
    bad = {**CREATE, "metadata": {**METADATA, "gesundheit": 9}}
    assert (await runtime.call("create_recipe", bad, call_id="w", scope="s", owner="o"))[
        "code"
    ] == "invalid_arguments"
    for name in RECIPE_READS | RECIPE_WRITES:
        schema = probatio.to_openapi(runtime.parameters[name], openapi_version="3.1.0")
        assert schema["additionalProperties"] is False
    client.call_tool.assert_not_called()
    await runtime.close()


async def test_real_recipe_rest_roundtrip_preserves_contract_and_idempotency(monkeypatch):
    monkeypatch.setattr("aioresponses.core.ClientResponse", CompatibleResponse)
    body = {
        "title": "Resten",
        "notes": merged_notes(None, {**CREATE, "ingredients": []}, creating=True),
        "recipe_url": None,
        "meal_types": ["lunch"],
        "ingredients": [],
    }
    saved = recipe(**body)
    with aioresponses() as mock:
        mock.get("http://host/api/v1/recipes", payload={"data": [saved]})
        mock.post("http://host/api/v1/recipes", payload={"data": saved}, status=201)
        mock.put("http://host/api/v1/recipes/1", payload={"data": saved})
        async with aiohttp.ClientSession() as session:
            api = RecipeAPI(MCPClient(session, "http://host/mcp", "token"))
            assert (await api.recipes())[0]["title"] == "Resten"
            assert recipe_snapshot(await api.save(None, body, "stable-key")) == body
            assert recipe_snapshot(await api.save(1, body, "stable-key")) == body
        post = next(v[0] for k, v in mock.requests.items() if k[0] == "POST")
        put = next(v[0] for k, v in mock.requests.items() if k[0] == "PUT")
        assert post.kwargs["headers"]["Idempotency-Key"] == "stable-key"
        assert "Idempotency-Key" not in put.kwargs["headers"]
        assert not post.kwargs["allow_redirects"] and post.kwargs["timeout"].total == 8


@pytest.mark.parametrize(
    "status,uncertain", [(403, False), (404, False), (409, True), (500, True), (302, True)]
)
async def test_recipe_permission_and_network_failures_fail_closed(monkeypatch, status, uncertain):
    monkeypatch.setattr("aioresponses.core.ClientResponse", CompatibleResponse)
    with aioresponses() as mock:
        mock.post("http://host/api/v1/recipes", status=status, body="private")
        async with aiohttp.ClientSession() as session:
            api = RecipeAPI(MCPClient(session, "http://host/mcp", "token"))
            body = recipe_snapshot(recipe())
            with pytest.raises(ShoppingFailure) as caught:
                await api.save(None, body, "key")
            assert caught.value.uncertain == uncertain and "private" not in str(caught.value)


async def test_changed_base_servings_require_explicit_corresponding_ingredients():
    notes = merged_notes(None, CREATE, creating=True)
    service, api, _ = await engine([recipe(notes=notes)])
    args = {"recipe_id": 1, "metadata": {"basisportionen": 6}}
    assert (await call(service, args, tool="update_recipe"))["code"] == "portions_require_ingredients"
    assert not api.writes
    args["ingredients"] = [{**CREATE["ingredients"][0], "quantity": "300 g"}]
    assert not (await call(service, args, key="corrected", tool="update_recipe"))["isError"]
    assert api.rows[0]["ingredients"][0]["quantity"] == "300 g"


async def test_cancelled_recipe_write_leaves_prepared_barrier():
    service, api, journal = await engine()

    async def cancel(*args):
        raise asyncio.CancelledError

    api.save = cancel
    with pytest.raises(asyncio.CancelledError):
        await call(service)
    assert journal.data["journal"]["request"]["state"] == "prepared"
    assert (await call(service, key="retry"))["code"] == "execution_unconfirmed"


async def test_recipe_drain_on_close_prevents_reloaded_owner_overlapping():
    service, api, journal = await engine()
    started, release = asyncio.Event(), asyncio.Event()
    save = api.save

    async def delayed(*args):
        started.set()
        await release.wait()
        return await save(*args)

    api.save = delayed
    task = asyncio.create_task(call(service))
    await started.wait()
    closing = asyncio.create_task(service.close())
    await asyncio.sleep(0)
    assert not closing.done()
    release.set()
    assert not (await task)["isError"]
    await closing
    assert (await call(service, key="next"))["code"] == "not_allowed"
    assert len(api.writes) == 1 and not journal.closed


async def test_file_store_recipe_put_receipt_restores_and_replays(tmp_path):
    import json

    path = tmp_path / "journal.json"

    class FileStore:
        async def async_load(self):
            return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

        async def async_save(self, data):
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    service, api, journal = await engine([recipe()], FileStore())
    args = {"recipe_id": 1, "notes": "Öl und Gemüse"}
    original = await call(service, args, tool="update_recipe")
    restored = Recipes(api, await make_journal(FileStore()))
    assert await call(restored, args, tool="update_recipe") == original
    assert len(api.writes) == 1
    assert restored.journal.data == journal.data


@pytest.mark.parametrize("rows", [[{}], [recipe(), recipe()], [recipe(ingredients=None)], [recipe(notes=42)]])
async def test_partial_recipe_rest_state_is_never_accepted(monkeypatch, rows):
    monkeypatch.setattr("aioresponses.core.ClientResponse", CompatibleResponse)
    with aioresponses() as mock:
        mock.get("http://host/api/v1/recipes", payload={"data": rows})
        async with aiohttp.ClientSession() as session:
            with pytest.raises(ShoppingFailure):
                await RecipeAPI(MCPClient(session, "http://host/mcp", "token")).recipes()


async def test_successful_but_mismatching_recipe_write_reply_is_uncertain(monkeypatch):
    monkeypatch.setattr("aioresponses.core.ClientResponse", CompatibleResponse)
    with aioresponses() as mock:
        mock.put("http://host/api/v1/recipes/1", payload={"data": recipe(ident=2)})
        async with aiohttp.ClientSession() as session:
            with pytest.raises(ShoppingFailure) as error:
                await RecipeAPI(MCPClient(session, "http://host/mcp", "token")).save(
                    1, recipe_snapshot(recipe()), "key"
                )
            assert error.value.uncertain


async def test_real_tcp_recipe_workflow_has_no_shopping_or_meal_writes():
    from aiohttp import web

    rows, requests = [], []

    async def handle(request):
        assert request.headers["Authorization"] == "Bearer local-test-token"
        requests.append((request.method, request.path))
        if request.path == "/api/v1/shopping/categories":
            return web.json_response({"data": CATEGORIES})
        assert request.path.startswith("/api/v1/recipes")
        if request.method == "GET":
            return web.json_response({"data": rows})
        body = await request.json()
        if request.method == "POST":
            assert request.headers["Idempotency-Key"]
            rows.append(recipe(**body))
        elif request.method == "PUT":
            rows[0].update(body)
        else:
            raise AssertionError(request.method)
        return web.json_response({"data": rows[0]}, status=201 if request.method == "POST" else 200)

    app = web.Application()
    app.router.add_route("*", "/{path:.*}", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", 0).start()
    try:
        async with aiohttp.ClientSession() as session:
            client = MCPClient(session, f"http://127.0.0.1:{runner.addresses[0][1]}/mcp", "local-test-token")
            purchasing = Purchasing(None, await make_journal())
            enabled = RECIPE_READS | RECIPE_WRITES
            runtime = Runtime(client, {}, lambda: enabled, purchasing=purchasing)
            try:
                assert not (
                    await runtime.call("create_recipe", CREATE, call_id="a", scope="a", owner="family")
                )["isError"]
                assert not (
                    await runtime.call(
                        "update_recipe",
                        {"recipe_id": 1, "notes": "Für Gäste"},
                        call_id="b",
                        scope="b",
                        owner="family",
                    )
                )["isError"]
                assert not (
                    await runtime.call("get_recipe", {"recipe_id": 1}, call_id="r", scope="r", owner="family")
                )["isError"]
                assert rows[0]["title"] == CREATE["title"] and "Für Gäste" in rows[0]["notes"]
                assert [m for m, p in requests if m != "GET"] == ["POST", "PUT"]
                assert all("/meals" not in p and "/shopping/" not in p or m == "GET" for m, p in requests)
            finally:
                await runtime.close()
    finally:
        await runner.cleanup()


async def test_full_shared_journal_never_evicts_pending_or_recent_receipts():
    from test_journal import record

    from custom_components.yuvomi_mcp.journal import MAX_JOURNAL

    journal = await make_journal()

    def fill(data):
        for number in range(MAX_JOURNAL):
            key = f"shopping-{number}"
            data["journal"][key] = {**record("done"), "id": key}

    await journal.change(fill)
    api = API()
    service = Recipes(api, journal)
    assert (await call(service))["code"] == "storage_error"
    assert not api.writes and len(journal.data["journal"]) == MAX_JOURNAL


async def test_new_health_rating_requires_new_reason_not_reused_previous_reason():
    notes = merged_notes(None, CREATE, creating=True)
    service, api, _ = await engine([recipe(notes=notes)])
    reply = await call(service, {"recipe_id": 1, "metadata": {"gesundheit": 2}}, tool="update_recipe")
    assert reply["code"] == "invalid_metadata" and not api.writes


async def test_zero_cooking_time_is_valid_for_resten_without_scaling():
    service, api, _ = await engine()
    args = {
        **CREATE,
        "title": "Resten",
        "ingredients": [],
        "metadata": {**METADATA, "zubereitungszeit_min": 0},
    }
    assert not (await call(service, args))["isError"]
    assert split_notes(api.rows[0]["notes"])[1]["metadata"]["zubereitungszeit_min"] == 0


@pytest.mark.parametrize("field", ["notes", "recipe_url", "ingredient_quantity"])
async def test_omitted_preserved_recipe_field_rejected_before_put(monkeypatch, field):
    value = recipe()
    if field == "ingredient_quantity":
        del value["ingredients"][0]["quantity"]
    else:
        del value[field]
    monkeypatch.setattr("aioresponses.core.ClientResponse", CompatibleResponse)
    with aioresponses() as mock:
        mock.get("http://host/api/v1/recipes", payload={"data": [value]})
        async with aiohttp.ClientSession() as session:
            service = Recipes(RecipeAPI(MCPClient(session, "http://host/mcp", "token")), await make_journal())
            reply = await call(service, {"recipe_id": 1, "notes": "Neu"}, tool="update_recipe")
            assert reply["code"] == "invalid_response"
            assert all(key[0] == "GET" for key in mock.requests)


async def test_invalid_unicode_recipe_title_is_a_tool_error_without_write():
    service, api, _ = await engine()
    assert (await call(service, {**CREATE, "title": "\ud800"}))["code"] == "invalid_arguments"
    assert not api.writes


async def test_recipe_writes_require_loaded_journal_even_after_opt_in():
    api = API()
    service = Recipes(api, None)
    assert (await call(service))["code"] == "storage_error"
    assert not api.writes
    assert not (await call(service, {}, tool="list_recipes"))["isError"]


@pytest.mark.parametrize("resource", [None, "shopping"])
async def test_put_journal_permission_is_not_extended_to_shopping(resource):
    from test_journal import record

    journal = await make_journal()
    value = record("prepared", method="PUT")
    if resource is not None:
        value["resource"] = resource
    with pytest.raises(JournalError):
        await journal.change(lambda data: data["journal"].update(key=value))
    assert not journal.data["journal"]
