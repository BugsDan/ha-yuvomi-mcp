"""Small HA options pages; selectors instead of JSON, one explicit atomic save."""

from copy import deepcopy
from uuid import uuid4

import probatio as vol
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector

from .journal import JournalError
from .planning_allocations import DAY_NAMES
from .planning_config import family_defaults, validate_config
from .shopping_api import ShoppingFailure


def select(options, multiple=False):
    return selector.SelectSelector(selector.SelectSelectorConfig(options=options, multiple=multiple))


def number(maximum=1440, minimum=0):
    return selector.NumberSelector(
        selector.NumberSelectorConfig(min=minimum, max=maximum, step=1, mode=selector.NumberSelectorMode.BOX)
    )


def whole(value):
    return int(value) if type(value) is float and value.is_integer() else value


class PlanningWizard:
    async def _wizard_start(self, config):
        if not hasattr(self, "_planning_draft"):
            self._planning_draft = deepcopy(config) if config.get("week") else family_defaults()
            if not config.get("week"):
                for field in (
                    "timezone",
                    "anchor_date",
                    "length_days",
                    "meal_type",
                    "meal_time",
                    "shopping_day",
                ):
                    self._planning_draft[field] = config[field]
        return self.async_show_menu(
            step_id="planning",
            menu_options=[
                "planning_general",
                "planning_profiles",
                "planning_week",
                "planning_calendars",
                "planning_finish",
            ],
        )

    def _choices(self, none=False):
        return ([{"value": "none", "label": "Niemand"}] if none else []) + [
            {"value": key, "label": p["name"]} for key, p in self._planning_draft["profiles"].items()
        ]

    async def _recipe_choices(self):
        rows = await self._runtime().planning.recipes.api.recipes()
        return [{"value": str(r["id"]), "label": r["title"]} for r in rows]

    def _form(self, step, fields, values, errors=None, detail=""):
        schema = {vol.Required(k, default=values[k]): s for k, s in fields.items()}
        return self.async_show_form(
            step_id=step,
            data_schema=vol.Schema(schema),
            errors=errors or {},
            description_placeholders={"validation_error": detail},
        )

    async def _accept_draft(self, candidate, step, fields, values):
        try:
            self._planning_draft = validate_config(candidate)
        except ShoppingFailure as error:
            field = getattr(error, "field", "base")
            if field not in fields:
                field = next((k for k in fields if f".{k}:" in str(error)), "base")
            return self._form(step, fields, values, {field: "invalid_planning"}, str(error))
        return await self._wizard_start(self._planning_draft)

    async def async_step_planning_general(self, user_input=None):
        c = self._planning_draft
        try:
            recipes = await self._recipe_choices()
        except ShoppingFailure as error:
            return self._form("planning_general", {}, {}, {"base": "invalid_planning"}, str(error))
        fields = {k: selector.TextSelector() for k in ("timezone", "anchor_date", "meal_time")}
        fields.update(
            length_days=number(31, 1),
            shopping_day=select([{"value": str(i), "label": d} for i, d in enumerate(DAY_NAMES)]),
            meal_type=select(
                [
                    {"value": k, "label": label}
                    for k, label in (
                        ("lunch", "Mittagessen"),
                        ("dinner", "Abendessen"),
                        ("breakfast", "Frühstück"),
                        ("snack", "Zwischenmahlzeit"),
                    )
                ]
            ),
            rest_recipe_id=select([{"value": "none", "label": "Keines"}] + recipes),
            rest_day=select(
                [{"value": "none", "label": "Flexibel"}]
                + [{"value": str(i), "label": d} for i, d in enumerate(DAY_NAMES)]
            ),
            rest_excluded_days=select([{"value": str(i), "label": d} for i, d in enumerate(DAY_NAMES)], True),
            emergency_recipe_ids=select(recipes, True),
            repeat_exceptions=select(recipes, True),
        )
        values = {k: c[k] for k in fields}
        for k in ("shopping_day", "rest_day", "rest_recipe_id"):
            values[k] = str(c[k]) if c[k] is not None else "none"
        for k in ("rest_excluded_days", "emergency_recipe_ids", "repeat_exceptions"):
            values[k] = list(map(str, c[k]))
        if user_input is None:
            return self._form("planning_general", fields, values)
        candidate = deepcopy(c)
        candidate.update(user_input)
        candidate["length_days"] = whole(user_input["length_days"])
        for k in ("shopping_day", "rest_day", "rest_recipe_id"):
            candidate[k] = None if user_input[k] == "none" else int(user_input[k])
        for k in ("rest_excluded_days", "emergency_recipe_ids", "repeat_exceptions"):
            candidate[k] = list(map(int, user_input[k]))
        return await self._accept_draft(candidate, "planning_general", fields, user_input)

    async def async_step_planning_profiles(self, user_input=None):
        if user_input is not None:
            self._profile_id = (
                "member_" + uuid4().hex[:12] if user_input["person"] == "new" else user_input["person"]
            )
            return await self.async_step_planning_profile()
        return self._form(
            "planning_profiles",
            {"person": select(self._choices() + [{"value": "new", "label": "Weitere Person"}])},
            {"person": next(iter(self._planning_draft["profiles"]))},
        )

    async def async_step_planning_profile(self, user_input=None):
        p = self._planning_draft["profiles"].get(self._profile_id, {"name": "", "days": []})
        warning = ""
        try:
            members = await self._runtime().planning.api.members()
            recipes = await self._recipe_choices()
        except ShoppingFailure as error:
            members, recipes, warning = {}, [], str(error) + " Für Kochzuordnung family:read prüfen."
        choices = [{"value": str(k), "label": v["name"]} for k, v in members.items()]
        fields = {k: selector.TextSelector() for k in ("name", "preferences", "avoid", "diet")}
        fields.update(
            portion=selector.NumberSelector(
                selector.NumberSelectorConfig(min=0.1, max=10, step=0.1, mode=selector.NumberSelectorMode.BOX)
            ),
            user_id=select([{"value": "none", "label": "Noch nicht verknüpft"}] + choices),
            fallback=select(
                [
                    {"value": "unknown", "label": "Ungeklärt – vor Planung klären"},
                    {"value": "absent", "label": "Ohne Kalender nicht dabei"},
                    {"value": "present", "label": "Ohne Kalender dabei"},
                ]
            ),
            dislikes=select(recipes, True),
        )
        values = {k: p.get(k, "") for k in ("name", "preferences", "avoid", "diet")}
        values.update(
            portion=p.get("portion", 1),
            user_id=str(p["user_id"]) if p.get("user_id") else "none",
            fallback=p.get("fallback", "absent"),
            dislikes=list(map(str, p.get("dislikes", []))),
        )
        if user_input is None:
            return self._form("planning_profile", fields, values, detail=warning)
        if user_input["user_id"] != "none" and int(user_input["user_id"]) not in members:
            return self._form(
                "planning_profile",
                fields,
                user_input,
                {"user_id": "invalid_planning"},
                "Kochidentität nicht in der aktuellen Yuvomi-Mitgliederliste.",
            )
        candidate = deepcopy(self._planning_draft)
        candidate["profiles"][self._profile_id] = {
            **p,
            **user_input,
            "days": [],
            "user_id": None if user_input["user_id"] == "none" else int(user_input["user_id"]),
            "dislikes": list(map(int, user_input["dislikes"])),
        }
        return await self._accept_draft(candidate, "planning_profile", fields, user_input)

    async def async_step_planning_week(self, user_input=None):
        if user_input is not None:
            self._weekday = user_input["day"]
            return await self.async_step_planning_day()
        return self._form(
            "planning_week",
            {"day": select([{"value": str(i), "label": d} for i, d in enumerate(DAY_NAMES)])},
            {"day": "0"},
        )

    async def async_step_planning_day(self, user_input=None):
        c, day = self._planning_draft, self._weekday
        rule = c["week"][day]
        fields = {
            "enabled": selector.BooleanSelector(),
            "fresh": select(self._choices(), True),
            "prepared": select(self._choices(), True),
            "max_age": number(2, 1),
            "limit_enabled": selector.BooleanSelector(),
            "max_minutes": number(),
            "cook": select(self._choices(True)),
            "calendars": selector.EntitySelector(
                selector.EntitySelectorConfig(domain="calendar", multiple=True)
            ),
        }
        values = {
            **rule,
            "cook": rule["cook"] or "none",
            "enabled": int(day) in c["days"],
            "limit_enabled": rule["max_minutes"] is not None,
            "max_minutes": rule["max_minutes"] or 0,
        }
        if user_input is None:
            return self._form("planning_day", fields, values)
        candidate = deepcopy(c)
        candidate["week"][day] = {k: user_input[k] for k in ("fresh", "prepared", "calendars")}
        candidate["week"][day].update(
            cook=None if user_input["cook"] == "none" else user_input["cook"],
            max_age=whole(user_input["max_age"]),
            max_minutes=whole(user_input["max_minutes"]) if user_input["limit_enabled"] else None,
        )
        candidate["days"] = sorted(
            (set(c["days"]) - {int(day)}) | ({int(day)} if user_input["enabled"] else set())
        )
        candidate["calendar_entities"] = sorted(set(c["calendar_entities"]) | set(user_input["calendars"]))
        return await self._accept_draft(candidate, "planning_day", fields, user_input)

    async def async_step_planning_calendars(self, user_input=None):
        if user_input is not None:
            self._calendar_id = (
                "rule_" + uuid4().hex[:12] if user_input["rule"] == "new" else user_input["rule"]
            )
            return await self.async_step_planning_calendar()
        options = [
            {"value": k, "label": v["entity"] + ": " + v["match"]}
            for k, v in self._planning_draft["calendars"].items()
        ]
        return self._form(
            "planning_calendars",
            {"rule": select(options + [{"value": "new", "label": "Neue Kalenderregel"}])},
            {"rule": "new"},
        )

    async def async_step_planning_calendar(self, user_input=None):
        rule = self._planning_draft["calendars"].get(
            self._calendar_id,
            {
                "entity": "",
                "profiles": [],
                "match": "Homeoffice",
                "effect": "present",
                "priority": 10,
                "match_mode": "exact",
                "required": True,
                "whole_day": False,
            },
        )
        fields = {
            "entity": selector.EntitySelector(selector.EntitySelectorConfig(domain="calendar")),
            "profiles": select(self._choices(), True),
            "match": selector.TextSelector(),
            "match_mode": select(["exact", "prefix", "contains"]),
            "effect": select(["present", "absent", "reheat", "no_reheat"]),
            "priority": number(100),
            "required": selector.BooleanSelector(),
            "whole_day": selector.BooleanSelector(),
            "delete": selector.BooleanSelector(),
        }
        values = {k: rule[k] for k in fields if k != "delete"} | {"delete": False}
        if user_input is None:
            return self._form("planning_calendar", fields, values)
        candidate = deepcopy(self._planning_draft)
        if user_input["delete"]:
            candidate["calendars"].pop(self._calendar_id, None)
        else:
            candidate["calendars"][self._calendar_id] = {k: user_input[k] for k in fields if k != "delete"}
            candidate["calendars"][self._calendar_id]["priority"] = whole(user_input["priority"])
            candidate["calendar_entities"] = sorted(
                set(candidate["calendar_entities"]) | {user_input["entity"]}
            )
        return await self._accept_draft(candidate, "planning_calendar", fields, user_input)

    async def async_step_planning_finish(self, user_input=None):
        if user_input and user_input.get("return_to_menu"):
            return await self._wizard_start(self._planning_draft)
        try:
            candidate = validate_config(self._planning_draft)
            registry = er.async_get(self.hass)
            for rule in candidate["calendars"].values():
                registered = registry.async_get(rule["entity"])
                if registered:
                    rule["registry_id"] = registered.id
            await self._runtime().planning.store.update(candidate)
        except (ShoppingFailure, JournalError, OSError) as error:
            return self._form(
                "planning_finish",
                {"return_to_menu": selector.BooleanSelector()},
                {"return_to_menu": True},
                {"base": "invalid_planning"},
                str(error),
            )
        self._runtime().planning.contexts.clear()
        return self.async_abort(reason="planning_saved")
