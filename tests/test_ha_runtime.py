"""Real HA 2026.10.2 objects/event loop/storage/ChatLog; only remote MCP is a loopback fixture.

No mock of HA, its API registry, API merge, selectors or config entry lifecycle.
The existing Windows host cannot import HA; CI explicitly rejects any skip.
"""

from pathlib import Path
from types import MappingProxyType

import aiohttp
import pytest
from aiohttp import web

pytest.importorskip("homeassistant")

from homeassistant.components import llm as llm_component  # noqa: E402
from homeassistant.components.conversation.chat_log import ChatLog  # noqa: E402
from homeassistant.config_entries import ConfigEntries, ConfigEntry  # noqa: E402
from homeassistant.core import HomeAssistant  # noqa: E402
from homeassistant.helpers import llm, selector  # noqa: E402
from homeassistant.loader import async_setup as setup_loader  # noqa: E402

from custom_components.yuvomi_mcp.client import MCPClient  # noqa: E402
from custom_components.yuvomi_mcp.const import CONF_TOOLS, DOMAIN  # noqa: E402
from custom_components.yuvomi_mcp.llm import YuvomiAPI, async_get_tools  # noqa: E402
from custom_components.yuvomi_mcp.persistence import load_journal, planning_store  # noqa: E402
from custom_components.yuvomi_mcp.planning_config import DEFAULTS  # noqa: E402
from custom_components.yuvomi_mcp.runtime import Runtime  # noqa: E402


@pytest.fixture
async def real_ha(tmp_path):
    hass = HomeAssistant(str(tmp_path))
    setup_loader(hass)
    hass.config_entries = ConfigEntries(hass, {})
    await hass.config_entries.async_initialize()
    assert await llm_component.async_setup(hass, {})
    try:
        yield hass
    finally:
        await hass.async_stop(force=True)


@pytest.fixture
async def mcp_runtime(real_ha):
    calls = []

    async def endpoint(request):
        payload = await request.json()
        method = payload["method"]
        if method == "notifications/initialized":
            return web.Response(status=202)
        if method == "initialize":
            answer = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}}
        elif method == "tools/list":
            answer = {
                "tools": [
                    {
                        "name": "list_tasks",
                        "description": "Tasks",
                        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
                    }
                ]
            }
        else:
            assert method == "tools/call"
            calls.append(payload["params"])
            answer = {"isError": False, "content": [{"type": "text", "text": "[]"}]}
        return web.json_response({"jsonrpc": "2.0", "id": payload["id"], "result": answer})

    app = web.Application()
    app.router.add_post("/mcp", endpoint)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    try:
        async with aiohttp.ClientSession() as session:
            client = MCPClient(session, f"http://127.0.0.1:{runner.addresses[0][1]}/mcp", "local-test-token")
            await client.initialize()
            allowed = {"list_tasks"}
            runtime = Runtime(client, await client.list_tools(), lambda: allowed)
            mode = {"value": "assist"}
            runtime.exposure = lambda: mode["value"]
            real_ha.data[DOMAIN] = {"runtime": runtime}
            try:
                yield runtime, mode, allowed, calls, client._url
            finally:
                await runtime.close()
    finally:
        await runner.cleanup()


def context():
    return llm.LLMContext(
        platform="local_openai", context=None, language="de", assistant="conversation", device_id=None
    )


def entry(url):
    return ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Yuvomi MCP",
        source="user",
        unique_id=url,
        data={"url": url, "api_token": "local-test-token"},
        options={CONF_TOOLS: ["list_tasks"]},
        discovery_keys=MappingProxyType({}),
        subentries_data=[],
    )


async def test_real_registry_config_entry_lifecycle_and_mode_reversibility(real_ha, mcp_runtime):
    runtime, mode, allowed, calls, url = mcp_runtime
    old_entry = entry(url)
    before = dict(old_entry.options)
    api = YuvomiAPI(real_ha, old_entry, runtime)
    old_entry.async_on_unload(llm.async_register_api(real_ha, api))
    assert api in llm.async_get_apis(real_ha)
    legacy = async_get_tools(real_ha, context(), "assist").tools[0]
    assert not (await api.async_get_api_instance(context())).tools
    mode["value"] = "dedicated"
    assert async_get_tools(real_ha, context(), "assist") is None
    instance = await llm.async_get_api(real_ha, api.id, context())
    tool = instance.tools[0]
    reply = await tool.async_call(
        real_ha, llm.ToolInput(tool_name=tool.name, tool_args={}, id="read"), context()
    )
    assert not reply.error and len(calls) == 1
    denied = await legacy.async_call(
        real_ha, llm.ToolInput(tool_name=legacy.name, tool_args={}, id="old"), context()
    )
    assert denied.error and len(calls) == 1
    allowed.clear()
    denied = await tool.async_call(
        real_ha, llm.ToolInput(tool_name=tool.name, tool_args={}, id="revoke"), context()
    )
    assert denied.error and len(calls) == 1
    allowed.add("list_tasks")
    mode["value"] = "assist"
    assert async_get_tools(real_ha, context(), "assist").tools
    assert dict(old_entry.options) == before and "exposure_mode" not in old_entry.options
    await old_entry._async_process_on_unload(real_ha)
    assert api not in llm.async_get_apis(real_ha)
    unregister = llm.async_register_api(real_ha, api)
    unregister()


async def test_real_api_selector_chatlog_and_combined_apis(real_ha, mcp_runtime):
    runtime, mode, _, calls, url = mcp_runtime
    mode["value"] = "dedicated"
    api = YuvomiAPI(real_ha, entry(url), runtime)
    unregister = llm.async_register_api(real_ha, api)
    try:
        selection = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[{"value": a.id, "label": a.name} for a in llm.async_get_apis(real_ha)], multiple=True
            )
        )
        selected = selection(["assist", api.id])
        log = ChatLog(real_ha, "isolated-ci-conversation")
        await log.async_provide_llm_data(context(), selected, "Identical CI agent prompt")
        assert isinstance(log.llm_api.api, llm.MergedAPI)
        tool = next(t for t in log.llm_api.tools if t.name.endswith("__list_tasks"))
        assert tool.name != "yuvomi_mcp__list_tasks" and len(tool.name) <= 64
        reply = await tool.async_call(
            real_ha, llm.ToolInput(tool_name=tool.name, tool_args={}, id="merged"), context()
        )
        assert not reply.error and len(calls) == 1
        assert log.conversation_id == "isolated-ci-conversation"
        await log.async_provide_llm_data(context(), [api.id], "Identical CI agent prompt")
        assert [t.name for t in log.llm_api.tools] == ["yuvomi_mcp__list_tasks"]
    finally:
        unregister()


async def test_real_chatlog_preserves_time_fallback_and_prompt_order(real_ha, mcp_runtime):
    from datetime import datetime, timezone

    from homeassistant.util import dt as dt_util

    runtime, mode, _, calls, url = mcp_runtime
    assist = async_get_tools(real_ha, context(), "assist")
    mode["value"] = "dedicated"
    api = YuvomiAPI(real_ha, entry(url), runtime)
    previous_zone = dt_util.DEFAULT_TIME_ZONE
    dt_util.set_default_time_zone(dt_util.get_time_zone("Europe/Zurich"))
    try:
        first = await api.async_get_api_instance(context())
        second = await api.async_get_api_instance(context())
        assert assist.prompt == first.api_prompt == second.api_prompt
        assert "Aktuelle Zeit (" not in first.api_prompt
        assert [tool.name for tool in first.tools] == ["yuvomi_mcp__list_tasks"]
        assert not calls
        # Real HA templates/clock: dynamic fallback is retained, never cached by Yuvomi.
        before = datetime.now(timezone.utc).astimezone(dt_util.DEFAULT_TIME_ZONE).date()
        log = ChatLog(real_ha, "time-context-regression")
        await log.async_provide_llm_data(context(), api, "AGENT_STATIC", "FAMILY_EXTRA")
        after = datetime.now(timezone.utc).astimezone(dt_util.DEFAULT_TIME_ZONE).date()
        text = log.content[0].content
        assert text.index("AGENT_STATIC") < text.index(first.api_prompt)
        assert text.index(first.api_prompt) < text.index("Current time is") < text.index("FAMILY_EXTRA")
        assert any(f"Today's date is {day}." in text for day in (before, after))
        assert text.count("Current time is") == 1
        assert "Aktuelle Zeit (" not in text
        assert not calls
    finally:
        dt_util.set_default_time_zone(previous_zone)


async def test_real_recipe_api_exposes_compact_pages_and_single_full_title_read(real_ha):
    from test_recipe_views import sample_recipes

    from custom_components.yuvomi_mcp.const import RECIPE_READS

    rows = sample_recipes()
    rows[0]["title"] = "Fleischkäse mit Ofengemüse"
    requests = []

    async def recipes(request):
        requests.append(request.method)
        return web.json_response({"data": rows})

    app = web.Application()
    app.router.add_get("/api/v1/recipes", recipes)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", 0).start()
    try:
        async with aiohttp.ClientSession() as session:
            client = MCPClient(session, f"http://127.0.0.1:{runner.addresses[0][1]}/mcp", "local-test-token")
            selected = set(RECIPE_READS)
            state = Runtime(client, {}, lambda: selected)
            state.exposure = lambda: "dedicated"
            try:
                api = await YuvomiAPI(real_ha, entry(client._url), state).async_get_api_instance(context())
                tools = {tool.remote_name: tool for tool in api.tools}
                page = await tools["list_recipes"].async_call(
                    real_ha, llm.ToolInput(tool_name=tools["list_recipes"].name, tool_args={}), context()
                )
                assert not page.error and "content" not in page.data
                assert len(page.data["data"]) == 20 and page.data["next_offset"] == 20
                assert all("notes" not in row and "ingredients" not in row for row in page.data["data"])
                detail = await tools["get_recipe"].async_call(
                    real_ha,
                    llm.ToolInput(tool_name=tools["get_recipe"].name, tool_args={"title": rows[0]["title"]}),
                    context(),
                )
                assert not detail.error and "content" not in detail.data
                assert detail.data["data"]["notes"] == rows[0]["notes"]
                assert detail.data["data"]["ingredients"] == rows[0]["ingredients"]
                selected.clear()
                denied = await tools["list_recipes"].async_call(
                    real_ha, llm.ToolInput(tool_name=tools["list_recipes"].name, tool_args={}), context()
                )
                assert denied.error and requests == ["GET", "GET"]
            finally:
                await state.close()
    finally:
        await runner.cleanup()


async def test_real_atomic_ha_store_restores_config_and_unresolved_journal(real_ha, mcp_runtime):
    _, _, _, _, url = mcp_runtime
    old_entry = entry(url)
    config = planning_store(real_ha, old_entry)
    await config.load()
    await config.update({**DEFAULTS, "profiles": {"child": {"name": "Kind", "days": [0, 1, 2]}}})
    journal = await load_journal(real_ha, old_entry)
    await journal.change(
        lambda data: data["journal"].update(
            pending={
                "id": "pending",
                "resource": "meals",
                "list_id": 1,
                "name": "Plan",
                "method": "POST",
                "body": {"assignments": []},
                "state": "unknown",
                "result": None,
                "created_at": "2026-10-26T12:00:00+00:00",
            }
        )
    )
    restored = planning_store(real_ha, old_entry)
    await restored.load()
    restored_journal = await load_journal(real_ha, old_entry)
    assert restored.data == config.data
    assert restored_journal.data["journal"]["pending"]["state"] == "unknown"
    assert list(Path(real_ha.config.config_dir).joinpath(".storage").glob("yuvomi_mcp*"))
    assert dict(old_entry.options) == {CONF_TOOLS: ["list_tasks"]}


async def test_real_calendar_service_enforces_user_permissions_and_exact_allowlist(real_ha):
    from copy import deepcopy
    from datetime import date

    from homeassistant.auth import auth_manager_from_config
    from homeassistant.core import Context, SupportsResponse
    from homeassistant.helpers import device_registry as dr
    from homeassistant.helpers import entity_registry as er

    from custom_components.yuvomi_mcp.planning_calendar import calendar_reader
    from custom_components.yuvomi_mcp.shopping_api import ShoppingFailure

    dr.async_setup(real_ha)
    await dr.async_load(real_ha)
    await er.async_load(real_ha)
    real_ha.auth = await auth_manager_from_config(real_ha, [], [])
    owner = await real_ha.auth.async_create_user("CI owner")
    denied_user = await real_ha.auth.async_create_user("CI no permissions", group_ids=[])
    real_ha.states.async_set("calendar.selected", "off")
    real_ha.states.async_set("calendar.not_selected", "off")
    calls = []

    async def get_events(call):
        calls.append(call)
        assert call.data["entity_id"] == ["calendar.selected"]
        return {"calendar.selected": {"events": []}}

    real_ha.services.async_register(
        "calendar", "get_events", get_events, supports_response=SupportsResponse.ONLY
    )
    settings = {**deepcopy(DEFAULTS), "calendars": {"selected": {"entity": "calendar.selected"}}}
    read = calendar_reader(real_ha)
    with pytest.raises(ShoppingFailure) as err:
        await read(settings, date(2026, 10, 26), date(2026, 10, 26), Context(user_id=denied_user.id))
    assert err.value.code == "calendar_not_allowed" and not calls
    with pytest.raises(ShoppingFailure):
        await read(settings, date(2026, 10, 26), date(2026, 10, 26), None)
    assert not calls
    result = await read(settings, date(2026, 10, 26), date(2026, 10, 26), Context(user_id=owner.id))
    assert result == {"calendar.selected": []} and len(calls) == 1
    assert calls[0].context.user_id == owner.id
    assert "calendar.not_selected" not in calls[0].data["entity_id"]
