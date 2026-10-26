"""Versioned planning settings, deliberately independent of an HA conversation."""

import asyncio
import json
from copy import deepcopy
from datetime import date, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from jsonschema import Draft202012Validator, ValidationError

from .journal import JournalError
from .shopping_api import ShoppingFailure

DAYS = {
    "type": "array",
    "uniqueItems": True,
    "maxItems": 7,
    "items": {"type": "integer", "minimum": 0, "maximum": 6},
}
IDS = {"type": "array", "uniqueItems": True, "maxItems": 200, "items": {"type": "integer", "minimum": 1}}
PROFILE = {
    "type": "object",
    "additionalProperties": False,
    "required": ["name", "days"],
    "properties": {
        "name": {"type": "string", "minLength": 1, "maxLength": 100},
        "days": DAYS,
        "portion": {"type": "number", "exclusiveMinimum": 0, "maximum": 10},
        "reheat_days": DAYS,
        "dislikes": IDS,
        "preferences": {"type": "string", "maxLength": 1000},
    },
}
CALENDAR = {
    "type": "object",
    "additionalProperties": False,
    "required": ["entity", "profiles", "match", "effect", "priority"],
    "properties": {
        "registry_id": {"type": "string", "maxLength": 100},
        "entity": {"type": "string", "pattern": "^calendar\\.[a-z0-9_]+$"},
        "profiles": {"type": "array", "minItems": 1, "uniqueItems": True, "items": {"type": "string"}},
        "match": {"type": "string", "minLength": 1, "maxLength": 200},
        "match_mode": {"enum": ["exact", "prefix", "contains"]},
        "effect": {"enum": ["present", "absent", "reheat", "no_reheat"]},
        "priority": {"type": "integer", "minimum": 0, "maximum": 100},
        "required": {"type": "boolean"},
        "whole_day": {"type": "boolean"},
    },
}
DEFAULTS = {
    "timezone": "Europe/Zurich",
    "anchor_date": "2026-10-21",
    "length_days": 7,
    "shopping_day": 2,
    "days": [0, 1, 2, 3, 4],
    "meal_type": "lunch",
    "meal_time": "12:00",
    "profiles": {},
    "calendars": {},
    "calendar_entities": [],
    "time_limits": {},
    "reheat_time_min": None,
    "rest_recipe_id": None,
    "rest_day": None,
    "rest_excluded_days": [],
    "emergency_recipe_ids": [],
    "repeat_exceptions": [],
    "max_reheat_days": 2,
}
SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": list(DEFAULTS),
    "properties": {
        "timezone": {"type": "string"},
        "anchor_date": {"type": "string"},
        "length_days": {"type": "integer", "minimum": 1, "maximum": 31},
        "shopping_day": {"type": "integer", "minimum": 0, "maximum": 6},
        "days": DAYS,
        "meal_type": {"enum": ["breakfast", "lunch", "dinner", "snack"]},
        "meal_time": {"type": "string", "pattern": "^(?:[01][0-9]|2[0-3]):[0-5][0-9]$"},
        "profiles": {
            "type": "object",
            "maxProperties": 20,
            "propertyNames": {"pattern": "^[a-z][a-z0-9_]{0,31}$"},
            "additionalProperties": PROFILE,
        },
        "calendar_entities": {
            "type": "array",
            "uniqueItems": True,
            "maxItems": 30,
            "items": {"type": "string", "pattern": "^calendar\\.[a-z0-9_]+$"},
        },
        "calendars": {"type": "object", "maxProperties": 30, "additionalProperties": CALENDAR},
        "time_limits": {
            "type": "object",
            "propertyNames": {"pattern": "^[0-6]$"},
            "additionalProperties": {"type": "integer", "minimum": 0, "maximum": 1440},
        },
        "reheat_time_min": {"type": ["integer", "null"], "minimum": 0, "maximum": 1440},
        "rest_recipe_id": {"type": ["integer", "null"], "minimum": 1},
        "rest_day": {"type": ["integer", "null"], "minimum": 0, "maximum": 6},
        "rest_excluded_days": DAYS,
        "emergency_recipe_ids": IDS,
        "repeat_exceptions": IDS,
        "max_reheat_days": {"type": "integer", "minimum": 1, "maximum": 2},
    },
}


def validate_config(value):
    try:
        Draft202012Validator(SCHEMA).validate(value)
        ZoneInfo(value["timezone"])
        date.fromisoformat(value["anchor_date"])
        if not value["days"] or value["rest_day"] in value["rest_excluded_days"]:
            raise ValueError
        if value["rest_day"] is not None and value["rest_recipe_id"] is None:
            raise ValueError
        permitted = set(value["emergency_recipe_ids"]) | {value["rest_recipe_id"]}
        if set(value["repeat_exceptions"]) - permitted:
            raise ValueError
        for rule in value["calendars"].values():
            if (
                set(rule["profiles"]) - value["profiles"].keys()
                or rule["entity"] not in value["calendar_entities"]
            ):
                raise ValueError
        json.dumps(value, allow_nan=False)
    except (ValidationError, ValueError, TypeError, ZoneInfoNotFoundError):
        raise ShoppingFailure(
            "invalid_planning_config",
            "Planungskonfiguration ungültig: Tage, Profile, Kalender, Zeiten und Ausnahmen prüfen.",
        ) from None
    return deepcopy(value)


def period(config, reference, which="current"):
    anchor = date.fromisoformat(config["anchor_date"])
    length = config["length_days"]
    start = anchor + timedelta(days=((reference - anchor).days // length + (which == "next")) * length)
    return start, start + timedelta(days=length - 1)


class PlanningStore:
    """Stores config, not recipes, profiles learned from a model, or actual leftovers."""

    def __init__(self, store, binding):
        self.store, self.binding = store, binding
        self.lock = asyncio.Lock()
        self.data = {"schema": 1, "binding": binding, "revision": 0, "config": deepcopy(DEFAULTS)}
        self.broken = False
        self.loaded = False

    async def load(self):
        async with self.lock:
            if self.loaded:
                return
            try:
                data = await self.store.async_load()
                if data is not None:
                    if (
                        set(data) != set(self.data)
                        or data["schema"] != 1
                        or data["binding"] != self.binding
                        or type(data["revision"]) is not int
                        or data["revision"] < 0
                    ):
                        raise ValueError
                    validate_config(data["config"])
                    self.data = deepcopy(data)
                self.loaded = True
            except Exception:
                self.broken = True
                raise JournalError(
                    "Planungsspeicher nicht lesbar; vorhandene Daten nicht überschreiben."
                ) from None

    async def update(self, config):
        candidate = validate_config(config)
        async with self.lock:
            if self.broken:
                raise JournalError("Planungsspeicher gesperrt.")
            value = {**self.data, "config": candidate, "revision": self.data["revision"] + 1}
            try:
                await self.store.async_save(deepcopy(value))
            except BaseException:
                self.broken = True
                raise
            self.data = value
