"""Fixed REST adapter and actual TCP integration with the runtime."""

from unittest.mock import AsyncMock

import aiohttp
import pytest
from aiohttp import web
from test_client import CompatibleResponse, aioresponses
from test_journal import make_journal
from test_purchasing import CATEGORIES, row

from custom_components.yuvomi_mcp.client import MCPClient, RemoteTool
from custom_components.yuvomi_mcp.purchasing import Purchasing
from custom_components.yuvomi_mcp.runtime import Runtime
from custom_components.yuvomi_mcp.shopping_api import ShoppingAPI, ShoppingFailure


@pytest.fixture(autouse=True)
def compat(monkeypatch):
    monkeypatch.setattr("aioresponses.core.ClientResponse", CompatibleResponse)


@pytest.mark.parametrize(
    "status,uncertain",
    [
        (400, False),
        (401, False),
        (403, False),
        (404, False),
        (409, True),
        (408, True),
        (500, True),
        (302, True),
    ],
)
async def test_write_errors_are_sanitized_and_ambiguity_is_classified(status, uncertain):
    with aioresponses() as mock:
        mock.post("http://host/api/v1/shopping/1/items", status=status, body="private response")
        async with aiohttp.ClientSession() as session:
            api = ShoppingAPI(MCPClient(session, "http://host/mcp", "secret-token"))
            with pytest.raises(ShoppingFailure) as caught:
                await api.create(1, {"name": "Tee", "quantity": None, "category": "Getränke"}, "stable-key")
            assert caught.value.uncertain is uncertain
            assert "private" not in str(caught.value)
            request = next(iter(mock.requests.values()))[0]
            assert request.kwargs["headers"]["Authorization"] == "Bearer secret-token"
            assert request.kwargs["headers"]["Idempotency-Key"] == "stable-key"
            assert request.kwargs["allow_redirects"] is False
            assert request.kwargs["timeout"].total == 8


@pytest.mark.parametrize(
    "data",
    [
        {"data": None},
        {"data": [row(list_id=2)]},
        {"data": [row(), row()]},
        {"data": [{"id": 1, "name": "X"}]},
    ],
)
async def test_incomplete_or_wrong_list_items_fail_closed(data):
    with aioresponses() as mock:
        mock.get("http://host/api/v1/shopping/1/items", payload=data)
        async with aiohttp.ClientSession() as session:
            with pytest.raises(ShoppingFailure):
                await ShoppingAPI(MCPClient(session, "http://host/mcp", "token")).items(1)


async def test_create_and_patch_do_not_allow_generic_fields_or_invalid_ids():
    async with aiohttp.ClientSession() as session:
        api = ShoppingAPI(MCPClient(session, "http://host/mcp", "token"))
        with pytest.raises(ShoppingFailure):
            await api.update(1, 1, {"url": "http://evil.example"})
        with pytest.raises(ShoppingFailure):
            await api.create(1, {"name": "X", "is_checked": True}, "key")
        with pytest.raises(ShoppingFailure):
            await api.items("../../admin")


async def test_successful_but_mismatched_patch_reply_is_uncertain():
    with aioresponses() as mock:
        mock.patch("http://host/api/v1/shopping/items/1", payload={"data": row(ident=2, checked=0)})
        async with aiohttp.ClientSession() as session:
            api = ShoppingAPI(MCPClient(session, "http://host/mcp", "token"))
            with pytest.raises(ShoppingFailure) as caught:
                await api.update(1, 1, {"is_checked": False})
            assert caught.value.uncertain


async def test_real_tcp_runtime_uses_rest_for_shopping_and_mcp_for_tasks():
    rows, requests = [], []

    async def handle(request):
        assert request.headers["Authorization"] == "Bearer local-test-token"
        requests.append((request.method, request.path))
        if request.path == "/mcp":
            message = await request.json()
            assert message["params"]["name"] == "create_task"
            return web.json_response(
                {
                    "jsonrpc": "2.0",
                    "id": message["id"],
                    "result": {"isError": False, "content": [{"type": "text", "text": "Task saved"}]},
                }
            )
        if request.path.endswith("categories"):
            return web.json_response({"data": CATEGORIES})
        if request.path == "/api/v1/shopping":
            return web.json_response({"data": [{"id": 1, "name": "Familie"}]})
        if request.method == "GET":
            return web.json_response({"data": rows, "version": len(requests)})
        body = await request.json()
        if request.method == "POST":
            assert request.headers.get("Idempotency-Key")
            item = row(
                body["name"], ident=len(rows) + 1, quantity=body["quantity"], category=body["category"]
            )
            rows.append(item)
        else:
            item = rows[0]
            item.update(body)
        return web.json_response({"data": item}, status=201 if request.method == "POST" else 200)

    app = web.Application()
    app.router.add_route("*", "/{path:.*}", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", 0).start()
    try:
        async with aiohttp.ClientSession() as session:
            client = MCPClient(session, f"http://127.0.0.1:{runner.addresses[0][1]}/mcp", "local-test-token")
            engine = Purchasing(ShoppingAPI(client), await make_journal())
            schema = {
                "type": "object",
                "properties": {k: {"type": "string"} for k in ("name", "quantity", "category", "list")},
                "required": ["name"],
                "additionalProperties": False,
            }
            runtime = Runtime(
                client,
                {
                    "add_shopping_item": RemoteTool("add_shopping_item", "Add", schema),
                    "create_task": RemoteTool("create_task", "Task", {"type": "object"}),
                },
                lambda: {"add_shopping_item", "create_task"},
                purchasing=engine,
            )
            try:

                async def add(scope):
                    return await runtime.call(
                        "add_shopping_item",
                        {"name": "Äpfeltee", "category": "Getr_nke"},
                        call_id=scope,
                        scope=scope,
                        owner="router-user-device",
                    )

                assert (await add("first"))["items"][0]["status"] == "created"
                assert (await add("new-alexa-turn"))["items"][0]["replayed"]
                rows[0].update(is_checked=1, quantity="99 l")
                assert (await add("third"))["items"][0]["status"] == "reactivated"
                assert len(rows) == 1 and rows[0]["quantity"] == "1"
                rows[0]["quantity"] = "1 Packung"
                args = {"name": "Äpfeltee", "quantity": "2 Packungen"}
                added = await runtime.call("add_shopping_item", args, call_id="q", scope="q", owner="u")
                assert added["items"][0]["old_quantity"] == "1 Packung"
                assert added["items"][0]["new_quantity"] == "3 Packungen"
                assert added["items"][0]["action"] == "increased"
                retry = await runtime.call(
                    "add_shopping_item", args, call_id="retry", scope="retry", owner="u"
                )
                assert retry["items"][0]["replayed"] and rows[0]["quantity"] == "3 Packungen"
                replaced = await runtime.call(
                    "add_shopping_item", {**args, "quantity": "2 Tuben"}, call_id="r", scope="r", owner="u"
                )
                assert replaced["items"][0]["action"] == "replaced" and rows[0]["quantity"] == "2 Tuben"
                task = await runtime.call("create_task", {"name": "Test"}, call_id="t", scope="t", owner="u")
                assert not task["isError"]
                assert sum(method == "POST" and path != "/mcp" for method, path in requests) == 1
                assert sum(path == "/mcp" for _, path in requests) == 1
            finally:
                await runtime.close()
    finally:
        await runner.cleanup()


async def test_runtime_bulk_opt_in_and_missing_storage_never_fall_back_to_mcp():
    client = AsyncMock(spec=MCPClient)
    selected = {"add_shopping_item"}
    engine = Purchasing(None, None)
    runtime = Runtime(
        client,
        {"add_shopping_item": RemoteTool("add_shopping_item", "Add", {"type": "object"})},
        lambda: selected,
        purchasing=engine,
    )
    try:
        result = await runtime.call(
            "add_shopping_items", {"items": [{"name": "X"}]}, call_id="1", scope="1", owner="u"
        )
        assert result["code"] == "not_allowed"
        result = await runtime.call("add_shopping_item", {"name": "X"}, call_id="2", scope="2", owner="u")
        assert result["isError"]
        client.call_tool.assert_not_called()
    finally:
        await runtime.close()


@pytest.mark.parametrize(
    "supplied,expected",
    [
        ("Getr_nke", "Getränke"),
        ("Obst und Gemuese", "Obst & Gemüse"),
        ("Suesses & Backzutaten", "Süsses und Backzutaten"),
        (None, None),
        ("invented", None),
    ],
)
async def test_tcp_bulk_category_followup_unicode_and_no_mcp_write(supplied, expected):
    from custom_components.yuvomi_mcp.shopping import BULK

    posted, rows = [], []
    categories = CATEGORIES + [{"id": 4, "name": "Süsses und Backzutaten"}]

    async def handle(request):
        assert request.headers["Authorization"] == "Bearer local-test-token"
        assert request.path != "/mcp"
        if request.path.endswith("categories"):
            return web.json_response({"data": categories})
        if request.path == "/api/v1/shopping":
            return web.json_response({"data": [{"id": 1, "name": "Familie"}]})
        if request.method == "GET":
            return web.json_response({"data": rows})
        assert request.method == "POST" and request.headers["Idempotency-Key"]
        body = await request.json()
        assert body["name"] == "Äpfel und süsser Tee" and body["quantity"] == "2 Stück"
        posted.append(body)
        item = row(body["name"], category=body["category"], quantity=body["quantity"])
        rows.append(item)
        return web.json_response({"data": item}, status=201)

    app = web.Application()
    app.router.add_route("*", "/{path:.*}", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", 0).start()
    try:
        async with aiohttp.ClientSession() as session:
            client = MCPClient(session, f"http://127.0.0.1:{runner.addresses[0][1]}/mcp", "local-test-token")
            engine = Purchasing(ShoppingAPI(client), await make_journal())
            runtime = Runtime(client, {}, lambda: {BULK}, purchasing=engine)
            try:
                item = {"name": "Äpfel und süsser Tee", "quantity": "2 Stück"}
                if supplied is not None:
                    item["category"] = supplied
                result = await runtime.call(BULK, {"items": [item]}, call_id="c", scope="s", owner="u")
                if expected is not None:
                    assert not result["isError"] and posted[0]["category"] == expected
                else:
                    assert result["code"] == ("category_required" if supplied is None else "invalid_category")
                    assert not posted
                    item["category"] = "Getränke"
                    fixed = await runtime.call(BULK, {"items": [item]}, call_id="c", scope="s", owner="u")
                    assert not fixed["isError"] and len(posted) == 1
            finally:
                await runtime.close()
    finally:
        await runner.cleanup()


@pytest.mark.parametrize("name", ["add_shopping_item", "add_shopping_items"])
async def test_missing_engine_never_uses_legacy_mcp_fallback(name):
    client = AsyncMock(spec=MCPClient)
    runtime = Runtime(
        client,
        {"add_shopping_item": RemoteTool("add_shopping_item", "Add", {"type": "object"})},
        lambda: {name},
    )
    try:
        args = {"items": [{"name": "New"}]} if name.endswith("items") else {"name": "New"}
        result = await runtime.call(name, args, call_id="c", scope="s", owner="u")
        assert result["code"] == "storage_unavailable"
        client.call_tool.assert_not_called()
    finally:
        await runtime.close()


def test_model_visible_single_and_bulk_schemas_share_described_parameters():
    import probatio

    engine = Purchasing(None, None)
    runtime = Runtime(AsyncMock(), {}, lambda: set(), purchasing=engine)
    single = probatio.to_openapi(runtime.parameters["add_shopping_item"], openapi_version="3.1.0")
    bulk = probatio.to_openapi(runtime.parameters["add_shopping_items"], openapi_version="3.1.0")
    item = bulk["properties"]["items"]["items"]
    assert item["properties"] == {k: v for k, v in single["properties"].items() if k != "list"}
    assert item["required"] == single["required"] == ["name"]
    assert "NEW" in item["properties"]["category"]["description"]
    assert "free text" in item["properties"]["quantity"]["description"].lower()
    assert item["properties"]["operation"]["enum"] == ["ensure", "set", "increase"]


@pytest.mark.parametrize("quantity", ["1 Flasche", "2 Tuben", "1 Packung", " 2 Tuben "])
@pytest.mark.parametrize("method", ["POST", "PATCH"])
async def test_free_text_quantity_reaches_rest_json_verbatim(method, quantity):
    url = "http://host/api/v1/shopping/1/items" if method == "POST" else "http://host/api/v1/shopping/items/1"
    body = (
        {"name": "Mayonnaise", "category": "Sonstiges", "quantity": quantity}
        if method == "POST"
        else {"quantity": quantity}
    )
    with aioresponses() as mock:
        mock.add(
            url, method=method, payload={"data": row("Mayonnaise", category="Sonstiges", quantity=quantity)}
        )
        async with aiohttp.ClientSession() as session:
            api = ShoppingAPI(MCPClient(session, "http://host/mcp", "token"))
            result = (
                await api.create(1, body, "stable-key") if method == "POST" else await api.update(1, 1, body)
            )
            request = next(iter(mock.requests.values()))[0]
            assert request.kwargs["json"] == body
            assert result["quantity"] == quantity
