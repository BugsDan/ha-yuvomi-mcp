"""Bounded recipe reads and public planning projections retain complete private source data."""

import json
from copy import deepcopy
from unittest.mock import AsyncMock

import probatio
import pytest
from test_menu_planning import engine as planning_engine
from test_recipes import API, CREATE, METADATA, call, engine, recipe

from custom_components.yuvomi_mcp.const import RECIPE_READS
from custom_components.yuvomi_mcp.recipe_engine import Recipes, result
from custom_components.yuvomi_mcp.recipe_views import planning_recipe, summary
from custom_components.yuvomi_mcp.recipes import RecipeAPI, merged_notes
from custom_components.yuvomi_mcp.runtime import Runtime
from custom_components.yuvomi_mcp.shopping_api import ShoppingFailure


def sample_recipes(count=22):
    instructions = ("Gemüse waschen, gleichmäßig schneiden und mit Gewürzen im Ofen garen. " * 40).strip()
    return [
        recipe(
            i + 1,
            title=f"Familienmenü {i + 1:02d} – Ofenvariante",
            notes=merged_notes(None, {**CREATE, "notes": instructions}, creating=True),
            ingredients=[
                {
                    "name": f"Zutat {j}",
                    "quantity": f"{100 + j} g",
                    "category": "Sonstiges",
                    "id": j + 1,
                    "pantry_item_id": None,
                }
                for j in range(12)
            ],
        )
        for i in range(count)
    ]


def llm_payload(reply):
    return {k: v for k, v in reply.items() if k != "content"}


async def test_compact_list_default_and_full_legacy_pages():
    rows = sample_recipes()
    service, api, journal = await engine(rows)
    before = deepcopy(api.rows)
    page = await call(service, {}, tool="list_recipes")
    assert len(page["data"]) == 20 and page["total"] == 22
    assert page["has_more"] and page["next_offset"] == 20
    assert page["data"][0] == summary(rows[0])
    assert set(page["data"][0]) == {
        "id",
        "title",
        "meal_types",
        "basisportionen",
        "zubereitungszeit_min",
        "wiederaufwärmbar",
        "gesundheit",
        "mag_nicht",
    }
    assert page["data"][0]["basisportionen"] == 4
    assert page["data"][0]["wiederaufwärmbar"] is True
    last = await call(service, {"offset": 20, "limit": 20}, tool="list_recipes")
    assert [r["id"] for r in last["data"]] == [21, 22]
    assert not last["has_more"] and last["next_offset"] is None
    empty = await call(service, {"offset": 100}, tool="list_recipes")
    assert empty["data"] == [] and empty["total"] == 22 and not empty["has_more"]
    full = await call(service, {"detail": "full", "limit": 100}, tool="list_recipes")
    assert full["data"] == [Recipes.present(row) for row in rows]
    assert api.rows == before and not api.writes and not journal.data["journal"]


async def test_exact_title_variants_and_single_recipe_full_details():
    rows = [
        recipe(1, title="Fleischkäse mit Ofengemüse"),
        recipe(2, title="Fleischkäse mit Ofengemüse – vegan"),
    ]
    service, api, _ = await engine(rows)
    direct = await call(service, {"title": rows[0]["title"]}, tool="get_recipe")
    assert direct["data"] == Recipes.present(rows[0])
    assert api.reads == 1 and not api.writes
    by_id = await call(service, {"recipe_id": 2}, tool="get_recipe")
    assert by_id["data"] == Recipes.present(rows[1])
    assert (await call(service, {"title": "Fleischkäse"}, tool="get_recipe"))["code"] == "recipe_not_found"
    exact = await call(service, {"title": rows[0]["title"]}, tool="list_recipes")
    assert [r["id"] for r in exact["data"]] == [1]
    api.rows.append(recipe(3, title=rows[0]["title"]))
    assert (await call(service, {"title": rows[0]["title"]}, tool="get_recipe"))["code"] == "recipe_unclear"
    for args in ({}, {"recipe_id": 1, "title": rows[0]["title"]}):
        reads = api.reads
        assert (await call(service, args, tool="get_recipe"))["code"] == "invalid_arguments"
        assert api.reads == reads


def test_structured_metadata_unknowns_and_projection_do_not_mutate():
    raw = sample_recipes(1)[0]
    before = deepcopy(raw)
    view = summary(raw, include_metadata=True)
    assert view["menu_metadata"]["metadata"]["gesundheit_begruendung"] == METADATA["gesundheit_begruendung"]
    assert "notes" not in view and "ingredients" not in view
    projected = planning_recipe(raw)
    assert set(projected) == {"id", "title", "meal_types", "menu_metadata", "ingredients"}
    assert projected["ingredients"][0] == {
        k: raw["ingredients"][0][k] for k in ("name", "quantity", "category")
    }
    projected["ingredients"][0]["name"] = "Changed projection"
    assert raw == before
    unknown = summary(recipe(notes=None))
    assert all(unknown[k] is None for k in ("basisportionen", "gesundheit", "mag_nicht", "wiederaufwärmbar"))


async def test_large_collection_pages_are_bounded_and_revocation_still_blocks():
    rows = [recipe(i + 1) for i in range(501)]
    service, api, _ = await engine(rows)
    reply = await call(service, {"limit": 100, "offset": 500}, tool="list_recipes")
    assert reply["total"] == 501 and len(reply["data"]) == 1 and not reply["has_more"]
    denied = await call(service, {}, tool="list_recipes", authorized=lambda: False)
    assert denied["code"] == "not_allowed" and api.reads == 1
    api.read_hook = lambda _: None
    allowed = [True]
    api.read_hook = lambda _: allowed.__setitem__(0, False)
    denied = await call(service, {}, tool="list_recipes", authorized=lambda: allowed[0])
    assert denied["code"] == "not_allowed" and not api.writes


@pytest.mark.parametrize(
    "extra", [{"total": 23}, {"has_more": True}, {"pagination": {"next": 2}}, {"next": "cursor"}]
)
async def test_unfamiliar_rest_envelope_is_never_claimed_complete(extra):
    api = RecipeAPI(None)
    api._request = AsyncMock(return_value={"data": [recipe()], **extra})
    with pytest.raises(ShoppingFailure) as failure:
        await api.recipes()
    assert failure.value.code == "invalid_response"


@pytest.mark.parametrize("args", [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"detail": "everything"}])
async def test_read_schema_bounds_and_no_extra_permissions(args):
    selected = set(RECIPE_READS)
    state = Runtime(AsyncMock(), {}, lambda: selected)
    state.recipes = Recipes(API([recipe()]), None)
    try:
        assert (await state.call("list_recipes", args, call_id="bad", scope="s", owner="o"))[
            "code"
        ] == "invalid_arguments"
        assert not state.recipes.api.reads
        for name in RECIPE_READS:
            schema = probatio.to_openapi(state.parameters[name], openapi_version="3.1.0")
            assert schema["properties"]
        assert state.enabled() == RECIPE_READS
    finally:
        await state.close()


async def test_22_recipe_response_sizes_and_full_private_planning_sources():
    rows = sample_recipes()
    service, _, _ = await engine(rows)
    old = result([Recipes.present(row) for row in rows])
    compact = llm_payload(await call(service, {"limit": 100}, tool="list_recipes"))
    one = llm_payload(await call(service, {"title": rows[0]["title"]}, tool="get_recipe"))
    planner, api, _, _ = await planning_engine(config={"length_days": 7}, recipes=rows)
    public = await planner.run(
        "get_menu_planning_context", {"action": "create_period"}, "sizes", lambda: True, owner="o"
    )
    assert not public["isError"], public
    ident = public["data"]["context_id"]
    assert planner.contexts[ident]["recipes"] == rows
    assert "notes" not in public["data"]["recipes"][0]
    assert public["data"]["recipes"][0]["ingredients"]
    assert public["data"]["recipes"][0]["menu_metadata"]["metadata"]["basisportionen"] == 4
    old_plan = deepcopy(llm_payload(public))
    old_plan["data"]["recipes"] = [Recipes.present(row) for row in rows]

    def size(value):
        return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))

    sizes = {
        "old_full_list": size(old),
        "old_full_list_single_copy": size(llm_payload(old)),
        "new_compact_list_22": size(compact),
        "single_full_recipe": size(one),
        "old_planning_context": size(old_plan),
        "compact_planning_context": size(llm_payload(public)),
    }
    assert sizes["new_compact_list_22"] < sizes["old_full_list"] / 10
    assert sizes["compact_planning_context"] < sizes["old_planning_context"] / 3
    print("RECIPE_RESPONSE_BYTES=" + json.dumps(sizes, sort_keys=True))
    # A full-week save still calculates ingredient quantities from unprojected source data.
    reply = await planner.run(
        "save_menu_plan",
        {
            "context_id": ident,
            "assignments": [
                {"date": slot["date"], "recipe_id": i + 1, "kind": "cook"}
                for i, slot in enumerate(public["data"]["free_slots"])
            ],
        },
        "save",
        lambda: True,
        owner="o",
    )
    assert not reply["isError"], reply
    assert api.writes and api.writes[0][0][0]["ingredients"][0]["name"] == rows[0]["ingredients"][0]["name"]
    assert api.writes[0][0][0]["ingredients"][0]["quantity"] == "25 g"
    assert rows[0]["ingredients"][0]["quantity"] == "100 g"
