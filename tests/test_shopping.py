"""Optional read tools and conservative Unicode category validation."""

import json
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest

from custom_components.yuvomi_mcp.client import MCPClient, RemoteTool
from custom_components.yuvomi_mcp.const import DEFAULT_TOOLS, READ_TOOLS
from custom_components.yuvomi_mcp.runtime import Runtime
from custom_components.yuvomi_mcp.shopping import CATEGORIES, SHOPPING_READS, SUGGESTIONS, resolve_category

SCHEMA = {
    "type": "object",
    "properties": {key: {"type": "string"} for key in ("name", "quantity", "category", "list")},
    "required": ["name"],
    "additionalProperties": False,
}


SUCCESS = {"isError": False, "content": [{"type": "text", "text": "Saved"}]}


def setup(enabled=None, schema=None):
    client = AsyncMock(spec=MCPClient)
    client.call_tool.return_value = deepcopy(SUCCESS)
    client.get_shopping_categories.return_value = [{"name": "Milchprodukte"}, {"name": "Sonstiges"}]
    client.get_shopping_suggestions.return_value = [
        {"name": "MILCH", "category": "Milchprodukte", "quantity": "99 Liter"}
    ]
    selected = set(enabled if enabled is not None else {"add_shopping_item", *SHOPPING_READS})
    state = Runtime(
        client,
        {"add_shopping_item": RemoteTool("add_shopping_item", "Add", schema or SCHEMA)},
        lambda: selected,
    )
    return state, client, selected


async def add(state, args=None, **kwargs):
    return await state.call(
        "add_shopping_item",
        args if args is not None else {"name": "Milch"},
        call_id="call",
        scope=kwargs.get("scope", "turn"),
        owner="user",
    )


async def test_local_reads_exist_without_any_remote_counterpart_and_stay_opt_in():
    state, client, _ = setup(DEFAULT_TOOLS)
    try:
        assert SHOPPING_READS <= state.tools.keys()
        assert SHOPPING_READS <= READ_TOOLS
        assert not (SHOPPING_READS & state.enabled())
        for name in SHOPPING_READS:
            assert (await state.call(name, {}, call_id="call", scope="turn", owner="user"))[
                "code"
            ] == "not_allowed"
        client.get_shopping_categories.assert_not_called()
        client.get_shopping_suggestions.assert_not_called()
    finally:
        await state.close()


@pytest.mark.parametrize(
    "name,args,method",
    [
        (CATEGORIES, {}, "get_shopping_categories"),
        (SUGGESTIONS, {"q": "Milch"}, "get_shopping_suggestions"),
    ],
)
async def test_local_reads_use_rest_without_action_approval_or_mcp(name, args, method):
    state, client, _ = setup({name})
    try:
        result = await state.call(name, args, call_id="call", scope="turn", owner="user")
        assert not result["isError"]
        assert isinstance(json.loads(result["content"][0]["text"]), list)
        assert getattr(client, method).await_count == 1
        client.call_tool.assert_not_called()
        assert not state.pending()
        assert not state._cache
        assert (await add(state))["code"] == "not_allowed"
    finally:
        await state.close()


@pytest.mark.parametrize("args", [{}, {"q": ""}, {"q": "Milch", "url": "http://evil.example"}])
async def test_suggestion_schema_rejects_invalid_input_before_rest(args):
    state, client, _ = setup({SUGGESTIONS})
    try:
        result = await state.call(SUGGESTIONS, args, call_id="call", scope="turn", owner="user")
        assert result["code"] == "invalid_arguments"
        client.get_shopping_suggestions.assert_not_called()
    finally:
        await state.close()


CATEGORY_NAMES = ["Getränke", "Obst & Gemüse", "Süsses und Backzutaten", "Sonstiges"]


@pytest.mark.parametrize(
    "supplied,expected",
    [
        ("Getränke", "Getränke"),
        ("Getr_nke", "Getränke"),
        ("Getr\ufffdnke", "Getränke"),
        ("Getraenke", "Getränke"),
        ("Getranke", "Getränke"),
        ("  GETRÄNKE  ", "Getränke"),
        ("Getra\u0308nke", "Getränke"),
        ("Ｇｅｔｒäｎｋｅ", "Getränke"),
        ("GetrÃ¤nke", "Getränke"),
        (r"Getr\u00e4nke", "Getränke"),
        ("Obst & Gemüse", "Obst & Gemüse"),
        ("Obst und Gemuese", "Obst & Gemüse"),
        ("Obst & Gem_se", "Obst & Gemüse"),
        ("Obst_&_Gemüse", "Obst & Gemüse"),
        ("Obst & GemÃ¼se", "Obst & Gemüse"),
        ("Süsses und Backzutaten", "Süsses und Backzutaten"),
        ("Süßes und Backzutaten", "Süsses und Backzutaten"),
        ("Suesses & Backzutaten", "Süsses und Backzutaten"),
        ("S_sses und Backzutaten", "Süsses und Backzutaten"),
    ],
)
def test_explicit_categories_resolve_to_existing_unicode_names_only(supplied, expected):
    assert resolve_category(supplied, [{"name": n} for n in CATEGORY_NAMES]) == expected


@pytest.mark.parametrize("supplied", ["Unbekannt", "", "  ", "Getr*", "Getr.*nke", "Getr__nke", "Geträn"])
def test_unknown_or_empty_category_returns_valid_choices_without_write(supplied):
    assert resolve_category(supplied, [{"name": n} for n in CATEGORY_NAMES]) is None


@pytest.mark.parametrize(
    "names,supplied",
    [
        (["Getränke", "Getrönke"], "Getr_nke"),
        (["Masse", "Maße"], "MASSE"),
        (["Obst & Gemüse", "Obst und Gemüse"], "obst und gemuese"),
    ],
)
def test_ambiguous_spelling_is_never_chosen_by_order(names, supplied):
    for ordered in (names, list(reversed(names))):
        assert resolve_category(supplied, [{"name": n} for n in ordered]) is None


@pytest.mark.parametrize("exact", ["Getränke", "Getranke"])
def test_exact_category_always_wins_over_normalization_collision(exact):
    assert resolve_category(exact, [{"name": "Getränke"}, {"name": "Getranke"}]) == exact
