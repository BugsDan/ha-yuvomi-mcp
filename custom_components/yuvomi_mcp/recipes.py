"""Narrow recipe tools and structured menu metadata stored only in Yuvomi notes."""

import json
from copy import deepcopy

from jsonschema import Draft202012Validator, ValidationError

from .client import RemoteTool
from .notes import edit_note, note_text
from .shopping import resolve_category
from .shopping_api import ShoppingAPI, ShoppingFailure, positive_id

START = "[yuvomi_mcp:menu:v1]"
END = "[/yuvomi_mcp:menu:v1]"
METADATA = {
    "type": "object",
    "properties": {
        "wiederaufwärmbar": {"type": "boolean"},
        "zubereitungszeit_min": {
            "type": "integer",
            "minimum": 0,
            "maximum": 10080,
            "description": "Total elapsed minutes from cooking start until ready to serve, including waiting/baking.",
        },
        "gesundheit": {"type": "integer", "minimum": 1, "maximum": 5},
        "gesundheit_begruendung": {
            "type": "string",
            "minLength": 1,
            "maxLength": 1000,
            "description": "Reason for the health rating. An AI rating is a suggestion, never a human confirmation.",
        },
        "mag_nicht": {
            "type": "array",
            "maxItems": 30,
            "uniqueItems": True,
            "items": {"type": "string", "minLength": 1, "maxLength": 100},
        },
        "basisportionen": {
            "type": "integer",
            "minimum": 1,
            "maximum": 100,
            "description": "Base servings the ingredient quantities describe. Default 4 on creation; no automatic scaling.",
        },
    },
    "additionalProperties": False,
}
REQUIRED_METADATA = ["wiederaufwärmbar", "zubereitungszeit_min", "gesundheit", "gesundheit_begruendung"]


def recipe_tools():
    ingredients = {
        "type": "array",
        "maxItems": 200,
        "description": "Exact ingredient names and free-text quantities for basisportionen. Each category must exist in list_shopping_categories. Empty allowed for Resten; no pantry calculation.",
        "items": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "minLength": 1, "maxLength": 200},
                "quantity": {"type": "string", "minLength": 1, "maxLength": 100},
                "category": {"type": "string", "minLength": 1, "maxLength": 100},
            },
            "required": ["name", "quantity", "category"],
            "additionalProperties": False,
        },
    }
    fields = {
        "title": {
            "type": "string",
            "minLength": 1,
            "maxLength": 200,
            "description": "Exact recipe/menu title including variant/brand. Never shorten or silently substitute.",
        },
        "ingredients": ingredients,
        "notes": {
            "type": "string",
            "minLength": 1,
            "maxLength": 5000,
            "description": "Human-readable recipe instructions/notes. Omission preserves them; default appends. Structured menu metadata is managed separately.",
        },
        "metadata": deepcopy(METADATA),
    }
    create_fields = deepcopy(fields)
    create_fields["metadata"]["required"] = REQUIRED_METADATA
    update_fields = {
        **deepcopy(fields),
        "recipe_id": {"type": "integer", "minimum": 1},
        "notes_mode": {
            "type": "string",
            "enum": ["append", "replace", "clear"],
            "description": "Only explicit replace/clear changes existing free-text notes; metadata remains. clear requires omission of notes.",
        },
    }
    descriptions = {
        "list_recipes": "Read compact recipe/menu summaries, never instructions, free-text notes, links or ingredients by default. Pagination: limit default 20 (max 100), offset default 0; follow has_more/next_offset until done. Optional title is exact, not fuzzy. include_metadata adds structured health reasoning/provenance only. detail=full explicitly retrieves full recipe pages for legacy workflows; prefer get_recipe for a named recipe. Requires meals:read, no writes.",
        "get_recipe": "Read one full recipe including ingredients, instructions/notes and structured menu metadata. Supply exactly one: recipe_id or exact title including variant. For a named recipe, call directly with title instead of listing all recipes. Ambiguous titles require an ID; no fuzzy matching. Internally reads the complete Yuvomi 2.79.0 list; returns only the selected recipe. Requires meals:read, no writes.",
        "create_recipe": "Create a Yuvomi recipe/menu as Mittagessen (lunch). Base servings default 4, stored with structured metadata in notes. Provide known reheatability, total cooking-to-serving time and justified health suggestion; ask when unknown. Preserve exact titles/variants. Resten is an ordinary recipe with optional empty ingredients. No images/links, menu planning, scaling or shopping transfer. Requires meals:read/write and shopping:read for ingredient categories. Never claim unconfirmed writes as success.",
        "update_recipe": "Edit one native Yuvomi recipe ID. Read first. Omitted fields, existing free-text notes, meal types, links and images are preserved. Notes append by default; replace/clear only on explicit request. Metadata merges by field; an AI health rating remains a suggestion. Ingredient replacement is explicit and complete; quantities always refer to stored base servings. No automatic scaling or planning. Provider-mirrored recipes cannot be edited. Requires meals:read/write; shopping:read for changed ingredients. On concurrent_change or execution_unconfirmed do not blindly retry.",
    }
    schemas = {
        "list_recipes": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                    "description": "Page size; default 20.",
                },
                "offset": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "Zero-based offset; default 0. Follow next_offset.",
                },
                "title": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 200,
                    "description": "Exact recipe title including variant; no fuzzy or partial match.",
                },
                "detail": {
                    "type": "string",
                    "enum": ["summary", "full"],
                    "description": "Default summary. full explicitly returns complete recipe pages.",
                },
                "include_metadata": {
                    "type": "boolean",
                    "description": "Add structured health reasoning/provenance; no free-text notes.",
                },
            },
            "additionalProperties": False,
        },
        "get_recipe": {
            "type": "object",
            "properties": {
                "recipe_id": {"type": "integer", "minimum": 1},
                "title": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 200,
                    "description": "Exact title including variant. Use exactly one of recipe_id or title.",
                },
            },
            "additionalProperties": False,
        },
        "create_recipe": {
            "type": "object",
            "properties": create_fields,
            "required": ["title", "ingredients", "metadata"],
            "additionalProperties": False,
        },
        "update_recipe": {
            "type": "object",
            "properties": update_fields,
            "required": ["recipe_id"],
            "additionalProperties": False,
        },
    }
    return {name: RemoteTool(name, descriptions[name], schema) for name, schema in schemas.items()}


def split_notes(notes):
    notes = notes or ""
    if START not in notes and END not in notes:
        return notes, None
    if notes.count(START) != 1 or notes.count(END) != 1:
        raise ShoppingFailure("invalid_metadata", "Mehrdeutiger Menü-Metadatenblock; in Yuvomi prüfen.")
    prefix, tail = notes.split(START)
    data, suffix = tail.split(END) if END in tail else (None, None)
    try:
        decoded = json.loads(data)
        if not isinstance(decoded, dict) or set(decoded) != {"metadata", "gesundheit_herkunft"}:
            raise ValueError
        Draft202012Validator(
            {**METADATA, "required": REQUIRED_METADATA + ["basisportionen", "mag_nicht"]}
        ).validate(decoded["metadata"])
        if decoded["gesundheit_herkunft"] != "ki_vorschlag":
            raise ValueError
    except (ValueError, TypeError, ValidationError, RecursionError):
        raise ShoppingFailure(
            "invalid_metadata", "Ungültiger Menü-Metadatenblock; nicht überschrieben."
        ) from None
    return (prefix + suffix).strip(), decoded


def merged_notes(existing, args, *, creating=False):
    plain, stored = split_notes(existing)
    if "gesundheit" in args.get("metadata", {}) and "gesundheit_begruendung" not in args["metadata"]:
        raise ShoppingFailure(
            "invalid_metadata", "Gesundheitsbewertung benötigt eine passende ausdrückliche Begründung."
        )
    if "notes" in args and (START in args["notes"] or END in args["notes"]):
        raise ShoppingFailure("invalid_metadata", "Menümetadaten ausschließlich über metadata angeben.")
    edited = edit_note(plain or None, args, field="notes", mode_field="notes_mode")
    if "metadata" not in args and not creating:
        # Omission preserves the exact server note, including its existing block.
        if "notes" not in args and "notes_mode" not in args:
            return existing
        data = stored
    else:
        metadata = {**(stored["metadata"] if stored else {}), **args.get("metadata", {})}
        if creating:
            metadata = {"basisportionen": 4, "mag_nicht": [], **metadata}
        try:
            Draft202012Validator(
                {**METADATA, "required": REQUIRED_METADATA + ["basisportionen", "mag_nicht"]}
            ).validate(metadata)
            if not metadata["gesundheit_begruendung"].strip():
                raise ValueError
        except (ValidationError, ValueError):
            raise ShoppingFailure(
                "invalid_metadata", "Vollständige gültige Menümetadaten erforderlich; keine Werte geraten."
            ) from None
        data = {"metadata": metadata, "gesundheit_herkunft": "ki_vorschlag"}
    block = START + "\n" + json.dumps(data, ensure_ascii=False, sort_keys=True) + "\n" + END if data else ""
    return note_text("\n\n".join(p for p in [edited, block] if p)) or None


def recipe_snapshot(row):
    return {
        "title": row["title"],
        "notes": row.get("notes"),
        "recipe_url": row.get("recipe_url"),
        "meal_types": row["meal_types"],
        "ingredients": [{k: i.get(k) for k in ("name", "quantity", "category")} for i in row["ingredients"]],
    }


def exact_text(value, maximum):
    try:
        size = len(value.encode("utf-16-le")) // 2 if isinstance(value, str) else maximum + 1
    except UnicodeError:
        raise ShoppingFailure("invalid_arguments", "Ungültiges Unicode in Rezeptname oder Menge.") from None
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
        or size > maximum
        or any(ord(c) < 32 for c in value)
    ):
        raise ShoppingFailure(
            "invalid_arguments",
            "Name/Menge exakt ohne äußere Leer- oder Steuerzeichen und innerhalb der Yuvomi-Länge angeben.",
        )
    return value


async def recipe_body(args, existing, api):
    if existing and (existing.get("provider_account_id") or existing.get("source", "native") != "native"):
        raise ShoppingFailure("recipe_read_only", "Provider-Rezept in seiner Quelle bearbeiten.")
    if existing and set(args) == {"recipe_id"}:
        raise ShoppingFailure(
            "invalid_arguments", "Mindestens eine ausdrückliche Rezeptänderung erforderlich."
        )
    body = recipe_snapshot(existing) if existing else {"meal_types": ["lunch"], "recipe_url": None}
    if "title" in args:
        body["title"] = exact_text(args["title"], 200)
    body["notes"] = merged_notes(existing.get("notes") if existing else None, args, creating=not existing)
    if existing and "metadata" in args and "basisportionen" in args["metadata"]:
        _, previous = split_notes(existing.get("notes"))
        if (
            previous is None or previous["metadata"]["basisportionen"] != args["metadata"]["basisportionen"]
        ) and "ingredients" not in args:
            raise ShoppingFailure(
                "portions_require_ingredients",
                "Bei geänderter Basisportionenzahl vollständige passende Zutatenmengen ausdrücklich mitgeben; keine automatische Skalierung.",
            )
    if "ingredients" in args:
        categories = await api.categories() if args["ingredients"] else []
        body["ingredients"] = []
        for item in args["ingredients"]:
            category = resolve_category(item["category"], categories)
            if category is None:
                raise ShoppingFailure(
                    "invalid_category",
                    "Gültige Einkaufskategorien: "
                    + json.dumps([c["name"] for c in categories], ensure_ascii=False),
                )
            body["ingredients"].append(
                {
                    "name": exact_text(item["name"], 200),
                    "quantity": exact_text(item["quantity"], 100),
                    "category": exact_text(category, 100),
                }
            )
    return body


class RecipeAPI(ShoppingAPI):
    """No arbitrary URLs, generic operations, images, pantry or shopping writes."""

    @staticmethod
    def validate(row):
        try:
            positive_id(row["id"])
            if not isinstance(row["title"], str) or not row["title"].strip():
                raise ValueError
            if (
                "notes" not in row
                or "recipe_url" not in row
                or not isinstance(row.get("notes"), (str, type(None)))
                or not isinstance(row.get("recipe_url"), (str, type(None)))
            ):
                raise ValueError
            if not isinstance(row["meal_types"], list) or any(
                m not in {"breakfast", "lunch", "dinner", "snack"} for m in row["meal_types"]
            ):
                raise ValueError
            if not isinstance(row["ingredients"], list) or len(row["ingredients"]) > 10000:
                raise ValueError
            for ingredient in row["ingredients"]:
                if (
                    not isinstance(ingredient, dict)
                    or not isinstance(ingredient.get("name"), str)
                    or not ingredient["name"].strip()
                    or not isinstance(ingredient.get("category"), str)
                    or "quantity" not in ingredient
                    or not isinstance(ingredient.get("quantity"), (str, type(None)))
                ):
                    raise ValueError
        except (KeyError, TypeError, ValueError, ShoppingFailure):
            raise ShoppingFailure(
                "invalid_response", "Unvollständige Rezeptantwort; nichts überschrieben."
            ) from None
        return row

    async def recipes(self):
        data = await self._request("GET", "/api/v1/recipes")
        # 2.79.0 has exactly {data: [...]} and no pagination. Unknown envelopes
        # may announce truncation/pagination; never pretend their rows are complete.
        if set(data) != {"data"}:
            raise ShoppingFailure(
                "invalid_response", "Rezeptlistenvertrag geändert; Vollständigkeit nicht belegt."
            )
        rows = data.get("data")
        if not isinstance(rows, list) or len(rows) > 10000:
            raise ShoppingFailure("invalid_response", "Unvollständige Rezeptliste.")
        seen = set()
        for row in rows:
            self.validate(row)
            if row["id"] in seen:
                raise ShoppingFailure("invalid_response", "Mehrdeutige Rezept-IDs.")
            seen.add(row["id"])
        return rows

    async def save(self, recipe_id, body, key):
        if recipe_id is not None:
            positive_id(recipe_id)
        if set(body) != {"title", "notes", "recipe_url", "meal_types", "ingredients"}:
            raise ShoppingFailure("invalid_arguments", "Unzulässige Rezeptfelder.")
        method = "PUT" if recipe_id else "POST"
        path = f"/api/v1/recipes/{recipe_id}" if recipe_id else "/api/v1/recipes"
        data = await self._request(method, path, body=body, key=key if not recipe_id else None)
        try:
            row = self.validate(data["data"])
            if (recipe_id and row["id"] != recipe_id) or recipe_snapshot(row) != body:
                raise ValueError
            return row
        except (KeyError, ValueError, ShoppingFailure):
            raise ShoppingFailure(
                "execution_unconfirmed", "Rezept-Schreibantwort nicht eindeutig bestätigt.", uncertain=True
            ) from None
