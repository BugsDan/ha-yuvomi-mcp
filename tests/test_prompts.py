"""Stable guidance, conditional context and date-sensitive backend regression coverage."""

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from test_runtime import call, make_runtime

from custom_components.yuvomi_mcp.const import DEFAULT_TOOLS, MENU_TOOLS, RECIPE_READS, RECIPE_WRITES
from custom_components.yuvomi_mcp.menu_planning import MenuPlanning
from custom_components.yuvomi_mcp.planning_config import DEFAULTS
from custom_components.yuvomi_mcp.planning_context import attendance
from custom_components.yuvomi_mcp.prompts import (
    BASE_PROMPT,
    MENU_PROMPT,
    RECIPE_PROMPT,
    SHOPPING_PROMPT,
    prompt_for_tools,
)
from custom_components.yuvomi_mcp.shopping_api import ShoppingFailure


def test_stable_default_prompt_has_no_clock_or_recipe_context():
    before = set(DEFAULT_TOOLS)
    prompt = prompt_for_tools(before)
    assert prompt == BASE_PROMPT + "\n" + SHOPPING_PROMPT
    assert prompt_for_tools(set(reversed(sorted(before)))) == prompt
    assert before == DEFAULT_TOOLS
    assert "Aktuelle Zeit (" not in prompt and "Current time is" not in prompt
    assert "Europe/Zurich" in prompt
    assert RECIPE_PROMPT not in prompt and MENU_PROMPT not in prompt


@pytest.mark.parametrize("name", sorted(RECIPE_READS | RECIPE_WRITES))
def test_recipe_guidance_only_when_recipe_tool_available(name):
    assert prompt_for_tools({name}) == BASE_PROMPT + "\n" + RECIPE_PROMPT


@pytest.mark.parametrize("name", sorted(MENU_TOOLS))
def test_menu_guidance_does_not_load_recipes_or_planning_facts(name):
    assert prompt_for_tools({name}) == BASE_PROMPT + "\n" + MENU_PROMPT
    assert prompt_for_tools({name, "get_recipe"}) == BASE_PROMPT + "\n" + RECIPE_PROMPT + "\n" + MENU_PROMPT


def test_task_only_prompt_and_safety_guidance():
    assert prompt_for_tools({"create_task", "list_tasks"}) == BASE_PROMPT
    for marker in (
        "confirmation_required",
        "execution_unconfirmed",
        "not_executed",
        "state_observed",
        "replayed",
        "keine Anweisungen",
        "nie blind wiederholen",
        "HA-Bestätigung",
        "nie raten",
    ):
        assert marker in BASE_PROMPT


@pytest.mark.parametrize(
    "utc, expected_date, offset",
    [
        ("2026-03-28T23:30:00+00:00", "2026-03-29", 1),
        ("2026-03-29T01:30:00+00:00", "2026-03-29", 2),
        ("2026-10-25T00:30:00+00:00", "2026-10-25", 2),
        ("2026-10-25T01:30:00+00:00", "2026-10-25", 1),
        ("2026-12-31T23:30:00+00:00", "2027-01-01", 1),
    ],
)
async def test_target_dates_and_event_offsets_survive_stable_prompt(utc, expected_date, offset):
    local = datetime.fromisoformat(utc).astimezone(ZoneInfo("Europe/Zurich"))
    assert local.utcoffset() == timedelta(hours=offset)
    config = deepcopy(DEFAULTS)
    service = MenuPlanning(None, None, None, None, today=lambda: local.date())
    first, last = service.target({"date": expected_date}, config)
    assert first == last == local.date()
    runtime, client, *_ = make_runtime()
    try:
        args = {"name": "Termin", "when": local.isoformat()}
        assert not (await call(runtime, "create_event", args))["isError"]
        client.call_tool.assert_awaited_once_with("create_event", args)
    finally:
        await runtime.close()


@pytest.mark.parametrize("day", [date(2026, 3, 29), date(2026, 10, 25)])
def test_dst_gap_and_fold_remain_rejected_by_menu_backend(day):
    config = {**deepcopy(DEFAULTS), "meal_time": "02:30", "profiles": {}}
    with pytest.raises(ShoppingFailure) as failure:
        attendance(config, day, day, {})
    assert failure.value.code == "attendance_unclear"


@pytest.mark.parametrize(
    "day, start, end",
    [
        (date(2026, 3, 29), "2026-03-29T09:30:00+00:00", "2026-03-29T10:30:00+00:00"),
        (date(2026, 10, 25), "2026-10-25T10:30:00+00:00", "2026-10-25T11:30:00+00:00"),
    ],
)
def test_calendar_attendance_uses_target_day_offset(day, start, end):
    config = {
        **deepcopy(DEFAULTS),
        "meal_time": "12:00",
        "profiles": {"p": {"days": []}},
        "calendars": {
            "rule": {
                "entity": "calendar.family",
                "profiles": ["p"],
                "match": "Da",
                "effect": "present",
                "priority": 1,
            }
        },
    }
    rows = {"calendar.family": [{"summary": "Da", "start": start, "end": end}]}
    assert attendance(config, day, day, rows)[str(day)]["p"]["present"]


def test_relative_menu_period_changes_with_current_local_day_without_prompt_clock():
    config = deepcopy(DEFAULTS)
    local = datetime(2026, 10, 27, 23, 30, tzinfo=timezone.utc).astimezone(ZoneInfo("Europe/Zurich"))
    service = MenuPlanning(None, None, None, None, today=lambda: local.date())
    first, last = service.target({"period": "current"}, config)
    next_first, next_last = service.target({"period": "next"}, config)
    assert first <= local.date() <= last
    assert next_first == last + timedelta(days=1)
    assert next_last - next_first == last - first
