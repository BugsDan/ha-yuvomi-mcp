"""Tests against real HA classes. Run on Linux / Python >=3.14.2 (see CI).

Skipped on the Windows development host, which has Python 3.12 and no HA.
These use real framework schemas/results with mocked HA storage/network.
"""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

pytest.importorskip("homeassistant")

from homeassistant.components import llm as llm_component  # noqa: E402
from homeassistant.helpers import llm  # noqa: E402

from custom_components.yuvomi_mcp import config_flow  # noqa: E402
from custom_components.yuvomi_mcp import llm as platform
from custom_components.yuvomi_mcp.client import AuthenticationError, ConnectionError, RemoteTool  # noqa: E402
from custom_components.yuvomi_mcp.const import DEFAULT_TOOLS, DOMAIN  # noqa: E402
from custom_components.yuvomi_mcp.runtime import Runtime  # noqa: E402


def context():
    return llm.LLMContext(
        platform="openai_conversation", context=None, language="de", assistant="conversation", device_id=None
    )


def runtime():
    client = AsyncMock()
    client.call_tool.return_value = {"isError": False, "content": [{"type": "text", "text": "Saved"}]}
    tools = {n: RemoteTool(n, "Description", {"type": "object", "properties": {}}) for n in DEFAULT_TOOLS}
    return Runtime(client, tools, lambda: set(DEFAULT_TOOLS))


async def test_actual_assist_aggregation_preserves_existing_tools():
    state = runtime()
    other = SimpleNamespace(name="other__existing", integration="other")
    existing = SimpleNamespace(
        async_get_tools=lambda *args: llm_component.LLMTools([other], "Existing prompt")
    )
    platforms = SimpleNamespace(
        async_get_platforms=AsyncMock(return_value={"other": existing, DOMAIN: platform})
    )
    hass = SimpleNamespace(data={DOMAIN: {"entry": state}, llm_component.DATA_PLATFORMS: platforms})
    instance = await llm_component.AssistAPI(hass).async_get_api_instance(context())
    assert other in instance.tools
    assert len(instance.tools) == 7
    assert "Existing prompt" in instance.api_prompt
    assert "Europe/Zurich" in instance.api_prompt
    tool = next(t for t in instance.tools if t.name == "yuvomi_mcp__create_task")
    result = await tool.async_call(hass, llm.ToolInput(tool_name=tool.name, tool_args={}), context())
    assert isinstance(result, llm.ToolResult)
    assert not result.error
    await state.close()
    assert platform.async_get_tools(hass, context(), "assist") is None


async def test_actual_toolresult_marks_remote_errors():
    state = runtime()
    state.client.call_tool.return_value = {"isError": True, "content": []}
    tool = platform.YuvomiTool(state, "create_task")
    result = await tool.async_call(None, llm.ToolInput(tool_name=tool.name, tool_args={}), context())
    assert result.error
    await state.close()


async def test_categories_are_read_only_non_destructive_and_require_explicit_opt_in():
    client = AsyncMock()
    client.call_tool.return_value = {"isError": False, "content": []}
    client.get_shopping_categories.return_value = []
    selected = set(DEFAULT_TOOLS)
    tools = {
        "list_shopping_categories": RemoteTool("list_shopping_categories", "Categories", {"type": "object"})
    }
    state = Runtime(client, tools, lambda: selected)
    hass = SimpleNamespace(data={DOMAIN: {"entry": state}})
    try:
        assert platform.async_get_tools(hass, context(), "assist") is None
        selected.add("list_shopping_categories")
        result = platform.async_get_tools(hass, context(), "assist")
        assert len(result.tools) == 1
        tool = result.tools[0]
        assert tool.name == "yuvomi_mcp__list_shopping_categories"
        assert tool.annotations.read_only
        assert tool.annotations.idempotent
        assert not tool.annotations.destructive
        assert not tool.annotations.open_world
        response = await tool.async_call(hass, llm.ToolInput(tool_name=tool.name, tool_args={}), context())
        assert not response.error
        assert not state.pending()
        selected.clear()
        response = await tool.async_call(hass, llm.ToolInput(tool_name=tool.name, tool_args={}), context())
        assert response.error
        assert client.get_shopping_categories.await_count == 1
        client.call_tool.assert_not_called()
    finally:
        await state.close()


def flow():
    result = config_flow.ConfigFlow()
    result.hass = Mock()
    result.hass.config_entries.async_entries.return_value = []
    result.context = {"source": "user"}
    result.handler = DOMAIN
    result.flow_id = "flow-test"
    result.async_set_unique_id = AsyncMock()
    result._abort_if_unique_id_configured = Mock()
    return result


async def test_config_form_uses_actual_password_selector():
    instance = flow()
    result = await instance.async_step_user()
    schema = result["data_schema"]
    assert schema({"url": "http://host/mcp", "api_token": "a-token"})["api_token"] == "a-token"
    selectors = list(schema.schema.values())
    assert any(getattr(s, "config", {}).get("type") == "password" for s in selectors)


async def test_setup_persists_only_initial_default_allowlist(monkeypatch):
    instance = flow()
    tools = {
        name: object()
        for name in DEFAULT_TOOLS | {"call_api_operation", "new_tool", "list_shopping_categories"}
    }
    monkeypatch.setattr(config_flow, "validate_connection", AsyncMock(return_value=tools))
    result = await instance.async_step_user({"url": "http://host/mcp", "api_token": "a-token"})
    assert result["data"]["api_token"] == "a-token"
    assert set(result["options"]["enabled_tools"]) == DEFAULT_TOOLS


@pytest.mark.parametrize(
    "error,code",
    [(AuthenticationError("fixed"), "invalid_auth"), (ConnectionError("fixed"), "cannot_connect")],
)
async def test_setup_errors_are_translated(monkeypatch, error, code):
    instance = flow()
    monkeypatch.setattr(config_flow, "validate_connection", AsyncMock(side_effect=error))
    result = await instance.async_step_user({"url": "http://host/mcp", "api_token": "a-token"})
    assert result["errors"] == {"base": code}


def load_setup_module():
    path = Path(__file__).parents[1] / "custom_components/yuvomi_mcp/__init__.py"
    # Load setup as a normal module so relative imports use the integration
    # package, rather than treating this __init__.py as a setup_test package.
    spec = importlib.util.spec_from_file_location(
        "custom_components.yuvomi_mcp.setup_test", path, submodule_search_locations=None
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def test_setup_and_unload_use_managed_session(monkeypatch):
    module = load_setup_module()
    client = AsyncMock()
    client.list_tools.return_value = {"list_tasks": RemoteTool("list_tasks", "Tasks", {"type": "object"})}
    monkeypatch.setattr(module, "async_get_clientsession", lambda hass: "managed-session")
    constructor = Mock(return_value=client)
    monkeypatch.setattr(module, "MCPClient", constructor)
    from test_journal import make_journal

    monkeypatch.setattr(module, "load_journal", AsyncMock(return_value=await make_journal()))
    hass = SimpleNamespace(data={})
    entry = SimpleNamespace(
        entry_id="entry",
        data={"url": "http://host/mcp", "api_token": "token"},
        options={"enabled_tools": ["list_tasks"]},
        async_on_unload=Mock(),
        add_update_listener=Mock(),
    )
    assert await module.async_setup_entry(hass, entry)
    constructor.assert_called_once_with("managed-session", "http://host/mcp", "token")
    assert entry.runtime_data.enabled() == {"list_tasks"}
    assert await module.async_unload_entry(hass, entry)
    assert entry.runtime_data.enabled() == set()


def options_flow(entry, state=None):
    instance = config_flow.OptionsFlow()
    instance.hass = Mock()
    instance.hass.data = {DOMAIN: {entry.entry_id: state}} if state else {}
    instance.hass.config_entries.async_get_known_entry.return_value = entry
    instance.handler = entry.entry_id
    instance.flow_id = "options-flow"
    return instance


async def test_options_empty_selection_and_new_tools_stay_off(monkeypatch):
    entry = SimpleNamespace(entry_id="entry", data={}, options={"enabled_tools": ["list_tasks"]})
    tools = {"list_tasks": object(), "new_tool": object()}
    monkeypatch.setattr(config_flow, "validate_connection", AsyncMock(return_value=tools))
    instance = options_flow(entry)
    form = await instance.async_step_tools()
    assert form["data_schema"]({})["enabled_tools"] == ["list_tasks"]
    result = await instance.async_step_tools({"enabled_tools": []})
    assert result["data"] == {"enabled_tools": []}


async def test_options_confirm_only_approves_exact_pending_request():
    client = AsyncMock()
    client.redact = Mock(side_effect=lambda value: value)
    state = Runtime(
        client, {"new_tool": RemoteTool("new_tool", "New", {"type": "object"})}, lambda: {"new_tool"}
    )
    await state.call("new_tool", {"name": "Test"}, call_id="call", scope="turn", owner="user")
    pending = state.pending()[0]
    entry = SimpleNamespace(entry_id="entry")
    instance = options_flow(entry, state)
    details = await instance.async_step_approve({"request_id": pending.request_id})
    assert details["step_id"] == "confirm"
    assert "Test" in details["description_placeholders"]["arguments"]
    client.call_tool.assert_not_called()
    result = await instance.async_step_confirm({"confirm": True})
    assert result["reason"] == "approved"
    assert pending.approved
    client.call_tool.assert_not_called()
    await state.close()


async def test_options_remove_product_functions_and_preserve_other_options(monkeypatch):
    entry = SimpleNamespace(entry_id="entry", data={}, options={"enabled_tools": [], "future_option": "keep"})
    instance = options_flow(entry)
    menu = await instance.async_step_init()
    assert menu["menu_options"] == ["tools", "approve", "executions"]
    assert not hasattr(instance, "async_step_products")
    monkeypatch.setattr(config_flow, "validate_connection", AsyncMock(return_value={"list_tasks": object()}))
    result = await instance.async_step_tools({"enabled_tools": ["list_tasks"]})
    assert result["data"]["future_option"] == "keep"


async def test_actual_store_adapter_requests_atomic_writes(monkeypatch):
    from test_journal import MemoryStore

    from custom_components.yuvomi_mcp import persistence

    store = MemoryStore()
    constructor = Mock(return_value=store)
    monkeypatch.setattr(persistence, "Store", constructor)
    entry = SimpleNamespace(entry_id="entry", data={"url": "http://host/mcp"})
    hass = object()
    journal = await persistence.load_journal(hass, entry)
    assert constructor.call_count == 2
    constructor.assert_any_call(hass, 1, "yuvomi_mcp.entry", atomic_writes=True)
    constructor.assert_any_call(hass, 1, "yuvomi_mcp.entry.catalog_archive_v1", atomic_writes=True)
    assert journal.binding == "http://host/mcp"


async def test_migration_adapter_archives_legacy_store_with_real_framework_imports(monkeypatch):
    from test_journal import MemoryStore, legacy_data

    from custom_components.yuvomi_mcp import persistence

    original = legacy_data()
    store, archive = MemoryStore(original), MemoryStore()
    monkeypatch.setattr(persistence, "Store", Mock(side_effect=[store, archive]))
    entry = SimpleNamespace(entry_id="entry", data={"url": "http://host/mcp"})
    journal = await persistence.load_journal(object(), entry)
    assert archive.data == original
    assert journal.data["journal"] == original["journal"]
    assert set(journal.data) == {"schema", "binding", "journal"}


async def test_execution_options_only_observe_and_never_resend():
    from test_journal import make_journal

    journal = await make_journal()
    engine = SimpleNamespace(reconcile=AsyncMock(return_value={"message": "Zustand beobachtet"}))
    state = SimpleNamespace(journal=journal, purchasing=engine)
    instance = options_flow(SimpleNamespace(entry_id="entry"), state)
    result = await instance.async_step_executions({"execution": "key"})
    engine.reconcile.assert_awaited_once_with("key")
    assert result["step_id"] == "execution_result"
    assert result["description_placeholders"]["message"] == "Zustand beobachtet"
