"""Versioned planning settings, deliberately independent of an HA conversation."""

import asyncio
import json
import re
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
        "avoid": {"type": "string", "maxLength": 1000},
        "diet": {"type": "string", "maxLength": 1000},
        "user_id": {"type": ["integer", "null"], "minimum": 1},
        "fallback": {"enum": ["present", "absent", "unknown"]},
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
        "days": DAYS,
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
    "week": {},
}
WEEKDAY = {
    "type": "object",
    "additionalProperties": False,
    "required": ["fresh", "prepared", "max_age", "max_minutes", "cook", "calendars"],
    "properties": {
        "fresh": {"type": "array", "uniqueItems": True, "items": {"type": "string"}},
        "prepared": {"type": "array", "uniqueItems": True, "items": {"type": "string"}},
        "max_age": {"type": "integer", "minimum": 1, "maximum": 2},
        "max_minutes": {"type": ["integer", "null"], "minimum": 0, "maximum": 1440},
        "cook": {"type": ["string", "null"]},
        "calendars": {"type": "array", "uniqueItems": True, "items": {"type": "string"}},
    },
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
        "week": {"type": "object", "propertyNames": {"pattern": "^[0-6]$"}, "additionalProperties": WEEKDAY},
    },
}


class PlanningConfigError(ShoppingFailure):
    def __init__(self, field, message):
        super().__init__("invalid_planning_config", message)
        self.field = field


def validate_config(value):
    # Read old settings without altering their stored representation or touching journals.
    # The options wizard explicitly replaces them with a new weekly draft on save.
    if isinstance(value, dict) and "week" not in value:
        value = {**value, "week": {}}
    if isinstance(value, dict) and isinstance(value.get("profiles"), dict):
        invalid = [key for key in value["profiles"] if not re.fullmatch(r"[a-z][a-z0-9_]{0,31}", str(key))]
        if invalid:
            labels = json.dumps([str(key)[:60] for key in invalid[:5]], ensure_ascii=False)
            raise PlanningConfigError(
                "profiles",
                f"Ungültige Profil-IDs: {labels}. Erlaubt: [a-z][a-z0-9_]{{0,31}}, z.B. kind_1; Anzeigename separat Kind 1.",
            )
    try:
        Draft202012Validator(SCHEMA).validate(value)
    except ValidationError as error:
        path = list(error.absolute_path)
        field = str(path[0]) if path else "base"
        raise PlanningConfigError(field, ".".join(map(str, path)) + ": " + error.message[:180]) from None
    try:
        ZoneInfo(value["timezone"])
    except (ValueError, ZoneInfoNotFoundError):
        raise PlanningConfigError(
            "timezone", "timezone: gültige IANA-Zeitzone angeben, z.B. Europe/Zurich."
        ) from None
    try:
        date.fromisoformat(value["anchor_date"])
    except ValueError:
        raise PlanningConfigError("anchor_date", "anchor_date: gültiges Datum YYYY-MM-DD angeben.") from None
    if not value["days"]:
        raise PlanningConfigError(
            "days", "days: mindestens einen Planungstag wählen (0=Montag bis 6=Sonntag)."
        )
    if value["rest_day"] in value["rest_excluded_days"]:
        raise PlanningConfigError("rest_day", "rest_day darf nicht in rest_excluded_days liegen.")
    if value["rest_day"] is not None and value["rest_recipe_id"] is None:
        raise PlanningConfigError("rest_recipe_id", "Ein fester Restentag benötigt rest_recipe_id.")
    permitted = set(value["emergency_recipe_ids"]) | {value["rest_recipe_id"]}
    if set(value["repeat_exceptions"]) - permitted:
        raise PlanningConfigError(
            "repeat_exceptions", "repeat_exceptions: nur konfigurierte Resten-/Notfall-Rezept-IDs zulässig."
        )
    for ident, rule in value["calendars"].items():
        if set(rule["profiles"]) - value["profiles"].keys():
            raise PlanningConfigError(
                "calendars", f"Kalenderregel {str(ident)[:60]}: unbekannte Profil-ID in profiles."
            )
        if rule["entity"] not in value["calendar_entities"]:
            raise PlanningConfigError(
                "calendar_entities",
                f"Kalenderregel {str(ident)[:60]}: Entity zuerst ausdrücklich in calendar_entities auswählen.",
            )
    if value["week"] and set(value["week"]) != set(map(str, range(7))):
        raise PlanningConfigError("week", "Standardwoche muss alle sieben Wochentage enthalten.")
    for day, rule in value["week"].items():
        people = set(rule["fresh"]) | set(rule["prepared"]) | ({rule["cook"]} if rule["cook"] else set())
        if people - value["profiles"].keys():
            raise PlanningConfigError("week", f"Wochentag {day}: unbekannte Person.")
        if set(rule["calendars"]) - set(value["calendar_entities"]):
            raise PlanningConfigError("week", f"Wochentag {day}: Kalender nicht freigegeben.")
        if set(rule["fresh"]) & set(rule["prepared"]):
            raise PlanningConfigError("week", f"Wochentag {day}: frisch und vorbereitet für dieselbe Person.")
    try:
        json.dumps(value, allow_nan=False)
    except (ValueError, TypeError):
        raise PlanningConfigError(
            "base", "Nur endliche JSON-Werte in der Planungskonfiguration verwenden."
        ) from None
    return deepcopy(value)


def family_defaults():
    """Editable initial draft; stable IDs are independent of display names and Yuvomi accounts."""
    value = deepcopy(DEFAULTS)
    value["profiles"] = {
        f"member_{i:02}": {
            "name": name,
            "days": [],
            "portion": 1,
            "preferences": "",
            "avoid": "",
            "diet": "",
            "user_id": None,
            "fallback": "unknown" if i == 1 else "absent",
        }
        for i, name in enumerate(("Daniel", "Cornelia", "Aaron", "Aliyah"), 1)
    }
    fresh = [
        ["member_02"],
        ["member_02", "member_04"],
        ["member_02", "member_03", "member_04"],
        ["member_02"],
        ["member_02", "member_04"],
        [],
        [],
    ]
    value["week"] = {
        str(d): {
            "fresh": fresh[d],
            "prepared": ["member_03"] if d == 1 else ["member_03", "member_04"] if d == 3 else [],
            "max_age": 1 if d == 1 else 2,
            "max_minutes": [75, 60, 40, 60, 25, None, None][d],
            "cook": "member_02" if d < 5 else None,
            "calendars": [],
        }
        for d in range(7)
    }
    return value


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
