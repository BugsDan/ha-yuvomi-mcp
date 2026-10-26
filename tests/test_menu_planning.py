"""Menu configuration, model-selected plans, portions, durable barriers and REST contracts."""

import asyncio
from copy import deepcopy
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from test_journal import MemoryStore, make_journal
from test_recipes import METADATA, recipe

from custom_components.yuvomi_mcp.const import DEFAULT_TOOLS, MENU_TOOLS
from custom_components.yuvomi_mcp.journal import Journal, JournalError
from custom_components.yuvomi_mcp.meals_api import MealAPI, slot
from custom_components.yuvomi_mcp.menu_metadata import metadata, notes_block, scale
from custom_components.yuvomi_mcp.menu_planning import MenuPlanning
from custom_components.yuvomi_mcp.planning_config import DEFAULTS, PlanningStore, period, validate_config
from custom_components.yuvomi_mcp.planning_context import attendance
from custom_components.yuvomi_mcp.recipe_engine import Recipes
from custom_components.yuvomi_mcp.recipes import merged_notes
from custom_components.yuvomi_mcp.runtime import Runtime
from custom_components.yuvomi_mcp.shopping_api import ShoppingFailure


class Meals:
    validate = staticmethod(MealAPI.validate)

    def __init__(self):
        self.rows, self.writes = [], []
        self.error, self.hook, self.skipped = None, None, []

    async def meals(self, first, last):
        return deepcopy([r for r in self.rows if str(first) <= r["date"] <= str(last)])

    async def apply(self, assignments, key, *, replace=False):
        self.writes.append((deepcopy(assignments), key, replace))
        if self.hook:
            self.hook()
        if self.error:
            raise self.error
        if self.skipped:
            return {"data": [], "skipped": self.skipped}
        if replace:
            targets = {slot(b) for b in assignments}
            self.rows = [r for r in self.rows if slot(r) not in targets]
        rows = [{**deepcopy(b), "id": 100 + len(self.rows) + i} for i, b in enumerate(assignments)]
        self.rows.extend(rows)
        return {"data": deepcopy(rows), "skipped": []}


def meal(ident=7, when="2026-10-26", **kwargs):
    return {
        "id": ident,
        "date": when,
        "meal_type": "lunch",
        "title": "Alt",
        "notes": "Handnotiz",
        "recipe_id": 2,
        "recipe_url": None,
        "ingredients": [],
        **kwargs,
    }


async def engine(config=None, rows=None, journal=None, store=None, recipes=None):
    settings = PlanningStore(store or MemoryStore(), "http://host/mcp")
    await settings.load()
    if config is not None:
        await settings.update(
            {
                **deepcopy(DEFAULTS),
                "profiles": {"person": {"name": "Person", "days": [0, 1, 2, 3, 4]}},
                **config,
            }
        )
    elif not settings.data["revision"]:
        await settings.update(
            {
                **deepcopy(DEFAULTS),
                "length_days": 1,
                "anchor_date": "2026-10-26",
                "profiles": {"person": {"name": "Person", "days": [0, 1, 2, 3, 4]}},
            }
        )
    journal = journal or await make_journal()
    api = Meals()
    api.rows = deepcopy(rows or [])
    recipe_rows = recipes or [recipe(notes=merged_notes(None, {"metadata": METADATA}, creating=True))]
    rec = Recipes(SimpleNamespace(recipes=AsyncMock(return_value=recipe_rows)), journal)
    service = MenuPlanning(api, rec, settings, journal, today=lambda: date(2026, 10, 26))
    return service, api, settings, journal


async def context(service, **kwargs):
    result = await service.run(
        "get_menu_planning_context",
        {"action": "create_period", **kwargs},
        "context",
        lambda: True,
        owner="owner",
    )
    assert not result["isError"], result
    return result["data"]["context_id"]


async def save(service, ident, assignments=None, key="save", owner="owner"):
    return await service.run(
        "save_menu_plan",
        {
            "context_id": ident,
            "assignments": assignments
            if assignments is not None
            else [{"date": "2026-10-26", "recipe_id": 1, "kind": "cook"}],
        },
        key,
        lambda: True,
        owner=owner,
    )


async def test_menu_opt_in_and_no_incomplete_sync():
    state = Runtime(AsyncMock(), {}, lambda: set(DEFAULT_TOOLS))
    assert MENU_TOOLS <= state.tools.keys()
    assert not MENU_TOOLS & state.enabled()
    assert "sync_menu_plan_shopping" not in state.tools
    denied = await state.call("save_menu_plan", {}, call_id="x", scope="s", owner="o")
    assert denied["code"] == "not_allowed"
    await state.close()


@pytest.mark.parametrize(
    "change",
    [
        {"length_days": 0},
        {"days": []},
        {"timezone": "bad/zone"},
        {"anchor_date": "2026-02-30"},
        {"max_reheat_days": 3},
        {"rest_day": 0, "rest_excluded_days": [0]},
        {"repeat_exceptions": [9]},
        {"profiles": {"bad id": {"name": "x", "days": [0]}}},
        {
            "calendars": {
                "x": {
                    "entity": "calendar.test",
                    "profiles": ["missing"],
                    "match": "x",
                    "effect": "absent",
                    "priority": 1,
                }
            }
        },
    ],
)
def test_configuration_rejects_unsafe_values(change):
    with pytest.raises(ShoppingFailure):
        validate_config({**deepcopy(DEFAULTS), **change})


def test_arbitrary_period_and_recipe_base_not_meal_minimum():
    assert period(DEFAULTS, date(2026, 10, 25), "next") == (date(2026, 10, 28), date(2026, 11, 3))
    assert period({**DEFAULTS, "length_days": 10}, date(2026, 10, 31)) == (
        date(2026, 10, 31),
        date(2026, 11, 9),
    )
    assert (
        scale([{"name": "Öl", "quantity": "200 g", "category": "Öle"}], __import__("decimal").Decimal("0.5"))[
            0
        ]["quantity"]
        == "100 g"
    )
    with pytest.raises(ShoppingFailure):
        scale(
            [{"name": "Salz", "quantity": "nach Geschmack", "category": "Sonstiges"}],
            __import__("decimal").Decimal("0.5"),
        )


async def test_config_persists_revision_and_rejects_other_binding():
    s = MemoryStore()
    service, _, settings, _ = await engine(store=s)
    restored = PlanningStore(s, "http://host/mcp")
    await restored.load()
    assert restored.data == settings.data
    with pytest.raises(JournalError):
        await PlanningStore(s, "http://other/mcp").load()
    assert s.data == settings.data
    s.fail = True
    with pytest.raises(OSError):
        await settings.update(settings.data["config"])
    assert settings.broken
    await service.close()


async def test_view_loads_no_recipes_or_calendar_and_brief_output():
    service, api, _, _ = await engine(rows=[meal(), meal(8, "2026-10-27"), meal(9, "2026-10-28")])
    result = await service.run("get_menu_plan", {"date": "2026-10-26"}, "read", lambda: True)
    assert len(result["data"]["meals"]) == 1
    service.recipes.api.recipes.assert_not_called()
    assert not api.writes


async def test_initial_plan_scales_once_and_exact_context_retry():
    service, api, _, journal = await engine()
    ident = await context(service)
    response = await save(service, ident)
    assert not response["isError"], response
    assert api.rows[0]["ingredients"][0]["quantity"] == "50 g"
    assert metadata(api.rows[0]["notes"])["servings_total"] == 1
    assert response["data"]["shopping_transferred"] is False
    repeat = await save(service, ident, key="other")
    assert repeat["replayed"] and repeat["data"] == response["data"] and len(api.writes) == 1
    assert journal.data["journal"]["save"]["resource"] == "meals"


async def test_occupied_initial_slot_untouched_and_empty_plan_allowed():
    original = meal()
    service, api, _, _ = await engine(rows=[original])
    ident = await context(service)
    assert (await save(service, ident))["code"] == "occupied"
    result = await save(service, ident, [])
    assert result["data"]["status"] == "already_planned"
    assert api.rows == [original] and not api.writes


async def test_targeted_replace_preserves_other_day_and_free_notes():
    service, api, _, _ = await engine(rows=[meal(), meal(8, "2026-10-27")])
    ident = await context(
        service, action="replace_day", date="2026-10-26", requested_recipe="Curry – Variante mit Käse"
    )
    response = await save(service, ident)
    assert response["data"]["status"] == "replaced", response
    assert len(api.rows) == 2 and meal(8, "2026-10-27") in api.rows
    new = next(r for r in api.rows if r["date"] == "2026-10-26")
    assert new["id"] != 7 and new["notes"].startswith("Handnotiz")
    assert api.writes[0][2]


async def test_suggestion_never_writes_and_owner_is_bound():
    service, api, _, _ = await engine()
    ident = await context(service, action="suggest_day", date="2026-10-26")
    assert (await save(service, ident))["code"] == "not_allowed"
    assert (await save(service, ident, owner="other"))["code"] == "context_stale"
    assert not api.writes


@pytest.mark.parametrize(
    "change,code",
    [
        ("config", "context_stale"),
        ("meal", "concurrent_change"),
        ("recipe", "context_stale"),
        ("expires", "context_stale"),
    ],
)
async def test_freshness_and_no_write(change, code):
    service, api, settings, _ = await engine()
    ident = await context(service)
    if change == "config":
        await settings.update(settings.data["config"])
    if change == "meal":
        api.rows.append(meal())
    if change == "recipe":
        service.recipes.api.recipes.return_value[0]["title"] = "Geändert"
    if change == "expires":
        service.contexts[ident]["expires"] = -1
    assert (await save(service, ident))["code"] == code
    assert not api.writes


@pytest.mark.parametrize(
    "config,code",
    [
        ({"profiles": {"person": {"name": "Person", "days": [0], "dislikes": [1]}}}, "disliked_recipe"),
        ({"time_limits": {"0": 1}}, "time_limit"),
    ],
)
async def test_hard_rules(config, code):
    service, api, _, _ = await engine(config={"length_days": 1, "anchor_date": "2026-10-26", **config})
    ident = await context(service)
    assert (await save(service, ident))["code"] == code
    assert not api.writes


async def test_adjacent_period_repeat_is_not_rolling_days():
    service, api, _, _ = await engine(rows=[meal(7, "2026-10-25", recipe_id=1)])
    ident = await context(service)
    assert (await save(service, ident))["code"] == "repeat_forbidden"
    assert not api.writes


async def test_timeout_restart_barrier_and_read_only_reconcile():
    service, api, settings, journal = await engine()
    ident = await context(service)
    api.error = ShoppingFailure("execution_unconfirmed", "timeout", uncertain=True)
    response = await save(service, ident)
    assert response["code"] == "execution_unconfirmed"
    restored = Journal(journal.store, journal.binding)
    await restored.load()
    assert restored.data["journal"]["save"]["state"] == "unknown"
    new, other, _, _ = await engine(store=settings.store, journal=restored)
    ctx = await context(new)
    assert (await save(new, ctx))["code"] == "execution_unconfirmed"
    assert not other.writes
    expected = restored.data["journal"]["save"]["body"]["assignments"]
    other.rows = [{**b, "id": i + 90} for i, b in enumerate(expected)]
    observed = await new.reconcile("save")
    assert "beobachtet" in observed["message"]
    assert not other.writes and restored.data["journal"]["save"]["state"] == "observed"
    assert (await save(new, ident))["code"] == "context_stale"


async def test_parallel_same_context_writes_once():
    service, api, _, _ = await engine()
    ident = await context(service)
    a, b = await asyncio.gather(save(service, ident, key="a"), save(service, ident, key="b"))
    assert a["data"] == b["data"] and b["replayed"] and len(api.writes) == 1


async def test_storage_failure_happens_before_network():
    service, api, _, journal = await engine()
    ident = await context(service)
    journal.store.fail = True
    assert (await save(service, ident))["isError"]
    assert not api.writes


async def test_partial_response_blocks_retry_without_false_success():
    service, api, _, journal = await engine()
    ident = await context(service)
    api.skipped = [0]
    response = await save(service, ident)
    assert (
        response["code"] == "execution_unconfirmed" and journal.data["journal"]["save"]["state"] == "unknown"
    )
    assert (await save(service, ident, key="again"))["code"] == "execution_unconfirmed"
    assert len(api.writes) == 1


def test_calendar_allowlist_priorities_and_exclusive_all_day_end():
    config = deepcopy(DEFAULTS)
    config["profiles"] = {"p": {"name": "Kind", "days": [0], "reheat_days": []}}
    config["calendar_entities"] = ["calendar.school"]
    rule = {
        "entity": "calendar.school",
        "profiles": ["p"],
        "match": "Schule",
        "effect": "absent",
        "priority": 2,
    }
    config["calendars"] = {"a": rule}
    validate_config(config)
    events = {"calendar.school": [{"summary": "Schule", "start": "2026-10-26", "end": "2026-10-27"}]}
    result = attendance(config, date(2026, 10, 26), date(2026, 10, 27), events)
    assert not result["2026-10-26"]["p"]["present"]
    config["calendars"]["b"] = {**rule, "effect": "present"}
    with pytest.raises(ShoppingFailure):
        attendance(config, date(2026, 10, 26), date(2026, 10, 26), events)
    with pytest.raises(ShoppingFailure):
        attendance(config, date(2026, 10, 26), date(2026, 10, 26), {})


async def test_three_today_two_children_tomorrow_scaling_and_no_reheat_ingredients():
    config = {
        "anchor_date": "2026-10-28",
        "length_days": 2,
        "profiles": {
            "parent": {"name": "Elternteil", "days": [2]},
            "a": {"name": "Kind A", "days": [2], "reheat_days": [3]},
            "b": {"name": "Kind B", "days": [2], "reheat_days": [3]},
        },
    }
    service, api, _, _ = await engine(config=config)
    ident = await context(service, start_date="2026-10-28")
    assignments = [
        {
            "date": "2026-10-28",
            "recipe_id": 1,
            "kind": "cook",
            "extra_servings": [
                {"profile_id": "a", "date": "2026-10-29", "servings": 1},
                {"profile_id": "b", "date": "2026-10-29", "servings": 1},
            ],
        },
        {"date": "2026-10-29", "recipe_id": 1, "kind": "reheat", "source_date": "2026-10-28"},
    ]
    response = await save(service, ident, assignments)
    assert not response["isError"], response
    cook, reheat = api.rows
    assert metadata(cook["notes"])["servings_total"] == 5
    assert cook["ingredients"][0]["quantity"] == "250 g"
    assert reheat["recipe_id"] is None and reheat["ingredients"] == []
    assert metadata(reheat["notes"])["source_date"] == "2026-10-28"
    assert metadata(reheat["notes"])["servings_total"] == 2
    assert len(service.recipes.api.recipes.return_value[0]["ingredients"]) == 1
    assert service.recipes.api.recipes.return_value[0]["ingredients"][0]["quantity"] == "200 g"


@pytest.mark.parametrize("bad", ["[yuvomi-menu:v2]x", "[yuvomi-menu:v1]bad[/yuvomi-menu]"])
def test_bad_metadata_never_overwritten(bad):
    with pytest.raises(ShoppingFailure):
        notes_block(bad, {"v": 1, "kind": "cook"}, "Summary")


async def test_meal_adapter_complete_weeks_and_fixed_write():
    api = MealAPI(None)
    api._request = AsyncMock(
        side_effect=[
            {"weekStart": "2026-10-26", "weekEnd": "2026-11-01", "data": [meal()]},
            {"weekStart": "2026-11-02", "weekEnd": "2026-11-08", "data": []},
        ]
    )
    rows = await api.meals("2026-10-28", "2026-11-03")
    assert rows == [] and api._request.await_count == 2
    assert api._request.await_args_list[1].args == ("GET", "/api/v1/meals?week=2026-11-02")
    api._request = AsyncMock(return_value={"data": []})
    await api.apply([], "key")
    api._request.assert_awaited_once_with(
        "POST", "/api/v1/meals/apply-plan", body={"assignments": [], "skip_occupied": True}, key="key"
    )


async def test_repeat_exception_for_resten_and_no_stock_proof_required():
    service, api, _, _ = await engine(
        config={"length_days": 1, "anchor_date": "2026-10-26", "rest_recipe_id": 1, "repeat_exceptions": [1]},
        rows=[meal(7, "2026-10-25", recipe_id=1)],
    )
    ident = await context(service)
    response = await save(service, ident, [{"date": "2026-10-26", "recipe_id": 1, "kind": "rest"}])
    assert not response["isError"], response
    assert len(api.writes) == 1


async def test_multi_slot_and_duplicate_assignments_rejected_before_post():
    service, api, _, _ = await engine(rows=[meal(), meal(8)])
    ident = await context(service, action="replace_day", date="2026-10-26")
    assert (await save(service, ident))["code"] == "occupied_unclear"
    duplicate = [{"date": "2026-10-26", "recipe_id": 1, "kind": "cook"}] * 2
    assert (await save(service, ident, duplicate))["code"] == "invalid_plan"
    assert not api.writes


async def test_precise_day_context_has_only_requested_recipe_and_no_all_period_rows():
    one = recipe(notes=merged_notes(None, {"metadata": METADATA}, creating=True))
    two = recipe(ident=2, title="Anderes Rezept", notes=one["notes"])
    service, api, _, _ = await engine(recipes=[one, two])
    ident = await context(service, action="replace_day", date="2026-10-26", requested_recipe=one["title"])
    assert len(service.contexts[ident]["public"]["recipes"]) == 1
    assert not api.writes


async def test_authorization_rechecked_immediately_before_io():
    service, api, _, _ = await engine()
    ident = await context(service)
    allowed = {"value": True}
    original = service.journal.store.async_save

    async def revoke_after_persist(data):
        await original(data)
        allowed["value"] = False

    service.journal.store.async_save = revoke_after_persist
    result = await service.run(
        "save_menu_plan",
        {"context_id": ident, "assignments": [{"date": "2026-10-26", "recipe_id": 1, "kind": "cook"}]},
        "write",
        lambda: allowed["value"],
        owner="owner",
    )
    assert result["code"] == "not_allowed" and not api.writes


async def test_definite_rejection_is_not_unknown_but_timeout_is():
    service, api, _, journal = await engine()
    ident = await context(service)
    api.error = ShoppingFailure("shopping_rejected", "Token-Rechte fehlen")
    result = await save(service, ident)
    assert result["code"] == "shopping_rejected" and journal.data["journal"]["save"]["state"] == "failed"


async def test_lost_journal_after_server_success_never_claims_success():
    service, api, _, journal = await engine()
    ident = await context(service)
    api.hook = lambda: setattr(journal.store, "fail", True)
    result = await save(service, ident)
    assert result["code"] == "execution_unconfirmed"
    assert journal.broken and len(api.writes) == 1


async def test_timed_out_day_replacement_after_commit_can_only_be_observed():
    service, api, _, journal = await engine(rows=[meal()])
    ident = await context(service, action="replace_day", date="2026-10-26")
    original = api.apply

    async def commit_then_timeout(*args, **kwargs):
        await original(*args, **kwargs)
        raise ShoppingFailure("execution_unconfirmed", "timeout", uncertain=True)

    api.apply = commit_then_timeout
    result = await save(service, ident)
    assert result["code"] == "execution_unconfirmed" and len(api.writes) == 1
    observed = await service.reconcile("save")
    assert "beobachtet" in observed["message"]
    assert journal.data["journal"]["save"]["state"] == "observed"
    assert len(api.writes) == 1


def test_dst_invalid_local_mealtime_requires_clarification():
    config = {**deepcopy(DEFAULTS), "meal_time": "02:30", "profiles": {"p": {"name": "P", "days": [6]}}}
    with pytest.raises(ShoppingFailure):
        attendance(config, date(2026, 3, 29), date(2026, 3, 29), {})
    with pytest.raises(ShoppingFailure):
        attendance(config, date(2026, 10, 25), date(2026, 10, 25), {})


def test_only_highest_calendar_priority_conflicts_are_relevant():
    config = deepcopy(DEFAULTS)
    config["profiles"] = {"p": {"name": "P", "days": [0]}}
    rule = {"entity": "calendar.test", "profiles": ["p"], "match": "Match", "effect": "absent", "priority": 1}
    config["calendars"] = {
        "low1": rule,
        "low2": {**rule, "effect": "present"},
        "high": {**rule, "priority": 2, "effect": "present"},
    }
    events = {"calendar.test": [{"summary": "Match", "start": "2026-10-26", "end": "2026-10-27"}]}
    assert attendance(config, date(2026, 10, 26), date(2026, 10, 26), events)["2026-10-26"]["p"]["present"]


async def test_persistent_existing_source_can_feed_reheat_without_new_ingredients():
    config = {
        "length_days": 1,
        "anchor_date": "2026-10-29",
        "profiles": {"a": {"name": "Kind A", "days": [], "reheat_days": [3]}},
        "emergency_recipe_ids": [1],
        "repeat_exceptions": [1],
    }
    block = {
        "v": 1,
        "kind": "cook",
        "recipe_id": 1,
        "date": "2026-10-28",
        "meal_type": "lunch",
        "servings_now": 1,
        "servings_total": 2,
        "extras": [{"profile_id": "a", "date": "2026-10-29", "meal_type": "lunch", "servings": 1}],
    }
    source = meal(7, "2026-10-28", recipe_id=1, notes=notes_block(None, block, "2 Portionen"))
    service, api, _, _ = await engine(config=config, rows=[source])
    ident = await context(service, start_date="2026-10-29")
    reply = await save(
        service,
        ident,
        [{"date": "2026-10-29", "recipe_id": 1, "kind": "reheat", "source_date": "2026-10-28"}],
    )
    assert not reply["isError"], reply
    assert source in api.rows
    target = next(r for r in api.rows if r["date"] == "2026-10-29")
    assert target["recipe_id"] is None and target["ingredients"] == []


async def test_foreign_execution_key_not_overwritten():
    from test_journal import record

    service, api, _, journal = await engine()
    ident = await context(service)
    old = record(state="done")
    old["id"] = "save"
    await journal.change(lambda data: data["journal"].update(save=old))
    assert (await save(service, ident))["code"] == "storage_error"
    assert journal.data["journal"]["save"] == old and not api.writes


@pytest.mark.parametrize("days", [0, 3])
async def test_reheat_distance_is_never_guessed_or_extended(days):
    target = date(2026, 10, 26)
    source = target - timedelta(days=days)
    config = {
        "length_days": 1,
        "anchor_date": str(target),
        "profiles": {"a": {"name": "A", "days": [], "reheat_days": [0]}},
        "emergency_recipe_ids": [1],
        "repeat_exceptions": [1],
    }
    block = {
        "v": 1,
        "kind": "cook",
        "recipe_id": 1,
        "extras": [{"profile_id": "a", "date": str(target), "meal_type": "lunch", "servings": 1}],
    }
    original = meal(7, str(source), recipe_id=1, notes=notes_block(None, block, "Planned extra"))
    service, api, _, _ = await engine(config=config, rows=[original])
    ident = await context(service, action="replace_day", date=str(target))
    reply = await save(
        service, ident, [{"date": str(target), "recipe_id": 1, "kind": "reheat", "source_date": str(source)}]
    )
    assert reply["code"] == "invalid_plan" and not api.writes
    assert api.rows == [original]


def test_fixed_resten_day_requires_selected_recipe():
    with pytest.raises(ShoppingFailure):
        validate_config({**deepcopy(DEFAULTS), "rest_day": 2})


async def test_revision_change_during_context_fetch_does_not_bind_old_rules_to_new_revision():
    service, api, settings, _ = await engine()
    original = service.recipes.api.recipes.return_value

    async def changed():
        await settings.update({**settings.data["config"], "time_limits": {"0": 0}})
        return original

    service.recipes.api.recipes.side_effect = changed
    reply = await service.run(
        "get_menu_planning_context", {"action": "create_period"}, "ctx", lambda: True, owner="owner"
    )
    assert reply["code"] == "context_stale" and not api.writes and not service.contexts


async def test_revision_change_after_durable_prepare_stops_before_http():
    service, api, settings, journal = await engine()
    ident = await context(service)
    original = journal.store.async_save

    async def changed(data):
        await original(data)
        await settings.update({**settings.data["config"], "time_limits": {"0": 0}})

    journal.store.async_save = changed
    reply = await save(service, ident)
    assert reply["code"] == "context_stale" and not api.writes
    assert journal.data["journal"]["save"]["state"] == "failed"
