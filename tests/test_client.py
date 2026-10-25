import asyncio
import json
from unittest.mock import Mock
from urllib.parse import urlencode

import aiohttp
import pytest
from aioresponses import CallbackResult
from aioresponses import aioresponses as BaseResponses

from custom_components.yuvomi_mcp.client import (
    AuthenticationError,
    ConnectionError,
    MCPClient,
    MCPError,
    RPCError,
    ShoppingReadError,
    normalize_url,
)

URL = "http://yuvomi.example:3015/mcp"
TOKEN = "test-secret-token"


class CompatibleResponse(aiohttp.ClientResponse):
    """aioresponses 0.7.9 lacks aiohttp 3.14's new constructor argument."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("stream_writer", Mock(output_size=0))
        super().__init__(*args, **kwargs)


class aioresponses(BaseResponses):
    def add(self, *args, **kwargs):
        kwargs.setdefault("response_class", CompatibleResponse)
        return super().add(*args, **kwargs)


@pytest.fixture(autouse=True)
def aiohttp_314_test_compat(monkeypatch):
    monkeypatch.setattr("aioresponses.core.ClientResponse", CompatibleResponse)


def reply(result=None, error=None, *, sse=False):
    def callback(url, **kwargs):
        request = kwargs["json"]
        data = {"jsonrpc": "2.0", "id": request["id"]}
        data.update({"error": error} if error else {"result": result})
        if sse:
            return CallbackResult(
                body="event: message\ndata: " + json.dumps(data) + "\n\n", content_type="text/event-stream"
            )
        return CallbackResult(payload=data)

    return callback


@pytest.mark.parametrize(
    "value",
    [
        "ftp://host/mcp",
        "http://user:password@host/mcp",
        "http://host/api",
        "http://host/mcp?token=abc",
        "http://host/mcp#x",
        "http://host:bad/mcp",
        "http://host:0/mcp",
        "http://ho st/mcp",
        "http://host\\evil/mcp",
    ],
)
def test_invalid_url(value):
    with pytest.raises(ValueError):
        normalize_url(value)


def test_url_normalization():
    assert normalize_url("HTTP://HOST:3015/mcp/") == "http://host:3015/mcp"


@pytest.mark.parametrize("version", ["2025-06-18", "2025-03-26", "2024-11-05"])
async def test_negotiate_headers_and_discover(version):
    with aioresponses() as mock:
        mock.post(URL, callback=reply({"protocolVersion": version, "capabilities": {"tools": {}}}))
        mock.post(URL, status=202)
        mock.post(
            URL,
            callback=reply(
                {
                    "tools": [
                        {
                            "name": "list_tasks",
                            "description": "Tasks",
                            "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer"}}},
                        }
                    ]
                }
            ),
        )
        async with aiohttp.ClientSession() as session:
            client = MCPClient(session, URL, TOKEN)
            await client.initialize()
            tools = await client.list_tools()
        assert client.protocol == version
        assert tools["list_tasks"].schema["properties"]["limit"] == {"type": "integer"}
        requests = next(iter(mock.requests.values()))
        assert [r.kwargs["json"]["method"] for r in requests] == [
            "initialize",
            "notifications/initialized",
            "tools/list",
        ]
        assert requests[2].kwargs["headers"]["MCP-Protocol-Version"] == version
        assert requests[0].kwargs["headers"]["Authorization"] == "Bearer " + TOKEN
        assert requests[0].kwargs["allow_redirects"] is False


async def test_initialize_fallback_and_unsupported_version():
    with aioresponses() as mock:
        mock.post(URL, callback=reply(error={"code": -32602, "message": TOKEN}))
        mock.post(URL, callback=reply({"protocolVersion": "2025-03-26", "capabilities": {"tools": {}}}))
        mock.post(
            URL,
            callback=lambda u, **k: CallbackResult(
                payload={"jsonrpc": "2.0", "id": None, "error": {"code": -32601, "message": "not supported"}}
            ),
        )
        async with aiohttp.ClientSession() as session:
            client = MCPClient(session, URL, TOKEN)
            await client.initialize()
        assert client.protocol == "2025-03-26"
    with aioresponses() as mock:
        mock.post(URL, callback=reply({"protocolVersion": "2099-01-01", "capabilities": {"tools": {}}}))
        async with aiohttp.ClientSession() as session:
            with pytest.raises(MCPError):
                await MCPClient(session, URL, TOKEN).initialize()


@pytest.mark.parametrize("status", [401, 403, 302, 405, 500])
async def test_http_errors_are_sanitized_and_never_retried(status):
    with aioresponses() as mock:
        mock.post(URL, status=status, body=TOKEN, headers={"Location": "http://evil.example/mcp"})
        async with aiohttp.ClientSession() as session:
            with pytest.raises(AuthenticationError if status in {401, 403} else ConnectionError) as error:
                await MCPClient(session, URL, TOKEN).call_tool("create_task", {"name": "x"})
        assert TOKEN not in str(error.value)
        assert sum(len(v) for v in mock.requests.values()) == 1


@pytest.mark.parametrize("error", [asyncio.TimeoutError(), aiohttp.ClientConnectionError(TOKEN)])
async def test_network_errors(error):
    with aioresponses() as mock:
        mock.post(URL, exception=error)
        async with aiohttp.ClientSession() as session:
            with pytest.raises(ConnectionError) as caught:
                await MCPClient(session, URL, TOKEN).call_tool("create_task", {})
        assert TOKEN not in str(caught.value)


@pytest.mark.parametrize("sse", [False, True])
async def test_tool_result_and_redaction(sse):
    with aioresponses() as mock:
        mock.post(
            URL,
            callback=reply(
                {"content": [{"type": "text", "text": "Saved " + TOKEN}], "isError": False}, sse=sse
            ),
        )
        async with aiohttp.ClientSession() as session:
            result = await MCPClient(session, URL, TOKEN).call_tool("add_shopping_item", {"name": "Milch"})
        assert result == {"isError": False, "content": [{"type": "text", "text": "Saved [REDACTED]"}]}


async def test_remote_tool_error_is_not_success():
    with aioresponses() as mock:
        mock.post(URL, callback=reply({"content": [{"type": "text", "text": TOKEN}], "isError": True}))
        async with aiohttp.ClientSession() as session:
            result = await MCPClient(session, URL, TOKEN).call_tool("create_event", {})
        assert result["isError"]
        assert TOKEN not in str(result)


async def test_rpc_error_is_sanitized():
    with aioresponses() as mock:
        mock.post(URL, callback=reply(error={"code": -32602, "message": TOKEN, "data": {"token": TOKEN}}))
        async with aiohttp.ClientSession() as session:
            with pytest.raises(RPCError) as caught:
                await MCPClient(session, URL, TOKEN).call_tool("list_tasks", {})
        assert TOKEN not in str(caught.value)


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"jsonrpc": "2.0", "id": "wrong", "result": {}},
        {"jsonrpc": "1.0", "result": {}},
        {"jsonrpc": "2.0", "error": "bad"},
    ],
)
async def test_malformed_envelopes(payload):
    with aioresponses() as mock:
        mock.post(URL, payload=payload)
        async with aiohttp.ClientSession() as session:
            with pytest.raises(MCPError):
                await MCPClient(session, URL, TOKEN).call_tool("list_tasks", {})


@pytest.mark.parametrize(
    "result",
    [
        {},
        {"content": "bad"},
        {"content": [], "isError": "false"},
        {"content": [{"type": "image", "data": "x"}]},
    ],
)
async def test_malformed_call_results(result):
    with aioresponses() as mock:
        mock.post(URL, callback=reply(result))
        async with aiohttp.ClientSession() as session:
            with pytest.raises(MCPError):
                await MCPClient(session, URL, TOKEN).call_tool("list_tasks", {})


async def test_paginated_tools_and_cursor_loop():
    tool = {"name": "list_tasks", "inputSchema": {"type": "object"}}
    with aioresponses() as mock:
        mock.post(URL, callback=reply({"tools": [tool], "nextCursor": "next"}))
        mock.post(URL, callback=reply({"tools": []}))
        async with aiohttp.ClientSession() as session:
            assert len(await MCPClient(session, URL, TOKEN).list_tools()) == 1
    with aioresponses() as mock:
        mock.post(URL, callback=reply({"tools": [], "nextCursor": "next"}), repeat=True)
        async with aiohttp.ClientSession() as session:
            with pytest.raises(MCPError):
                await MCPClient(session, URL, TOKEN).list_tools()


@pytest.mark.parametrize(
    "tool",
    [
        {"name": "list_tasks", "inputSchema": []},
        {"name": "invalid.name", "inputSchema": {"type": "object"}},
        {"name": "list_tasks", "inputSchema": {"type": "array"}},
    ],
)
async def test_invalid_tool_metadata(tool):
    with aioresponses() as mock:
        mock.post(URL, callback=reply({"tools": [tool]}))
        async with aiohttp.ClientSession() as session:
            with pytest.raises(MCPError):
                await MCPClient(session, URL, TOKEN).list_tools()


@pytest.mark.parametrize("status", [200, 400])
async def test_yuvomi_initialized_method_not_found_compatibility(status):
    with aioresponses() as mock:
        mock.post(URL, callback=reply({"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}}))
        mock.post(
            URL,
            status=status,
            payload={"jsonrpc": "2.0", "id": None, "error": {"code": -32601, "message": TOKEN}},
        )
        async with aiohttp.ClientSession() as session:
            client = MCPClient(session, URL, TOKEN)
            await client.initialize()
            assert client.protocol == "2025-06-18"


async def test_stateful_server_is_explicitly_rejected():
    with aioresponses() as mock:
        mock.post(URL, headers={"Mcp-Session-Id": "session"}, payload={})
        async with aiohttp.ClientSession() as session:
            with pytest.raises(MCPError, match="zustandslosen"):
                await MCPClient(session, URL, TOKEN).initialize()


async def test_rest_categories_derived_origin_shared_token_complete_order_and_timeout():
    endpoint = "https://other.example:8443/api/v1/shopping/categories"
    categories = [{"id": i, "name": f"Kategorie {i}", "sort_order": 300 - i} for i in range(300)]
    with aioresponses() as mock:
        mock.get(endpoint, payload={"data": categories})
        async with aiohttp.ClientSession() as session:
            client = MCPClient(session, "https://other.example:8443/mcp", TOKEN)
            client.protocol = "2025-06-18"
            result = await client.get_shopping_categories()
        assert result == [{"name": row["name"]} for row in categories]
        request = next(iter(mock.requests.values()))[0]
        assert request.kwargs["headers"]["Authorization"] == "Bearer " + TOKEN
        assert "MCP-Protocol-Version" not in request.kwargs["headers"]
        assert request.kwargs["allow_redirects"] is False
        assert request.kwargs["timeout"].total == 5


async def test_rest_suggestions_query_is_a_parameter_and_result_has_no_extra_fields():
    query = "Milch & Käse / ? http://evil.example"
    endpoint = "http://other.example:3015/api/v1/shopping/suggestions?" + urlencode({"q": query})
    with aioresponses() as mock:
        mock.get(
            endpoint,
            payload={
                "data": [{"name": "Käse", "category": "Milchprodukte", "quantity": "100 g", "ignored": "x"}]
            },
        )
        async with aiohttp.ClientSession() as session:
            result = await MCPClient(
                session, "http://other.example:3015/mcp", TOKEN
            ).get_shopping_suggestions(query)
        assert result == [{"name": "Käse", "category": "Milchprodukte", "quantity": "100 g"}]
        request = next(iter(mock.requests.values()))[0]
        assert request.kwargs["params"] == {"q": query}
        assert request.kwargs["headers"]["Authorization"] == "Bearer " + TOKEN


@pytest.mark.parametrize("status", [401, 403, 302, 404, 500])
async def test_rest_http_errors_are_sanitized_without_redirects_or_retries(status):
    endpoint = "http://yuvomi.example:3015/api/v1/shopping/categories"
    with aioresponses() as mock:
        mock.get(endpoint, status=status, body=TOKEN, headers={"Location": "http://evil.example"})
        async with aiohttp.ClientSession() as session:
            with pytest.raises(ShoppingReadError) as error:
                await MCPClient(session, URL, TOKEN).get_shopping_categories()
        assert TOKEN not in str(error.value)
        assert sum(len(v) for v in mock.requests.values()) == 1


@pytest.mark.parametrize("error", [TimeoutError(), aiohttp.ClientConnectionError(TOKEN)])
async def test_rest_timeouts_and_network_errors_are_sanitized(error):
    with aioresponses() as mock:
        mock.get("http://yuvomi.example:3015/api/v1/shopping/categories", exception=error)
        async with aiohttp.ClientSession() as session:
            with pytest.raises(ShoppingReadError) as caught:
                await MCPClient(session, URL, TOKEN).get_shopping_categories()
        assert TOKEN not in str(caught.value)


@pytest.mark.parametrize(
    "payload", [{}, [], {"data": {}}, {"data": [None]}, {"data": [{"name": ""}]}, {"data": [{"name": 3}]}]
)
async def test_rest_categories_bad_envelope_or_rows(payload):
    with aioresponses() as mock:
        mock.get("http://yuvomi.example:3015/api/v1/shopping/categories", payload=payload)
        async with aiohttp.ClientSession() as session:
            with pytest.raises(ShoppingReadError):
                await MCPClient(session, URL, TOKEN).get_shopping_categories()


@pytest.mark.parametrize(
    "row",
    [
        {"name": "x", "category": 3},
        {"name": "x", "quantity": {}},
        {"name": "x", "quantity": True},
        {"name": "x", "quantity": float("inf")},
    ],
)
async def test_rest_suggestions_bad_rows(row):
    with aioresponses() as mock:
        mock.get("http://yuvomi.example:3015/api/v1/shopping/suggestions?q=x", payload={"data": [row]})
        async with aiohttp.ClientSession() as session:
            with pytest.raises(ShoppingReadError):
                await MCPClient(session, URL, TOKEN).get_shopping_suggestions("x")


async def test_rest_response_size_limit(monkeypatch):
    from custom_components.yuvomi_mcp import client as module

    monkeypatch.setattr(module, "MAX_RESPONSE", 32)
    with aioresponses() as mock:
        mock.get("http://yuvomi.example:3015/api/v1/shopping/categories", body="x" * 33)
        async with aiohttp.ClientSession() as session:
            with pytest.raises(ShoppingReadError):
                await MCPClient(session, URL, TOKEN).get_shopping_categories()


async def test_rest_rejects_unapproved_endpoint_before_network():
    async with aiohttp.ClientSession() as session:
        with pytest.raises(ShoppingReadError):
            await MCPClient(session, URL, TOKEN)._shopping_get("https://evil.example")
