"""Lossless form defaults and candidate construction, independent of HA UI imports."""

from copy import deepcopy

from .planning_config import PlanningConfigError

ADVANCED = (
    "days",
    "rest_recipe_id",
    "rest_day",
    "rest_excluded_days",
    "emergency_recipe_ids",
    "repeat_exceptions",
    "reheat_time_min",
)


def form_values(config, submitted=None):
    values = {key: deepcopy(value) for key, value in config.items() if key not in ADVANCED}
    values["advanced"] = {key: deepcopy(config[key]) for key in ADVANCED}
    if submitted is not None:
        values.update(deepcopy(submitted))
    return values


def form_candidate(config, submitted):
    advanced = submitted.get("advanced")
    if not isinstance(advanced, dict) or set(advanced) - set(ADVANCED):
        raise PlanningConfigError(
            "advanced", "advanced: nur die angezeigten erweiterten Felder als Objekt angeben."
        )
    candidate = {
        **deepcopy(config),
        **deepcopy({k: v for k, v in submitted.items() if k != "advanced"}),
        **deepcopy(advanced),
    }
    for key in ("length_days", "shopping_day", "max_reheat_days"):
        if type(candidate[key]) is float and candidate[key].is_integer():
            candidate[key] = int(candidate[key])
    return candidate
