"""Shopping notes share quantity serialization/journal without triggering additions."""

import asyncio
from copy import deepcopy

import aiohttp
import pytest
from test_client import CompatibleResponse, aioresponses
from test_journal import MemoryStore, make_journal
from test_purchasing import row, run, setup

from custom_components.yuvomi_mcp.client import MCPClient
from custom_components.yuvomi_mcp.notes import edit_note
from custom_components.yuvomi_mcp.purchasing import Purchasing
from custom_components.yuvomi_mcp.shopping_api import ShoppingAPI, ShoppingFailure


@pytest.mark.parametrize("checked", [0, 1])
@pytest.mark.parametrize(
    "mode,note,expected",
    [
        ("append", "Öl\nextra", "Keep\nÖl\nextra"),
        ("replace", "Süss & scharf", "Süss & scharf"),
        ("clear", None, None),
    ],
)
async def test_pure_note_edit_preserves_quantity_category_and_status(checked, mode, note, expected):
    engine, api, _ = await setup([row(quantity="3 Packungen", checked=checked)])
    args = {"name": "Tee", "operation": "note", "note_mode": mode}
    if note is not None:
        args["note"] = note
    reply = await run(engine, args)
    assert not reply["isError"]
    assert api.writes == [("PATCH", {"notes": expected}, 1)]
    assert api.rows[0]["quantity"] == "3 Packungen"
    assert api.rows[0]["category"] == "Getränke" and api.rows[0]["is_checked"] == checked
    assert reply["items"][0]["action"] == "note_updated"
    assert reply["items"][0]["note"] == expected


@pytest.mark.parametrize("checked", [0, 1])
async def test_note_append_retries_with_new_ids_and_restart_never_duplicate(checked):
    store = MemoryStore()
    engine, api, _ = await setup([row(quantity="2 Tuben", checked=checked)], store=store)
    args = {"name": "Tee", "operation": "note", "note": "Ohne Zucker"}
    original = await run(engine, args, key="first")
    restored = Purchasing(api, await make_journal(store))
    assert await run(restored, args, key="first") == original
    retry = await run(restored, args, key="new-id")
    assert retry["items"][0]["replayed"]
    assert len(api.writes) == 1 and api.rows[0]["notes"] == "Keep\nOhne Zucker"
    assert api.rows[0]["quantity"] == "2 Tuben"


async def test_note_plus_quantity_has_distinct_intent_and_preserves_category():
    engine, api, _ = await setup([row(quantity="1")])
    args = {"name": "Tee", "quantity": "2", "note": "Bio", "category": "invalid"}
    first = await run(engine, args, key="1")
    retry = await run(engine, args, key="2")
    assert not first["isError"] and retry["items"][0]["replayed"]
    assert len(api.writes) == 1
    assert api.rows[0]["quantity"] == "3" and api.rows[0]["notes"] == "Keep\nBio"


@pytest.mark.parametrize(
    "args",
    [
        {"name": "Neu", "operation": "note", "note": "X"},
        {"name": "Tee", "operation": "note", "quantity": "2", "note": "X"},
        {"name": "Tee", "operation": "note"},
        {"name": "Tee", "note": ""},
        {"name": "Tee", "note_mode": "replace"},
        {"name": "Tee", "note_mode": "clear", "note": "X"},
        {"name": "Tee", "note": "\x00"},
        {"name": "Tee", "note": "x" * 5001},
    ],
)
async def test_invalid_notes_fail_before_quantity_or_any_write(args):
    engine, api, _ = await setup([row(quantity="5")])
    assert (await run(engine, args))["isError"]
    assert not api.writes and api.rows[0]["quantity"] == "5"


async def test_bulk_note_and_quantity_use_shared_preflight_and_lock():
    engine, api, _ = await setup([row(), row("Kaffee", ident=2, quantity="1")])
    reply = await run(
        engine,
        {"items": [{"name": "Tee", "operation": "note", "note": "Bio"}, {"name": "Kaffee", "quantity": "2"}]},
        bulk=True,
    )
    assert not reply["isError"] and api.rows[0]["quantity"] is None
    assert api.rows[0]["notes"] == "Keep\nBio" and api.rows[1]["quantity"] == "3"
    args = {"name": "Tee", "operation": "note", "note": "Zitrone"}
    first, second = await asyncio.gather(run(engine, args, key="a"), run(engine, args, key="b"))
    assert not first["isError"] and not second["isError"]
    assert api.rows[0]["notes"].count("Zitrone") == 1


async def test_concurrent_note_change_is_not_overwritten():
    engine, api, _ = await setup([row(quantity="1")])
    items = api.items

    async def changing(list_id):
        if api.reads == 1:
            api.rows[0]["notes"] = "Weboberfläche"
        return await items(list_id)

    api.items = changing
    reply = await run(engine, {"name": "Tee", "operation": "note", "note": "Bio"})
    assert reply["code"] == "concurrent_change" and not api.writes


async def test_note_timeout_restores_barrier_and_read_only_reconciliation():
    store = MemoryStore()
    engine, api, journal = await setup([row(quantity="4")], store=store)

    async def timeout():
        raise ShoppingFailure("execution_unconfirmed", "timeout", uncertain=True)

    api.after_write = timeout
    args = {"name": "Tee", "operation": "note", "note": "Bio"}
    assert (await run(engine, args))["code"] == "execution_unconfirmed"
    engine = Purchasing(api, await make_journal(store))
    assert (await run(engine, args, key="retry"))["code"] == "execution_unconfirmed"
    assert (await engine.reconcile(next(iter(journal.data["journal"]))))["status"] == "state_observed"
    assert len(api.writes) == 1 and api.rows[0]["quantity"] == "4"


async def test_create_and_reactivation_forward_note_through_real_rest_adapter(monkeypatch):
    monkeypatch.setattr("aioresponses.core.ClientResponse", CompatibleResponse)
    with aioresponses() as mock:
        created = {**row(quantity="1"), "notes": "Für Gäste"}
        mock.post("http://host/api/v1/shopping/1/items", payload={"data": created}, status=201)
        mock.patch("http://host/api/v1/shopping/items/1", payload={"data": created})
        async with aiohttp.ClientSession() as session:
            api = ShoppingAPI(MCPClient(session, "http://host/mcp", "token"))
            body = {"name": "Tee", "quantity": "1", "category": "Getränke", "notes": "Für Gäste"}
            assert (await api.create(1, body, "key"))["notes"] == "Für Gäste"
            assert (await api.update(1, 1, {"notes": "Für Gäste"}))["notes"] == "Für Gäste"
            assert next(iter(mock.requests.values()))[0].kwargs["json"] == body


async def test_create_plan_and_reactivate_notes_preserve_default_or_append():
    engine, api, _ = await setup()
    plan = await engine.plan(
        {"name": "Tee", "category": "Getränke", "note": "Für Gäste"}, [], await api.categories()
    )
    assert plan["body"]["notes"] == "Für Gäste"
    engine, api, _ = await setup([row(checked=1, quantity="99")])
    assert not (await run(engine, {"name": "Tee", "note": "Bio"}))["isError"]
    assert api.rows[0]["notes"] == "Keep\nBio" and api.rows[0]["quantity"] == "1"
    before = deepcopy(api.rows[0])
    assert edit_note(before["notes"], {}) == before["notes"]


@pytest.mark.parametrize("operation", ["ensure", "set"])
async def test_note_with_quantity_retry_never_appends_twice(operation):
    engine, api, _ = await setup([row(quantity="1")])
    args = {"name": "Tee", "quantity": "2", "operation": operation, "note": "Bio"}
    assert not (await run(engine, args, key="a"))["isError"]
    assert (await run(engine, args, key="b"))["items"][0]["replayed"]
    assert len(api.writes) == 1 and api.rows[0]["notes"] == "Keep\nBio"


@pytest.mark.parametrize("value", ["\ud800", "😀" * 2501])
def test_invalid_unicode_or_utf16_overflow_note_is_rejected(value):
    with pytest.raises(ShoppingFailure):
        edit_note(None, {"note": value})


def test_multiline_note_crlf_and_umlauts_are_preserved():
    assert edit_note(None, {"note": "Für Gäste\r\nSüss & scharf"}) == "Für Gäste\r\nSüss & scharf"


async def test_missing_current_shopping_notes_fail_closed(monkeypatch):
    monkeypatch.setattr("aioresponses.core.ClientResponse", CompatibleResponse)
    current = row(quantity="2")
    del current["notes"]
    with aioresponses() as mock:
        mock.get("http://host/api/v1/shopping/1/items", payload={"data": [current]})
        async with aiohttp.ClientSession() as session:
            api = ShoppingAPI(MCPClient(session, "http://host/mcp", "token"))
            with pytest.raises(ShoppingFailure):
                await api.items(1)
            assert all(key[0] == "GET" for key in mock.requests)
