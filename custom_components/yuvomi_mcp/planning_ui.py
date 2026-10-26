"""Explicit HA options editor; no model may mutate family or calendar rules."""

from copy import deepcopy

import probatio as vol
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector

from .journal import JournalError
from .shopping_api import ShoppingFailure


class PlanningOptions:
    async def async_step_planning(self, user_input=None):
        runtime = self._runtime()
        if runtime is None or runtime.planning is None:
            return self.async_abort(reason="planning_unavailable")
        store = runtime.planning.store
        try:
            await store.load()
        except JournalError:
            return self.async_abort(reason="planning_unavailable")
        config = deepcopy(store.data["config"])
        errors = {}
        fields = {}
        for key in ("timezone", "anchor_date", "meal_time", "meal_type"):
            fields[vol.Required(key, default=config[key])] = selector.TextSelector()
        for key in ("length_days", "shopping_day", "max_reheat_days"):
            fields[vol.Required(key, default=config[key])] = selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1 if key != "shopping_day" else 0,
                    max=31 if key == "length_days" else 6 if key == "shopping_day" else 2,
                    step=1,
                    mode=selector.NumberSelectorMode.BOX,
                )
            )
        for key in ("profiles", "calendars", "time_limits"):
            fields[vol.Required(key, default=config[key])] = selector.ObjectSelector()
        fields[vol.Required("calendar_entities", default=config["calendar_entities"])] = (
            selector.EntitySelector(selector.EntitySelectorConfig(domain="calendar", multiple=True))
        )
        # Array and nullable advanced settings remain a structured, validated HA object.
        advanced = {
            k: config[k]
            for k in (
                "days",
                "rest_recipe_id",
                "rest_day",
                "rest_excluded_days",
                "emergency_recipe_ids",
                "repeat_exceptions",
                "reheat_time_min",
            )
        }
        fields[vol.Required("advanced", default=advanced)] = selector.ObjectSelector()
        if user_input is not None and "advanced" in user_input:
            # Flatten before validation; never persist an opaque unvalidated subdocument.
            return await self._planning_flat(user_input, store, errors)
        return self.async_show_form(step_id="planning", data_schema=vol.Schema(fields), errors=errors)

    async def _planning_flat(self, user_input, store, errors):
        candidate = {
            **store.data["config"],
            **{k: v for k, v in user_input.items() if k != "advanced"},
            **user_input["advanced"],
        }
        for field in ("length_days", "shopping_day", "max_reheat_days"):
            if type(candidate[field]) is float and candidate[field].is_integer():
                candidate[field] = int(candidate[field])
        try:
            registry = er.async_get(self.hass)
            for rule in candidate["calendars"].values():
                registered = registry.async_get(rule["entity"])
                if registered:
                    rule["registry_id"] = registered.id
            await store.update(candidate)
        except (ShoppingFailure, JournalError, TypeError, KeyError, OSError):
            # Render the form again without recursively processing the rejected input.
            response = await self.async_step_planning()
            response["errors"] = {"base": "invalid_planning"}
            return response
        self._runtime().planning.contexts.clear()
        return self.async_abort(reason="planning_saved")
