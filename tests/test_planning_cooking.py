"""1.4.5 cooking-only planning: deterministic portions, no reheat events, durable writes."""

import asyncio
from copy import deepcopy
from datetime import date
from unittest.mock import AsyncMock

import pytest
from test_menu_planning import context, engine, meal
from test_recipes import METADATA, recipe

from custom_components.yuvomi_mcp.const import MENU_TOOLS
from custom_components.yuvomi_mcp.journal import Journal
from custom_components.yuvomi_mcp.meals_api import MealAPI
from custom_components.yuvomi_mcp.menu_metadata import metadata, notes_block
from custom_components.yuvomi_mcp.menu_tools import menu_tools
from custom_components.yuvomi_mcp.planning_config import family_defaults, validate_config
from custom_components.yuvomi_mcp.planning_context import attendance
from custom_components.yuvomi_mcp.runtime import Runtime
from custom_components.yuvomi_mcp.shopping_api import ShoppingFailure


def settings():
    config = family_defaults()
    config.update(anchor_date="2026-10-26", length_days=7)
    config["profiles"]["member_01"]["fallback"] = "absent"  # explicit test assumption
    config["profiles"]["member_02"]["user_id"] = 11
    config["profiles"]["member_01"]["user_id"] = 12
    return config


def recipes():
    return [
        recipe(
            i,
            title=f"Gericht {i} – Variante",
            notes=__import__("custom_components.yuvomi_mcp.recipes", fromlist=["merged_notes"]).merged_notes(
                None, {"metadata": {**METADATA, "zubereitungszeit_min": 20}}, creating=True
            ),
        )
        for i in range(1, 8)
    ]


async def cooking(config=None, rows=None, recipe_rows=None, **kwargs):
    service, api, store, journal = await engine(
        config=config or settings(), rows=rows, recipes=recipe_rows or recipes(), **kwargs
    )
    api.members = AsyncMock(
        return_value={11: {"id": 11, "name": "Cornelia"}, 12: {"id": 12, "name": "Daniel"}}
    )
    return service, api, store, journal


def assignments():
    return [{"date": f"2026-10-{d}", "recipe_id": i} for i, d in enumerate(range(26, 31), 1)]


def selections():
    return [
        {"date": "2026-10-29", "profile_id": p, "source_date": "2026-10-28"}
        for p in ("member_03", "member_04")
    ]


async def submit(service, ident, rows=None, execution_key="save", **kwargs):
    return await service.run(
        "save_menu_plan",
        {"context_id": ident, "assignments": assignments() if rows is None else rows, **kwargs},
        execution_key,
        lambda: True,
        owner="owner",
    )


def test_defaults_have_requested_people_stable_identity_and_no_invented_presence():
    c = family_defaults()
    assert [p["name"] for p in c["profiles"].values()] == ["Daniel", "Cornelia", "Aaron", "Aliyah"]
    assert all(p["user_id"] is None for p in c["profiles"].values())
    assert c["profiles"]["member_01"]["fallback"] == "unknown"
    assert [c["week"][str(d)]["max_minutes"] for d in range(5)] == [75, 60, 40, 60, 25]
    changed = deepcopy(c)
    changed["profiles"]["member_03"]["name"] = "Neuer Anzeigename"
    assert validate_config(changed)["week"]["1"]["prepared"] == ["member_03"]


async def test_full_week_fresh_plus_one_and_two_extras_without_reheat_events():
    service, api, _, journal = await cooking()
    original = deepcopy(service.recipes.api.recipes.return_value)
    ident = await context(service)
    ambiguous = await submit(service, ident)
    assert ambiguous["code"] == "reheat_source_unclear" and "2026-10-27" in str(ambiguous)
    assert ambiguous["data"]["source_dates"] == ["2026-10-27", "2026-10-28"]
    assert not api.writes and not journal.data["journal"]
    checked = await submit(service, ident, reheat_sources=selections(), validate_only=True)
    assert checked["data"]["status"] == "validated_preview" and not api.writes
    response = await submit(service, ident, reheat_sources=selections())
    assert not response["isError"], response
    assert len(api.rows) == 5 and len(api.writes) == 1
    blocks = {r["date"]: metadata(r["notes"]) for r in api.rows}
    assert [blocks[f"2026-10-{d}"]["servings_now"] for d in range(26, 31)] == [1, 2, 3, 1, 2]
    assert blocks["2026-10-26"]["servings_total"] == 2
    assert blocks["2026-10-28"]["servings_total"] == 5
    assert len(blocks["2026-10-28"]["extras"]) == 2
    assert all(b["kind"] == "cook" for b in blocks.values())
    assert api.rows[2]["ingredients"][0]["quantity"] == "250 g"
    assert "5 Portionen" in api.rows[2]["title"] and "Aliyah" in api.rows[2]["title"]
    assert api.rows[2]["recipe_id"] == 3 and api.rows[2]["cook_user_id"] == 11
    assert original == service.recipes.api.recipes.return_value
    replay = await submit(service, ident, reheat_sources=selections())
    assert replay["replayed"] and len(api.writes) == 1


@pytest.mark.parametrize("source", ["2026-10-27", "2026-10-28"])
async def test_one_or_two_day_sources_and_no_duplicate_consumption(source):
    service, api, _, _ = await cooking()
    ident = await context(service)
    choice = [
        {"date": "2026-10-29", "profile_id": p, "source_date": source} for p in ("member_03", "member_04")
    ]
    response = await submit(service, ident, reheat_sources=choice)
    assert not response["isError"], response
    extras = [e for r in api.rows for e in metadata(r["notes"])["extras"]]
    assert len(extras) == len({(e["date"], e["profile_id"]) for e in extras}) == 3
    block = metadata(next(r for r in api.rows if r["date"] == source)["notes"])
    assert len(block["extras"]) == 2


async def test_takeaway_only_day_has_no_calendar_record_and_is_readable():
    c = settings()
    c["week"]["1"]["fresh"] = []
    service, api, _, _ = await cooking(c)
    ident = await context(service)
    rows = [a for a in assignments() if a["date"] != "2026-10-27"]
    result = await submit(service, ident, rows)
    assert not result["isError"], result
    assert len(api.rows) == 4 and not any(r["date"] == "2026-10-27" for r in api.rows)
    read = await service.run("get_menu_plan", {"date": "2026-10-27"}, "read", lambda: True)
    assert read["data"]["meals"] == []
    assert read["data"]["prepared_meals"][0]["profile_id"] == "member_03"


async def test_unknown_daniel_requires_explicit_assumption_not_guessed():
    c = settings()
    c["profiles"]["member_01"]["fallback"] = "unknown"
    service, api, _, _ = await cooking(c)
    response = await service.run("get_menu_planning_context", {"action": "create_period"}, "c", lambda: True)
    assert response["code"] == "attendance_unclear" and not api.writes


async def test_target_day_needs_no_unrelated_future_fresh_attendance_answer():
    c = settings()
    c["profiles"]["member_01"]["fallback"] = "unknown"
    service, api, _, _ = await cooking(c)
    ident = await context(
        service,
        action="create_day",
        date="2026-10-26",
        overrides=[{"date": "2026-10-26", "profile_id": "member_01", "present": True}],
    )
    response = await submit(service, ident, [{"date": "2026-10-26", "recipe_id": 1}])
    assert not response["isError"], response
    assert metadata(api.rows[0]["notes"])["servings_total"] == 3  # two fresh plus Aaron Tuesday


async def test_period_overrides_presence_extra_amount_cook_recipe_and_time_are_not_persisted():
    service, api, store, _ = await cooking()
    before = deepcopy(store.data)
    overrides = [
        {"date": "2026-10-26", "profile_id": "member_01", "present": True},
        {"date": "2026-10-27", "profile_id": "member_03", "reheat": False},
        {"date": "2026-10-29", "profile_id": "member_04", "portion": 2},
        {"date": "2026-10-30", "cook": "member_01", "max_minutes": 1, "recipe_id": 5},
    ]
    ident = await context(service, overrides=overrides)
    response = await submit(service, ident, reheat_sources=selections())
    assert not response["isError"], response
    assert metadata(api.rows[0]["notes"])["servings_total"] == 2
    assert metadata(api.rows[2]["notes"])["servings_total"] == 6
    assert api.rows[4]["cook_user_id"] == 12 and store.data == before


@pytest.mark.parametrize(
    "overrides,code",
    [
        ([{"date": "2026-10-26", "profile_id": "missing", "present": True}], "profile_unclear"),
        (
            [
                {"date": "2026-10-26", "profile_id": "member_01", "present": True},
                {"date": "2026-10-26", "profile_id": "member_01", "present": False},
            ],
            "invalid_override",
        ),
        ([{"date": "2026-11-03", "cook": None}], "invalid_override"),
    ],
)
async def test_bad_overrides_fail_before_writing(overrides, code):
    service, api, _, _ = await cooking()
    result = await service.run(
        "get_menu_planning_context", {"action": "create_period", "overrides": overrides}, "ctx", lambda: True
    )
    assert result["code"] == code and not api.writes


def calendar_config():
    c = settings()
    c["calendars"] = {
        "home": {
            "entity": "calendar.work",
            "profiles": ["member_01"],
            "match": "Homeoffice",
            "effect": "present",
            "priority": 10,
        }
    }
    c["calendar_entities"] = ["calendar.work"]
    c["week"]["0"]["calendars"] = ["calendar.work"]
    return c


def test_calendar_only_selected_day_and_explicit_semantics():
    c = calendar_config()
    events = {"calendar.work": [{"summary": "Homeoffice", "start": "2026-10-26", "end": "2026-10-28"}]}
    facts = attendance(c, date(2026, 10, 26), date(2026, 10, 27), events)
    assert facts["2026-10-26"]["member_01"]["present"]
    assert not facts["2026-10-27"]["member_01"]["present"]
    events["calendar.work"][0]["summary"] = "Anderer Termin"
    assert not attendance(c, date(2026, 10, 26), date(2026, 10, 26), events)["2026-10-26"]["member_01"][
        "present"
    ]


@pytest.mark.parametrize("code", ["calendar_not_allowed", "attendance_unclear"])
async def test_missing_or_denied_calendar_is_not_invented(code):
    service, api, _, _ = await cooking(calendar_config())
    service.calendar_reader = AsyncMock(side_effect=ShoppingFailure(code, "Kalender nicht lesbar"))
    result = await service.run("get_menu_planning_context", {"action": "create_period"}, "ctx", lambda: True)
    assert result["code"] == code and not api.writes


@pytest.mark.parametrize("dislike", [True, False])
async def test_explicit_day_recipe_bypasses_taste_time_and_repeat_but_not_reheat_safety(dislike):
    c = settings()
    c["profiles"]["member_02"]["dislikes"] = [1] if dislike else []
    c["week"]["0"]["max_minutes"] = 1
    service, api, _, _ = await cooking(c, rows=[meal(9, "2026-10-19", recipe_id=1)])
    ident = await context(
        service, action="replace_day", date="2026-10-26", requested_recipe="Gericht 1 – Variante"
    )
    result = await submit(service, ident, [{"date": "2026-10-26", "recipe_id": 1}])
    assert not result["isError"], result
    assert metadata(api.rows[-1]["notes"])["servings_total"] == 2


async def test_explicit_non_reheatable_recipe_is_not_silently_replaced():
    from custom_components.yuvomi_mcp.recipes import merged_notes

    rows = recipes()
    rows[0]["notes"] = merged_notes(
        None, {"metadata": {**METADATA, "wiederaufwärmbar": False}}, creating=True
    )
    service, api, _, _ = await cooking(recipe_rows=rows)
    ident = await context(
        service, action="replace_day", date="2026-10-26", requested_recipe="Gericht 1 – Variante"
    )
    rejected = await submit(service, ident, [{"date": "2026-10-26", "recipe_id": 1}])
    assert rejected["code"] == "reheat_source_unclear" and not api.writes


async def test_targeted_recipe_change_preserves_existing_takeaway_dependencies_and_notes():
    service, api, _, _ = await cooking()
    ident = await context(service)
    assert not (await submit(service, ident, reheat_sources=selections()))["isError"]
    monday = api.rows[0]
    monday["notes"] = "Freie GUI-Notiz\n" + monday["notes"]
    changed_context = await service.run(
        "get_menu_planning_context",
        {"action": "replace_day", "date": "2026-10-26", "requested_recipe": "Gericht 6 – Variante"},
        "dayctx",
        lambda: True,
        owner="owner",
    )
    ident = changed_context["data"]["context_id"]
    response = await submit(service, ident, [{"date": "2026-10-26", "recipe_id": 6}], execution_key="day")
    assert not response["isError"], response
    changed = next(r for r in api.rows if r["date"] == "2026-10-26")
    assert metadata(changed["notes"])["extras"][0]["date"] == "2026-10-27"
    assert changed["notes"].startswith("Freie GUI-Notiz") and len(api.rows) == 5


async def test_legacy_reheat_dependency_is_not_silently_rewritten():
    notes = notes_block(None, {"v": 1, "kind": "reheat", "source_date": "2026-10-26", "extras": []}, "Alt")
    service, api, _, _ = await cooking(rows=[meal(8, "2026-10-27", notes=notes)])
    ident = await context(
        service, action="replace_day", date="2026-10-26", requested_recipe="Gericht 1 – Variante"
    )
    response = await submit(service, ident, [{"date": "2026-10-26", "recipe_id": 1}])
    assert response["code"] == "dependent_meal" and not api.writes


@pytest.mark.parametrize("bad", ["duplicate", "too_old", "no_need", "unknown_profile", "legacy_reheat"])
async def test_bad_sources_or_legacy_assignments_never_write(bad):
    service, api, _, journal = await cooking()
    ident = await context(service)
    rows, choices = assignments(), selections()
    if bad == "duplicate":
        choices.append(deepcopy(choices[0]))
    elif bad == "too_old":
        choices[0]["source_date"] = "2026-10-26"
    elif bad == "no_need":
        choices[0]["date"] = "2026-10-30"
    elif bad == "unknown_profile":
        choices[0]["profile_id"] = "missing"
    else:
        rows[0]["kind"] = "reheat"
    response = await submit(service, ident, rows, reheat_sources=choices)
    assert response["isError"] and not api.writes and not journal.data["journal"]


async def test_timeout_restart_reconciliation_and_parallel_retry_preserve_journal():
    service, api, store, journal = await cooking()
    ident = await context(service)
    api.error = ShoppingFailure("execution_unconfirmed", "Timeout", uncertain=True)
    response = await submit(service, ident, reheat_sources=selections())
    assert (
        response["code"] == "execution_unconfirmed" and journal.data["journal"]["save"]["state"] == "unknown"
    )
    restored = Journal(journal.store, journal.binding)
    await restored.load()
    restarted, _, _, _ = await cooking(journal=restored)
    restarted.api = api
    new_context = await context(restarted)
    blocked = await submit(restarted, new_context, reheat_sources=selections())
    assert blocked["code"] == "execution_unconfirmed" and len(api.writes) == 1
    api.rows = [
        {**deepcopy(b), "id": i + 1}
        for i, b in enumerate(journal.data["journal"]["save"]["body"]["assignments"])
    ]
    assert (await restarted.reconcile("save"))["status"] == "state_observed"
    assert len(api.writes) == 1
    fresh, api2, _, _ = await cooking()
    cid = await context(fresh)
    outcomes = await asyncio.gather(*(submit(fresh, cid, reheat_sources=selections()) for _ in range(3)))
    assert all(not r["isError"] for r in outcomes) and len(api2.writes) == 1


async def test_runtime_schema_field_errors_and_legacy_setup_gate():
    service, _, _, _ = await engine()
    runtime = Runtime(AsyncMock(), {}, lambda: set(MENU_TOOLS))
    runtime.planning = service
    bad = await runtime.call(
        "save_menu_plan",
        {"context_id": "x", "assignments": [{"date": "2026-10-26", "recipe_id": "1"}]},
        call_id="x",
        scope="s",
        owner="o",
    )
    assert bad["code"] == "invalid_arguments" and "recipe_id" in str(bad)
    old = await runtime.call(
        "get_menu_planning_context", {"action": "create_period"}, call_id="c", scope="s", owner="o"
    )
    assert old["code"] == "planning_not_configured"
    await runtime.close()


def test_compact_contract_accepts_cook_days_and_rejects_unknown_technical_fields():
    from jsonschema import Draft202012Validator, ValidationError

    validator = Draft202012Validator(menu_tools()["save_menu_plan"].schema)
    validator.validate(
        {
            "context_id": "ctx",
            "assignments": assignments(),
            "reheat_sources": selections(),
            "validate_only": True,
        }
    )
    with pytest.raises(ValidationError):
        validator.validate(
            {
                "context_id": "ctx",
                "assignments": [{"date": "2026-10-26", "recipe_id": 1, "servings_total": 4}],
            }
        )


async def test_additional_portions_are_added_by_backend_once_and_override_conflicts_fail():
    service, api, _, _ = await cooking()
    ident = await context(
        service, overrides=[{"date": "2026-10-29", "profile_id": "member_04", "additional_portions": 2}]
    )
    result = await submit(service, ident, reheat_sources=selections())
    assert not result["isError"], result
    assert metadata(api.rows[2]["notes"])["servings_total"] == 7  # 3 fresh + Aaron 1 + Aliyah 3
    replay = await submit(service, ident, reheat_sources=selections())
    assert replay["replayed"] and len(api.writes) == 1
    fresh, _, _, _ = await cooking()
    rejected = await fresh.run(
        "get_menu_planning_context",
        {
            "action": "create_period",
            "overrides": [
                {"date": "2026-10-29", "profile_id": "member_04", "portion": 1},
                {"date": "2026-10-29", "profile_id": "member_04", "additional_portions": 1},
            ],
        },
        "bad",
        lambda: True,
    )
    assert rejected["code"] == "invalid_override"


async def test_explicit_non_reheatable_friday_is_allowed_without_takeaway_need():
    from custom_components.yuvomi_mcp.recipes import merged_notes

    recs = recipes()
    recs[0]["notes"] = merged_notes(
        None, {"metadata": {**METADATA, "wiederaufwärmbar": False, "mag_nicht": ["member_04"]}}, creating=True
    )
    service, api, _, _ = await cooking(recipe_rows=recs)
    ident = await context(service, action="replace_day", date="2026-10-30", requested_recipe=recs[0]["title"])
    result = await submit(service, ident, [{"date": "2026-10-30", "recipe_id": 1}])
    assert not result["isError"], result
    assert metadata(api.rows[0]["notes"])["servings_total"] == 2


async def test_explicit_recipe_never_overrides_takeaway_recipients_dislike():
    from custom_components.yuvomi_mcp.recipes import merged_notes

    recs = recipes()
    recs[0]["notes"] = merged_notes(
        None, {"metadata": {**METADATA, "mag_nicht": ["member_03"]}}, creating=True
    )
    service, api, _, _ = await cooking(recipe_rows=recs)
    ident = await context(service, action="replace_day", date="2026-10-26", requested_recipe=recs[0]["title"])
    result = await submit(service, ident, [{"date": "2026-10-26", "recipe_id": 1}])
    assert result["code"] == "reheat_source_unclear" and not api.writes


async def test_no_calendar_read_when_rule_not_selected_on_any_day():
    c = calendar_config()
    c["week"]["0"]["calendars"] = []
    service, _, _, _ = await cooking(c)
    await context(service)
    assert service.calendar_reader is None


async def test_real_member_directory_filters_personal_fields_and_rejects_duplicate_ids():
    api = MealAPI(None)
    api._request = AsyncMock(
        return_value={
            "data": [{"id": 11, "display_name": "Cornelia", "email": "unused", "avatar_data": "unused"}]
        }
    )
    assert await api.members() == {11: {"id": 11, "name": "Cornelia"}}
    api._request.assert_awaited_once_with("GET", "/api/v1/family/members")
    api._request.return_value["data"].append({"id": 11, "display_name": "Duplicate"})
    with pytest.raises(ShoppingFailure, match="identität"):
        await api.members()


async def test_unknown_cook_or_changed_directory_blocks_before_post():
    c = settings()
    c["profiles"]["member_02"]["user_id"] = 999
    service, api, _, _ = await cooking(c)
    ident = await context(service)
    response = await submit(service, ident, reheat_sources=selections())
    assert response["code"] == "cook_unclear" and not api.writes
    service, api, _, _ = await cooking()
    ident = await context(service)
    api.members.return_value[11]["name"] = "Andere Identität"
    response = await submit(service, ident, reheat_sources=selections())
    assert response["code"] == "cook_unclear" and not api.writes


async def test_new_whole_week_partially_occupied_preserves_exact_existing_entry():
    existing = meal(90, "2026-10-30", recipe_id=7, title="Manuell unverändert", notes="Freitext")
    service, api, _, _ = await cooking(rows=[existing])
    ident = await context(service)
    result = await submit(service, ident, assignments()[:-1], reheat_sources=selections())
    assert not result["isError"], result
    assert existing in api.rows and len(api.rows) == 5
    assert all(b["date"] != "2026-10-30" for b in api.writes[0][0])


async def test_duplicate_persistent_allocations_block_all_writes():
    extra = {"date": "2026-10-29", "profile_id": "member_03", "servings": 1}
    notes = notes_block(None, {"v": 1, "kind": "cook", "recipe_id": 1, "extras": [extra]}, "Doppelt")
    service, api, _, _ = await cooking(
        rows=[meal(1, "2026-10-27", notes=notes), meal(2, "2026-10-28", notes=notes)]
    )
    ident = await context(
        service, action="replace_day", date="2026-10-30", requested_recipe="Gericht 6 – Variante"
    )
    result = await submit(service, ident, [{"date": "2026-10-30", "recipe_id": 6}])
    assert result["code"] == "invalid_metadata" and not api.writes


async def test_changed_existing_source_without_allocation_is_not_silently_increased():
    c = settings()
    c["week"]["2"]["fresh"] = []
    service, api, _, _ = await cooking(c, rows=[meal(90, "2026-10-27", recipe_id=2)])
    ident = await context(service)
    rows = [a for a in assignments() if a["date"] not in {"2026-10-27", "2026-10-28"}]
    result = await submit(service, ident, rows)
    assert result["code"] == "reheat_source_unclear" and not api.writes


async def test_long_exact_recipe_title_keeps_identity_and_details_in_notes():
    recs = recipes()
    recs[0]["title"] = "Langer exakter Variantenname " + "x" * 170
    service, api, _, _ = await cooking(recipe_rows=recs)
    ident = await context(service, action="replace_day", date="2026-10-26", requested_recipe=recs[0]["title"])
    result = await submit(service, ident, [{"date": "2026-10-26", "recipe_id": 1}])
    assert not result["isError"], result
    assert api.rows[0]["title"] == recs[0]["title"] and "member_03" in api.rows[0]["notes"]


async def test_partial_week_result_blocks_retries_without_claiming_success():
    service, api, _, journal = await cooking()
    ident = await context(service)
    api.skipped = [{"date": "2026-10-26", "reason": "occupied"}]
    response = await submit(service, ident, reheat_sources=selections())
    assert (
        response["code"] == "execution_unconfirmed" and journal.data["journal"]["save"]["state"] == "unknown"
    )
    retry = await submit(service, ident, reheat_sources=selections(), execution_key="different")
    assert retry["code"] == "execution_unconfirmed" and len(api.writes) == 1


async def test_create_day_never_overwrites_existing_entry_but_fills_free_day():
    existing = meal(90, "2026-10-30", notes="Nicht ändern")
    service, api, _, _ = await cooking(rows=[existing])
    ident = await context(service, action="create_day", date="2026-10-30")
    response = await submit(service, ident, [{"date": "2026-10-30", "recipe_id": 1}])
    assert response["code"] == "occupied" and api.rows == [existing] and not api.writes
    service, api, _, _ = await cooking()
    ident = await context(service, action="create_day", date="2026-10-30")
    response = await submit(service, ident, [{"date": "2026-10-30", "recipe_id": 1}])
    assert response["data"]["status"] == "created" and not api.writes[0][2]


@pytest.mark.parametrize("explicit", [False, True])
async def test_recipe_change_keeps_actual_yuvomi_cook_unless_explicitly_overridden(explicit):
    old = meal(90, "2026-10-26", recipe_id=7, cook_user_id=12)
    service, api, store, _ = await cooking(rows=[old])
    overrides = [{"date": "2026-10-26", "cook": "member_02"}] if explicit else []
    ident = await context(
        service,
        action="replace_day",
        date="2026-10-26",
        requested_recipe="Gericht 6 – Variante",
        overrides=overrides,
    )
    response = await submit(service, ident, [{"date": "2026-10-26", "recipe_id": 6}])
    assert not response["isError"], response
    assert api.rows[0]["cook_user_id"] == (11 if explicit else 12)
    assert store.data["config"]["week"]["0"]["cook"] == "member_02"


async def test_deliberate_prep_only_cooking_day_is_allowed_but_empty_meal_is_not():
    c = settings()
    c["week"]["0"]["fresh"] = []
    service, api, _, _ = await cooking(c)
    ident = await context(service)
    response = await submit(service, ident, reheat_sources=selections())
    assert not response["isError"], response
    first = metadata(api.rows[0]["notes"])
    assert first["servings_now"] == 0 and first["servings_total"] == 1
    c["week"]["1"]["prepared"] = []
    service, api, _, _ = await cooking(c)
    ident = await context(service)
    response = await submit(service, ident, reheat_sources=selections())
    assert response["code"] == "attendance_unclear" and not api.writes


async def test_period_end_does_not_force_unrequested_next_period_takeaway_meals():
    c = settings()
    c["anchor_date"] = "2026-10-28"
    service, api, _, _ = await cooking(c)
    # Existing previous-period allocations supply Thursday and remain untouched.
    extra = [{"date": "2026-10-29", "profile_id": p, "servings": 1} for p in ("member_03", "member_04")]
    notes = notes_block(None, {"v": 1, "kind": "cook", "recipe_id": 7, "extras": extra}, "Vorherige Quelle")
    api.rows = [meal(90, "2026-10-27", recipe_id=7, notes=notes)]
    ident = await context(service, start_date="2026-10-28")
    rows = [
        {"date": d, "recipe_id": i}
        for i, d in enumerate(["2026-10-28", "2026-10-29", "2026-10-30", "2026-11-02", "2026-11-03"], 1)
    ]
    response = await submit(service, ident, rows)
    assert not response["isError"], response
    last = metadata(next(r for r in api.rows if r["date"] == "2026-11-03")["notes"])
    assert last["extras"] == []  # do not choose Tuesday over next period's unplanned Wednesday
