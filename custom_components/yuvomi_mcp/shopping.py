"""Shopping tool schemas, conservative name matching and category validation.

No REST writes, product rules, persistent history or copies of shopping lists.
"""

import re
import unicodedata

from .client import RemoteTool

CATEGORIES = "list_shopping_categories"
SUGGESTIONS = "suggest_shopping_items"
BULK = "add_shopping_items"
SHOPPING_READS = frozenset({CATEGORIES, SUGGESTIONS})


def _decoded_spellings(value: str) -> set[str]:
    """Bounded repairs of literal Unicode escapes and UTF-8 mojibake only."""
    values = {value, re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m[1], 16)), value)}
    for _ in range(2):
        for text in tuple(values):
            for encoding in ("latin-1", "cp1252"):
                try:
                    values.add(text.encode(encoding).decode("utf-8"))
                except (UnicodeEncodeError, UnicodeDecodeError):
                    pass
    return values


def _category_keys(value: str) -> set[str]:
    """Whole-name spelling keys; never use edit distance or product rules."""
    value = unicodedata.normalize("NFKC", value).casefold().replace("&", " und ")
    variants = {value, value.translate(str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue"}))}
    keys = set()
    for variant in variants:
        plain = "".join(c for c in unicodedata.normalize("NFKD", variant) if not unicodedata.combining(c))
        # Preserve underscores/replacement characters to distinguish a lost
        # character from separators. Other punctuation separates whole words.
        keys.add(" ".join(re.sub(r"[^\w\ufffd]+", " ", plain).split()))
    return keys


def resolve_category(value: str, categories: list[dict]) -> str | None:
    """Return one existing name verbatim; reject all ambiguous corrections."""
    if not isinstance(value, str):
        return None
    names = {item["name"] for item in categories}
    if value in names:
        return value
    inputs = set().union(*(_category_keys(text) for text in _decoded_spellings(value)))
    inputs.discard("")
    # '_' may mean a separator or exactly one lost letter (Getr_nke).
    # No variable-length wildcard and no fuzzy nearest-category selection.
    patterns = [
        re.compile(re.escape(key).replace("_", "[^\\W\\d_]").replace("\ufffd", "[^\\W\\d_]"))
        for key in inputs
        if key.count("_") + key.count("\ufffd") == 1
    ]
    separator_keys = {" ".join(key.replace("_", " ").split()) for key in inputs}
    matches = {
        name
        for name in names
        if any(
            key in inputs or key in separator_keys or any(pattern.fullmatch(key) for pattern in patterns)
            for key in _category_keys(name)
        )
    }
    return next(iter(matches)) if len(matches) == 1 else None


def shopping_tools(*, include_single=False) -> dict[str, RemoteTool]:
    """Local shopping schemas, with shared per-item write parameters."""
    fields = {
        "name": {
            "type": "string",
            "minLength": 1,
            "maxLength": 256,
            "description": "Exact requested product/brand name. Never shorten, substitute brands or use synonyms.",
        },
        "quantity": {
            "type": "string",
            "minLength": 1,
            "maxLength": 256,
            "description": "Free text quantity, e.g. 2 Packungen or 2 Tuben. Omitted means 1. For open items ensure and increase both add compatible quantities; otherwise replace with this value and report it. Checked items reactivate with this new quantity, never add to the old one. set is an explicit absolute correction.",
        },
        "category": {
            "type": "string",
            "minLength": 1,
            "maxLength": 256,
            "description": "For EVERY NEW product choose the best matching exact existing Yuvomi category and supply it on the FIRST call. Read list_shopping_categories first unless valid names are already in context. Never invent categories. Choose Sonstiges only when no specific existing category fits. Existing items always keep their Yuvomi category.",
        },
        "operation": {
            "type": "string",
            "enum": ["ensure", "set", "increase", "note"],
            "description": "ensure/increase: add to open items or replace incompatible/unparseable quantities, create new or reactivate checked items. Missing quantity defaults to 1. set: explicit absolute correction only; quantity required. note: edit ONLY an existing item note, without quantity/category/status changes; never use ensure for a note-only request.",
        },
    }
    fields["note"] = {
        "type": "string",
        "minLength": 1,
        "maxLength": 5000,
        "description": "Optional shopping note. Omit to preserve existing notes, including reactivation. With existing text default append; replace only when explicitly requested. Unicode/newlines supported.",
    }
    fields["note_mode"] = {
        "type": "string",
        "enum": ["append", "replace", "clear"],
        "description": "Default append. replace explicitly replaces; clear explicitly deletes without a note field. For note-only edits use operation=note (no quantity or category).",
    }
    description = (
        "Use current Yuvomi shopping state including checked items. Preserve existing names and categories. "
        "For every NEW item supply the best fitting category on the FIRST call from list_shopping_categories (unless known from context), never invent names and use Sonstiges only if no specific category fits; "
        "category_required returns valid names for a corrected call, with no writes. "
        "Never equate partial names, brands or size variants. Open products are updated on their existing ID, never duplicated. "
        "ensure and increase both add quantities for open items; if addition is unsafe, replace with the requested free text and clearly report replacement without a question. Missing quantity means 1 (one current unit when identifiable). Checked items reactivate with the requested quantity. Use set only for an explicit absolute correction. Report old_quantity, new_quantity and action; replayed means already processed, do not claim another addition. "
        "Optional note preserves existing text by default (append); note_mode=replace/clear only on explicit request. For pure note edits use operation=note, never ensure/increase: no quantity addition or reactivation. "
        "Never report not_executed or execution_unconfirmed as success or blindly retry uncertain writes."
    )
    result = {
        BULK: RemoteTool(
            BULK,
            "Ensure up to 20 items on one list; give category inside EACH new items[] object. " + description,
            {
                "type": "object",
                "properties": {
                    "list": {"type": "string"},
                    "items": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 20,
                        "items": {
                            "type": "object",
                            "properties": fields,
                            "required": ["name"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["items"],
                "additionalProperties": False,
            },
        ),
        CATEGORIES: RemoteTool(
            CATEGORIES,
            "Read all existing Yuvomi shopping category names via REST. Use only these categories when categorizing items.",
            {"type": "object", "properties": {}, "additionalProperties": False},
        ),
        SUGGESTIONS: RemoteTool(
            SUGGESTIONS,
            "Read Yuvomi shopping suggestions for q (prefix search). Only an exactly matching normalized name may supply a previous category. Similar names are different products. Never copy historical quantities automatically.",
            {
                "type": "object",
                "properties": {
                    "q": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 256,
                        "description": "Shopping item name or prefix.",
                    }
                },
                "required": ["q"],
                "additionalProperties": False,
            },
        ),
    }
    if include_single:
        result["add_shopping_item"] = RemoteTool(
            "add_shopping_item",
            description,
            {
                "type": "object",
                "properties": {**fields, "list": {"type": "string"}},
                "required": ["name"],
                "additionalProperties": False,
            },
        )
    return result


def normalized_name(value: str) -> str:
    """Exact equality after Unicode/case/whitespace normalization, never fuzzy."""
    return " ".join(unicodedata.normalize("NFKC", value).split()).lower()
