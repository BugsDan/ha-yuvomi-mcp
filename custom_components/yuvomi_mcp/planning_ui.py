"""Explicit HA options editor; no model may mutate family or calendar rules."""

from copy import deepcopy

import probatio as vol
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector

from .journal import JournalError
from .planning_config import validate_config
from .planning_form import form_candidate, form_values
from .planning_wizard import PlanningWizard
from .shopping_api import ShoppingFailure


class PlanningOptions(PlanningWizard):
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
        if user_input is not None:
            return await self._planning_flat(user_input, store)
        return await self._wizard_start(config)

    def _planning_form(self, config, user_input=None, errors=None, detail=""):
        config = form_values(config, user_input)
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
        for key in ("profiles", "calendars", "time_limits", "week"):
            fields[vol.Required(key, default=config[key])] = selector.ObjectSelector()
        fields[vol.Required("calendar_entities", default=config["calendar_entities"])] = (
            selector.EntitySelector(selector.EntitySelectorConfig(domain="calendar", multiple=True))
        )
        # Array and nullable advanced settings remain a structured, validated HA object.
        fields[vol.Required("advanced", default=config["advanced"])] = selector.ObjectSelector()
        return self.async_show_form(
            step_id="planning",
            data_schema=vol.Schema(fields),
            errors=errors or {},
            description_placeholders={"validation_error": detail},
        )

    async def _planning_flat(self, user_input, store):
        try:
            candidate = validate_config(form_candidate(store.data["config"], user_input))
            registry = er.async_get(self.hass)
            for rule in candidate["calendars"].values():
                registered = registry.async_get(rule["entity"])
                if registered:
                    rule["registry_id"] = registered.id
            await store.update(candidate)
        except ShoppingFailure as error:
            field = getattr(error, "field", "base")
            if field not in form_values(store.data["config"]):
                field = "advanced" if field != "base" else "base"
            return self._planning_form(
                store.data["config"], user_input, {field: "invalid_planning"}, str(error)
            )
        except (JournalError, OSError):
            return self._planning_form(
                store.data["config"],
                user_input,
                {"base": "planning_storage_error"},
                "Speichern fehlgeschlagen; Eingaben bleiben im Formular. Integration/Sicherung prüfen.",
            )
        self._runtime().planning.contexts.clear()
        return self.async_abort(reason="planning_saved")
