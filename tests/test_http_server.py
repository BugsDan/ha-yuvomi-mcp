"""Exercise the real aiohttp transport against an isolated TCP MCP server."""

import aiohttp
import pytest
from aiohttp import web

from custom_components.yuvomi_mcp.client import MCPClient, MCPError
from custom_components.yuvomi_mcp.runtime import Runtime


@pytest.mark.parametrize("sse", [False, True])
async def test_real_transport_end_to_end(sse):
    received = []

    async def handle(request):
        assert request.headers["Authorization"] == "Bearer local-test-token"
        message = await request.json()
        received.append(message)
        method = message["method"]
        if method == "notifications/initialized":
            return web.Response(status=202)
        if method == "initialize":
            result = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}}
        elif method == "tools/list":
            assert request.headers["MCP-Protocol-Version"] == "2025-06-18"
            result = {
                "tools": [
                    {
                        "name": "create_task",
                        "description": "Add an item",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"name": {"type": "string"}},
                            "required": ["name"],
                        },
                    }
                ]
            }
        else:
            assert method == "tools/call"
            assert message["params"]["arguments"] == {"name": "Milch"}
            result = {"content": [{"type": "text", "text": "Saved"}], "isError": False}
        envelope = {"jsonrpc": "2.0", "id": message["id"], "result": result}
        if sse:
            import json

            return web.Response(
                text="data: " + json.dumps(envelope) + "\n\n", content_type="text/event-stream"
            )
        return web.json_response(envelope)

    app = web.Application()
    app.router.add_post("/mcp", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = runner.addresses[0][1]
    try:
        async with aiohttp.ClientSession() as session:
            client = MCPClient(session, f"http://127.0.0.1:{port}/mcp", "local-test-token")
            await client.initialize()
            runtime = Runtime(client, await client.list_tools(), lambda: {"create_task"})
            result = await runtime.call(
                "create_task", {"name": "Milch"}, call_id="call", scope="turn", owner="user"
            )
            assert not result["isError"]
            assert [r["method"] for r in received] == [
                "initialize",
                "notifications/initialized",
                "tools/list",
                "tools/call",
            ]
            await runtime.close()
    finally:
        await runner.cleanup()


async def test_response_size_limit(monkeypatch):
    from custom_components.yuvomi_mcp import client as module

    monkeypatch.setattr(module, "MAX_RESPONSE", 64)
    app = web.Application()

    async def handle(request):
        return web.Response(body=b"x" * 65, content_type="application/json")

    app.router.add_post("/mcp", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    try:
        async with aiohttp.ClientSession() as session:
            client = MCPClient(session, f"http://127.0.0.1:{runner.addresses[0][1]}/mcp", "local-test-token")
            with pytest.raises(MCPError, match="Größenlimit"):
                await client.list_tools()
    finally:
        await runner.cleanup()


async def test_real_rest_redirect_never_forwards_token():
    from custom_components.yuvomi_mcp.client import ShoppingReadError

    stolen = []

    async def redirect(request):
        raise web.HTTPFound("/other-endpoint")

    async def other(request):
        stolen.append(request.headers.get("Authorization"))
        return web.json_response({"data": []})

    app = web.Application()
    app.router.add_get("/api/v1/shopping/categories", redirect)
    app.router.add_get("/other-endpoint", other)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", 0).start()
    try:
        async with aiohttp.ClientSession() as session:
            client = MCPClient(session, f"http://127.0.0.1:{runner.addresses[0][1]}/mcp", "local-test-token")
            with pytest.raises(ShoppingReadError):
                await client.get_shopping_categories()
        assert not stolen
    finally:
        await runner.cleanup()
