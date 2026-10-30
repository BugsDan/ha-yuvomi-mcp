"""Preview uses the same hard checks as saving; rejected forms and plans never change data."""

from copy import deepcopy
from unittest.mock import AsyncMock

import pytest
from test_menu_planning import context, engine, meal, save
from test_recipes import METADATA, recipe

from custom_components.yuvomi_mcp.const import MENU_TOOLS
from custom_components.yuvomi_mcp.planning_config import DEFAULTS, PlanningStore, validate_config
from custom_components.yuvomi_mcp.planning_context import PLANNING_PROMPT
from custom_components.yuvomi_mcp.planning_form import form_candidate, form_values
from custom_components.yuvomi_mcp.recipes import merged_notes
from custom_components.yuvomi_mcp.runtime import Runtime
from custom_components.yuvomi_mcp.shopping_api import ShoppingFailure


@pytest.mark.parametrize("ident", ["Ehemann", "Ehefrau", "Kind 1", "Kind 2", "1kind"])
def test_invalid_profile_id_named_and_input_untouched(ident):
    value = {**deepcopy(DEFAULTS), "profiles": {ident: {"name": "Kind 1", "days": [0]}}}
    before = deepcopy(value)
    with pytest.raises(ShoppingFailure) as error:
        validate_config(value)
    assert error.value.code == "invalid_planning_config"
    assert error.value.field == "profiles" and ident in str(error.value)
    assert "kind_1" in str(error.value) and value == before


def test_form_roundtrip_retains_every_field_and_never_aliases_store():
    saved = deepcopy(DEFAULTS)
    submitted = form_values(saved)
    submitted.update(
        profiles={"Kind 1": {"name": "Kind 1", "days": [0], "reheat_days": [1]}},
        timezone="invalid/zone",
        time_limits={"0": 25},
        calendars={"new": {"entity": "calendar.school"}},
        calendar_entities=["calendar.school"],
        length_days=14.0,
    )
    submitted["advanced"]["days"] = [0, 2, 4]
    before = deepcopy(submitted)
    defaults = form_values(saved, submitted)
    assert defaults == submitted
    candidate = form_candidate(saved, defaults)
    assert candidate["length_days"] == 14 and type(candidate["length_days"]) is int
    with pytest.raises(ShoppingFailure):
        validate_config(candidate)
    assert form_values(saved, before) == before
    candidate["profiles"].clear()
    assert submitted == before and saved == DEFAULTS


@pytest.mark.parametrize(
    "change,field",
    [
        ({"time_limits": {"7": 10}}, "time_limits"),
        ({"anchor_date": "not-a-date"}, "anchor_date"),
        ({"timezone": "bad/zone"}, "timezone"),
        ({"rest_day": 1}, "rest_recipe_id"),
    ],
)
def test_config_errors_identify_relevant_field(change, field):
    with pytest.raises(ShoppingFailure) as error:
        validate_config({**deepcopy(DEFAULTS), **change})
    assert error.value.field == field


async def preview(service, ident, assignments, **kwargs):
    return await service.run(
        "save_menu_plan",
        {"context_id": ident, "assignments": assignments, "validate_only": True},
        "preview",
        lambda: True,
        owner=kwargs.get("owner", "owner"),
    )


async def test_period_proposal_is_write_bound_and_validates_without_journal_changes():
    service, api, _, journal = await engine()
    ident = await context(service, action="suggest_period")
    assert service.contexts[ident]["public"]["validation_status"] == "context_only"
    assert service.contexts[ident]["public"]["write_permitted"] is False
    assignments = [{"date": "2026-10-26", "recipe_id": 1, "kind": "cook"}]
    original = deepcopy(journal.data)
    checked = await preview(service, ident, assignments)
    assert checked["data"]["status"] == "validated_preview"
    assert checked["data"]["saved"] is False and checked["data"]["validation_status"] == "validated"
    assert checked["data"]["write_permitted"] is False
    assert checked["data"]["meals"][0]["servings_total"] == 1
    assert checked["data"]["meals"][0]["servings_now"] == 1
    assert (await save(service, ident, assignments))["code"] == "not_allowed"
    assert not api.writes and journal.data == original
    assert (await preview(service, ident, assignments, owner="other"))["code"] == "context_stale"


async def test_reheat_preview_three_present_plus_two_extras_is_five_not_recipe_base_per_person():
    config = {
        "anchor_date": "2026-10-28",
        "length_days": 2,
        "profiles": {
            "parent": {"name": "Elternteil", "days": [2]},
            "kind_1": {"name": "Kind 1", "days": [2], "reheat_days": [3]},
            "kind_2": {"name": "Kind 2", "days": [2], "reheat_days": [3]},
        },
    }
    service, api, _, journal = await engine(config=config)
    ident = await context(service, action="suggest_period", start_date="2026-10-28")
    assignments = [
        {
            "date": "2026-10-28",
            "recipe_id": 1,
            "kind": "cook",
            "extra_servings": [
                {"profile_id": "kind_1", "date": "2026-10-29", "servings": 1},
                {"profile_id": "kind_2", "date": "2026-10-29", "servings": 1},
            ],
        },
        {"date": "2026-10-29", "recipe_id": 1, "kind": "reheat", "source_date": "2026-10-28"},
    ]
    reply = await preview(service, ident, assignments)
    assert not reply["isError"], reply
    cook, reheat = reply["data"]["meals"]
    assert cook["servings_now"] == 3 and cook["servings_total"] == 5
    assert reheat["servings_total"] == 2 and reheat["source_date"] == "2026-10-28"
    assert not api.writes and not journal.data["journal"]
    for bad in ("not_reheatable", "missing_extra", "duplicate_extra"):
        changed = deepcopy(assignments)
        if bad == "not_reheatable":
            raw = service.contexts[ident]["recipes"][0]
            raw["notes"] = merged_notes(
                None, {"metadata": {**METADATA, "wiederaufwärmbar": False}}, creating=True
            )
        elif bad == "missing_extra":
            changed[0]["extra_servings"].pop()
        else:
            changed[0]["extra_servings"].append(changed[0]["extra_servings"][0])
        rejected = await preview(service, ident, changed)
        assert rejected["isError"] and not api.writes
        service.contexts[ident]["recipes"][0] = deepcopy(service.recipes.api.recipes.return_value[0])


@pytest.mark.parametrize("reference", ["kind_1", "Kind 1"])
async def test_dislikes_block_by_stable_id_or_display_name(reference):
    notes = merged_notes(None, {"metadata": {**METADATA, "mag_nicht": [reference]}}, creating=True)
    service, api, _, journal = await engine(
        config={
            "length_days": 1,
            "anchor_date": "2026-10-26",
            "profiles": {"kind_1": {"name": "Kind 1", "days": [0]}},
        },
        recipes=[recipe(notes=notes)],
    )
    ident = await context(service)
    assert (await save(service, ident))["code"] == "disliked_recipe"
    assert not api.writes and not journal.data["journal"]


async def test_unknown_dislike_identity_requires_clarification():
    notes = merged_notes(None, {"metadata": {**METADATA, "mag_nicht": ["unknown_person"]}}, creating=True)
    service, api, _, _ = await engine(recipes=[recipe(notes=notes)])
    ident = await context(service)
    assert (await save(service, ident))["code"] == "profile_unclear"
    assert not api.writes


async def test_ambiguous_display_name_does_not_guess_a_profile():
    notes = merged_notes(None, {"metadata": {**METADATA, "mag_nicht": ["Kind"]}}, creating=True)
    service, api, _, _ = await engine(
        config={
            "length_days": 1,
            "anchor_date": "2026-10-26",
            "profiles": {"a": {"name": "Kind", "days": [0]}, "b": {"name": "Kind", "days": [0]}},
        },
        recipes=[recipe(notes=notes)],
    )
    ident = await context(service)
    assert (await save(service, ident))["code"] == "profile_unclear"
    assert not api.writes


async def test_suggestion_respects_existing_slots_and_current_period_variety():
    service, api, _, journal = await engine(
        config={"length_days": 2, "anchor_date": "2026-10-26"}, rows=[meal(recipe_id=1)]
    )
    ident = await context(service, action="suggest_period")
    assert (await preview(service, ident, [{"date": "2026-10-26", "recipe_id": 1, "kind": "cook"}]))[
        "code"
    ] == "occupied"
    assert (await preview(service, ident, [{"date": "2026-10-27", "recipe_id": 1, "kind": "cook"}]))[
        "code"
    ] == "repeat_forbidden"
    assert not api.writes and not journal.data["journal"]


async def test_repeated_cooking_within_period_rejected_but_explicit_exception_remains():
    service, api, settings, _ = await engine(config={"anchor_date": "2026-10-26", "length_days": 2})
    ident = await context(service)
    assignments = [{"date": day, "recipe_id": 1, "kind": "cook"} for day in ("2026-10-26", "2026-10-27")]
    assert (await save(service, ident, assignments))["code"] == "repeat_forbidden"
    assert not api.writes
    await settings.update({**settings.data["config"], "emergency_recipe_ids": [1], "repeat_exceptions": [1]})
    service.contexts.clear()
    ident = await context(service)
    assert not (await save(service, ident, assignments))["isError"]


async def test_time_violation_on_later_day_rejects_whole_plan_before_writing():
    notes = merged_notes(None, {"metadata": METADATA}, creating=True)
    service, api, _, journal = await engine(
        config={"anchor_date": "2026-10-26", "length_days": 2, "time_limits": {"1": 10}},
        recipes=[recipe(notes=notes), recipe(2, title="Zweite Variante", notes=notes)],
    )
    ident = await context(service)
    assignments = [
        {"date": "2026-10-26", "recipe_id": 1, "kind": "cook"},
        {"date": "2026-10-27", "recipe_id": 2, "kind": "cook"},
    ]
    assert (await save(service, ident, assignments))["code"] == "time_limit"
    assert not api.writes and not journal.data["journal"]


@pytest.mark.parametrize(
    "args",
    [
        {"period": "current", "start_date": "2026-10-26"},
        {"period": "next", "date": "2026-10-26"},
        {"date": "2026-10-26", "start_date": "2026-10-26"},
    ],
)
async def test_exclusive_dates_explain_how_to_correct_without_writes(args):
    service, api, _, _ = await engine()
    reply = await service.run(
        "get_menu_planning_context", {"action": "create_period", **args}, "bad", lambda: True
    )
    assert reply["code"] == "date_unclear" and "schließen sich aus" in reply["data"]["message"]
    assert not api.writes and not service.contexts


async def test_runtime_validation_only_does_not_cache_a_stale_preview():
    from test_planning_cooking import cooking
    from test_planning_cooking import settings as weekly_settings

    config = weekly_settings()
    config.update(length_days=1)
    service, api, settings, _ = await cooking(config)
    state = Runtime(AsyncMock(), {}, lambda: set(MENU_TOOLS))
    state.planning = service
    try:
        reply = await state.call(
            "get_menu_planning_context", {"action": "suggest_period"}, call_id="ctx", scope="s", owner="o"
        )
        ident = reply["data"]["context_id"]
        args = {
            "context_id": ident,
            "validate_only": True,
            "assignments": [{"date": "2026-10-26", "recipe_id": 1, "kind": "cook"}],
        }
        first = await state.call("save_menu_plan", args, call_id="v", scope="s", owner="o")
        assert first["data"]["status"] == "validated_preview"
        assert not state._cache
        await settings.update(settings.data["config"])
        again = await state.call("save_menu_plan", args, call_id="v", scope="s", owner="o")
        assert again["code"] == "context_stale" and not api.writes
    finally:
        await state.close()


async def test_existing_config_and_revision_survive_rejected_edit_and_reload():
    service, _, settings, _ = await engine()
    original = deepcopy(settings.data)
    with pytest.raises(ShoppingFailure):
        await settings.update(
            {**settings.data["config"], "profiles": {"Kind 1": {"name": "Kind 1", "days": [0]}}}
        )
    restored = PlanningStore(settings.store, settings.binding)
    await restored.load()
    assert restored.data == original and settings.data == original


def test_central_prompt_separates_ideas_context_validation_and_storage():
    assert "generic recipe inspiration" in PLANNING_PROMPT
    for text in (
        "FIRST",
        "not a checked plan",
        "validate_only=true",
        "3 present portions + 2",
        "period/start_date/date",
    ):
        assert text in PLANNING_PROMPT
