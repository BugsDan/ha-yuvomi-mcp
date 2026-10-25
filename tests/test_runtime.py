import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock

import probatio
import pytest

from custom_components.yuvomi_mcp.client import ConnectionError, MCPError, RemoteTool
from custom_components.yuvomi_mcp.const import DEFAULT_TOOLS
from custom_components.yuvomi_mcp.runtime import Runtime

SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "minLength": 1},
        "quantity": {"type": "string"},
        "count": {"type": "integer", "minimum": 1},
        "when": {"type": "string", "format": "date-time"},
    },
    "required": ["name"],
    "additionalProperties": False,
}
SUCCESS = {"isError": False, "content": [{"type": "text", "text": "Saved"}]}


def make_runtime():
    names = set(DEFAULT_TOOLS) | {"call_api_operation", "list_api_operations", "new_tool"}
    tools = {name: RemoteTool(name, name, deepcopy(SCHEMA)) for name in names}
    client = AsyncMock()
    client.call_tool.return_value = deepcopy(SUCCESS)
    enabled = set(DEFAULT_TOOLS)
    now = [1000.0]
    runtime = Runtime(client, tools, lambda: enabled, clock=lambda: now[0])
    return runtime, client, enabled, now


async def call(runtime, name="create_task", args=None, **kwargs):
    return await runtime.call(
        name,
        {"name": "Milch", "quantity": "3 Liter"} if args is None else args,
        call_id=kwargs.get("call_id", "call-1"),
        scope=kwargs.get("scope", "turn-1"),
        owner=kwargs.get("owner", "user-1"),
    )


async def test_default_allowlist_and_call_time_revocation():
    runtime, client, enabled, _ = make_runtime()
    assert runtime.enabled() == DEFAULT_TOOLS
    assert (await call(runtime, "call_api_operation"))["isError"]
    assert (await call(runtime, "unknown"))["isError"]
    client.call_tool.assert_not_called()
    assert not (await call(runtime))["isError"]
    enabled.remove("create_task")
    assert (await call(runtime))["code"] == "not_allowed"
    assert client.call_tool.await_count == 1


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"name": ""},
        {"name": 2},
        {"name": "X", "count": 0},
        {"name": "X", "count": True},
        {"name": "X", "unexpected": True},
        [],
        {"name": "X", "when": "tomorrow"},
    ],
)
async def test_validation_before_network(arguments):
    runtime, client, _, _ = make_runtime()
    assert (await call(runtime, args=arguments))["code"] == "invalid_arguments"
    client.call_tool.assert_not_called()


def test_schema_required_optional_and_roundtrip():
    runtime, *_ = make_runtime()
    schema = probatio.to_openapi(runtime.parameters["add_shopping_item"], openapi_version="3.1.0")
    assert schema["required"] == ["name"]
    assert schema["properties"]["quantity"]["type"] == "string"
    assert "quantity" not in schema["required"]


async def test_local_offset_is_forwarded_without_inventing_parameters():
    runtime, client, *_ = make_runtime()
    args = {"name": "Autowaschen", "when": "2026-10-24T14:00:00+02:00"}
    assert not (await call(runtime, "create_event", args))["isError"]
    client.call_tool.assert_awaited_once_with("create_event", args)


async def test_concurrent_duplicate_writes_are_coalesced():
    runtime, client, *_ = make_runtime()

    async def slow(*args):
        await asyncio.sleep(0.01)
        return deepcopy(SUCCESS)

    client.call_tool.side_effect = slow
    results = await asyncio.gather(*(call(runtime, call_id=f"call-{i}") for i in range(20)))
    assert all(result == SUCCESS for result in results)
    assert client.call_tool.await_count == 1
    assert not runtime._locks


async def test_distinct_articles_and_new_turns_not_deduplicated():
    runtime, client, *_ = make_runtime()
    for name in ["Milch", "Eier", "Kartoffeln"]:
        assert not (await call(runtime, args={"name": name}))["isError"]
    await call(runtime, args={"name": "Milch"}, scope="new-turn")
    assert client.call_tool.await_count == 4


async def test_partial_failure_and_unknown_outcome_not_retried():
    runtime, client, *_ = make_runtime()
    client.call_tool.side_effect = [SUCCESS, ConnectionError("not exposed"), SUCCESS]
    results = [await call(runtime, args={"name": name}) for name in ["Milch", "Eier", "Kartoffeln"]]
    assert [r["isError"] for r in results] == [False, True, False]
    again = await call(runtime, args={"name": "Eier"})
    assert again["code"] == "execution_unconfirmed"
    assert client.call_tool.await_count == 3


async def test_error_result_stays_error_and_cache_expires():
    runtime, client, _, now = make_runtime()
    client.call_tool.return_value = {"isError": True, "content": []}
    assert (await call(runtime))["isError"]
    assert (await call(runtime))["isError"]
    assert client.call_tool.await_count == 1
    now[0] += 121
    await call(runtime)
    assert client.call_tool.await_count == 2


async def test_reads_are_not_cached():
    runtime, client, *_ = make_runtime()
    await call(runtime, "list_tasks")
    await call(runtime, "list_tasks")
    assert client.call_tool.await_count == 2


async def test_additional_tools_require_exact_one_use_approval():
    runtime, client, enabled, _ = make_runtime()
    enabled.add("call_api_operation")
    assert (await call(runtime, "call_api_operation"))["code"] == "confirmation_required"
    client.call_tool.assert_not_called()
    pending = runtime.pending()
    assert len(pending) == 1
    assert runtime.approve(pending[0].request_id)
    # Changing arguments or caller does not inherit approval.
    assert (await call(runtime, "call_api_operation", {"name": "Other"}))["code"] == "confirmation_required"
    assert (await call(runtime, "call_api_operation", owner="other-user"))["code"] == "confirmation_required"
    assert not (await call(runtime, "call_api_operation", scope="next-turn"))["isError"]
    assert (await call(runtime, "call_api_operation", scope="third-turn"))["code"] == "confirmation_required"
    assert client.call_tool.await_count == 1


async def test_approval_expires_and_unload_blocks_old_tools():
    runtime, client, enabled, now = make_runtime()
    enabled.add("new_tool")
    await call(runtime, "new_tool")
    request = runtime.pending()[0].request_id
    now[0] += 121
    assert not runtime.approve(request)
    await runtime.close()
    assert (await call(runtime))["code"] == "not_allowed"
    assert not runtime.pending()
    client.call_tool.assert_not_called()


def test_external_schema_reference_is_rejected_without_network():
    schema = {"type": "object", "properties": {"x": {"$ref": "http://evil.example/schema"}}}
    with pytest.raises(MCPError):
        Runtime(AsyncMock(), {"x": RemoteTool("x", "x", schema)}, lambda: {"x"})


async def test_timer_cleanup_and_unload_cancel_expiry_handle():
    runtime, _, enabled, now = make_runtime()
    enabled.add("new_tool")
    await call(runtime)
    await call(runtime, "new_tool")
    assert runtime._cleanup_handle is not None
    now[0] += 121
    runtime._cleanup_handle.cancel()
    runtime._cleanup()
    assert not runtime._cache
    assert not runtime._approvals
    assert runtime._cleanup_handle is None
    await call(runtime)
    handle = runtime._cleanup_handle
    await runtime.close()
    assert handle.cancelled()


async def test_revocation_blocks_queued_call_even_after_first_succeeds():
    runtime, client, enabled, _ = make_runtime()
    entered = asyncio.Event()
    release = asyncio.Event()

    async def slow(*args):
        entered.set()
        await release.wait()
        return deepcopy(SUCCESS)

    client.call_tool.side_effect = slow
    first = asyncio.create_task(call(runtime))
    await entered.wait()
    second = asyncio.create_task(call(runtime))
    await asyncio.sleep(0)
    enabled.clear()
    release.set()
    assert not (await first)["isError"]
    assert (await second)["code"] == "not_allowed"
    assert client.call_tool.await_count == 1
    await runtime.close()
