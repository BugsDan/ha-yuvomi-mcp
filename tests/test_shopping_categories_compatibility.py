"""Categories require opt-in but no action approval; unknown tools remain gated."""

import json
from unittest.mock import AsyncMock

import pytest

from custom_components.yuvomi_mcp.client import RemoteTool
from custom_components.yuvomi_mcp.const import DEFAULT_TOOLS, READ_TOOLS
from custom_components.yuvomi_mcp.runtime import Runtime

CATEGORIES_TOOL = "list_shopping_categories"


def tool_metadata(*extra_names):
    return {
        name: RemoteTool(name, "Test metadata", {"type": "object", "properties": {}})
        for name in DEFAULT_TOOLS | {CATEGORIES_TOOL} | set(extra_names)
    }


async def test_discovered_categories_tool_is_not_automatically_enabled_after_reload():
    # Existing persisted selection remains unchanged when a new server tool appears.
    selected = set(DEFAULT_TOOLS)
    client = AsyncMock()
    state = Runtime(client, tool_metadata(), lambda: selected)
    try:
        assert CATEGORIES_TOOL in state.tools
        assert CATEGORIES_TOOL not in state.enabled()
        result = await state.call(CATEGORIES_TOOL, {}, call_id="call", scope="turn", owner="user")
        assert result["code"] == "not_allowed"
        client.call_tool.assert_not_called()
    finally:
        await state.close()


async def test_manual_categories_activation_executes_without_ui_confirmation():
    selected = set(DEFAULT_TOOLS) | {CATEGORIES_TOOL}
    client = AsyncMock()
    expected = {"isError": False, "content": [{"type": "text", "text": '[{"name":"Milchprodukte"}]'}]}
    client.get_shopping_categories.return_value = [{"name": "Milchprodukte"}]
    state = Runtime(client, tool_metadata(), lambda: selected)
    try:
        assert CATEGORIES_TOOL in state.enabled()
        assert CATEGORIES_TOOL in READ_TOOLS
        result = await state.call(CATEGORIES_TOOL, {}, call_id="call", scope="turn", owner="user")
        assert not result["isError"]
        assert json.loads(result["content"][0]["text"]) == json.loads(expected["content"][0]["text"])
        assert not state.pending()
        client.get_shopping_categories.assert_awaited_once_with()
        client.call_tool.assert_not_called()
    finally:
        await state.close()


async def test_categories_are_fetched_again_even_in_same_turn():
    client = AsyncMock()
    first = [{"name": "Before"}]
    second = [{"name": "After"}]
    client.get_shopping_categories.side_effect = [first, second]
    state = Runtime(client, tool_metadata(), lambda: {CATEGORIES_TOOL})
    try:
        for expected in (first, second):
            result = await state.call(CATEGORIES_TOOL, {}, call_id="call", scope="turn", owner="user")
            assert json.loads(result["content"][0]["text"]) == expected
        assert client.get_shopping_categories.await_count == 2
        client.call_tool.assert_not_called()
        assert not state._cache
        assert not state.pending()
    finally:
        await state.close()


async def test_categories_revocation_and_unload_block_previously_enabled_tool():
    client = AsyncMock()
    client.get_shopping_categories.return_value = []
    selected = {CATEGORIES_TOOL}
    state = Runtime(client, tool_metadata(), lambda: selected)
    try:
        assert not (await state.call(CATEGORIES_TOOL, {}, call_id="call", scope="turn", owner="user"))[
            "isError"
        ]
        selected.clear()
        assert (await state.call(CATEGORIES_TOOL, {}, call_id="call", scope="turn", owner="user"))[
            "code"
        ] == "not_allowed"
        selected.add(CATEGORIES_TOOL)
        await state.close()
        assert (await state.call(CATEGORIES_TOOL, {}, call_id="call", scope="turn", owner="user"))[
            "code"
        ] == "not_allowed"
        assert client.get_shopping_categories.await_count == 1
        client.call_tool.assert_not_called()
    finally:
        await state.close()


@pytest.mark.parametrize(
    "name",
    [
        "list_api_operations",
        "get_api_operation",
        "call_api_operation",
        "list_future_items",
        "list_shopping_categories_extra",
    ],
)
async def test_other_tools_still_require_both_allowlist_and_exact_action_approval(name):
    client = AsyncMock()
    client.call_tool.return_value = {"isError": False, "content": []}
    selected = {CATEGORIES_TOOL}
    state = Runtime(client, tool_metadata(name), lambda: selected)
    try:
        assert (await state.call(name, {}, call_id="call", scope="turn", owner="user"))[
            "code"
        ] == "not_allowed"
        selected.add(name)
        assert (await state.call(name, {}, call_id="call", scope="turn", owner="user"))[
            "code"
        ] == "confirmation_required"
        client.call_tool.assert_not_called()
        assert state.approve(state.pending()[0].request_id)
        assert not (await state.call(name, {}, call_id="call", scope="turn", owner="user"))["isError"]
        assert (await state.call(name, {}, call_id="next-call", scope="next-turn", owner="user"))[
            "code"
        ] == "confirmation_required"
        assert client.call_tool.await_count == 1
    finally:
        await state.close()


async def test_categories_schema_validation_is_not_bypassed():
    client = AsyncMock()
    state = Runtime(client, tool_metadata(), lambda: {CATEGORIES_TOOL})
    try:
        result = await state.call(CATEGORIES_TOOL, [], call_id="call", scope="turn", owner="user")
        assert result["code"] == "invalid_arguments"
        client.call_tool.assert_not_called()
        assert not state.pending()
    finally:
        await state.close()
