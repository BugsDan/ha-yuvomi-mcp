"""Read-only projections; complete source recipes stay internal to validation and writes."""

from copy import deepcopy

from .recipes import split_notes
from .shopping_api import ShoppingFailure


def menu_metadata(row):
    try:
        _, block = split_notes(row.get("notes"))
        return {"menu_metadata": deepcopy(block)}
    except ShoppingFailure:
        return {"menu_metadata": None, "metadata_error": "invalid_metadata"}


def summary(row, *, include_metadata=False):
    parsed = menu_metadata(row)
    metadata = (parsed["menu_metadata"] or {}).get("metadata", {})
    value = {"id": row["id"], "title": row["title"], "meal_types": deepcopy(row["meal_types"])}
    for name in ("basisportionen", "zubereitungszeit_min", "wiederaufwärmbar", "gesundheit", "mag_nicht"):
        value[name] = deepcopy(metadata.get(name))
    if "metadata_error" in parsed:
        value["metadata_error"] = parsed["metadata_error"]
    if include_metadata:
        value.update(parsed)
    return value


def planning_recipe(row):
    return {
        "id": row["id"],
        "title": row["title"],
        "meal_types": deepcopy(row["meal_types"]),
        **menu_metadata(row),
        "ingredients": [
            {key: ingredient.get(key) for key in ("name", "quantity", "category")}
            for ingredient in row["ingredients"]
        ],
    }
