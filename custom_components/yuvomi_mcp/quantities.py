"""Deliberately narrow quantity arithmetic. Never guess units or old amounts."""

import re
from decimal import Decimal

from .shopping_api import ShoppingFailure

UNITS = {
    "l": "l",
    "liter": "l",
    "ml": "ml",
    "g": "g",
    "kg": "kg",
    "stück": "Stück",
    "stueck": "Stück",
    "stk": "Stück",
    "packung": "Packung",
    "packungen": "Packung",
    "flasche": "Flasche",
    "flaschen": "Flasche",
    "tube": "Tube",
    "tuben": "Tube",
    "einheit": "Einheit",
    "einheiten": "Einheit",
}


def parse(value):
    if not isinstance(value, str):
        raise ShoppingFailure(
            "quantity_unclear", "Zusätzliche Menge braucht eine bekannte Ausgangsmenge und Einheit."
        )
    match = re.fullmatch(r"\s*(\d{1,6}(?:[.,]\d{1,3})?)\s*([A-Za-zÄÖÜäöü]+)?\s*", value)
    if not match:
        raise ShoppingFailure(
            "quantity_unclear", "Mengenangabe ist nicht eindeutig. Zahl und gleiche Einheit angeben."
        )
    amount = Decimal(match[1].replace(",", "."))
    unit = UNITS.get((match[2] or "").lower(), "" if not match[2] else None)
    if unit is None or amount <= 0:
        raise ShoppingFailure("quantity_unclear", "Menge oder Einheit ist nicht unterstützt.")
    return amount, unit


def increase(current, extra):
    first, unit = parse(current)
    second, other = parse(extra)
    if unit != other:
        raise ShoppingFailure(
            "quantity_unclear", "Für zusätzliche Mengen müssen die Einheiten übereinstimmen."
        )
    total = first + second
    if total > 1_000_000:
        raise ShoppingFailure("quantity_unclear", "Menge ist zu groß.")
    number = format(total, "f").rstrip("0").rstrip(".") if "." in format(total, "f") else str(total)
    plurals = {"Packung": "Packungen", "Flasche": "Flaschen", "Tube": "Tuben", "Einheit": "Einheiten"}
    label = plurals.get(unit, unit) if total != 1 else unit
    return number + (" " + label if label else "")


def quantity_key(value):
    """Stable retry comparison for numeric variants and otherwise exact free text."""
    try:
        amount, unit = parse(value)
        return [format(amount.normalize(), "f"), unit]
    except ShoppingFailure:
        return ["text", value]


def add_or_replace(current, requested, *, defaulted=False):
    """No guessed conversion: unsafe arithmetic transparently replaces the value."""
    operand = requested
    if defaulted:
        try:
            _, unit = parse(current)
            operand = "1" + (" " + unit if unit else "")
        except ShoppingFailure:
            pass
    try:
        return increase(current, operand), "increased", None
    except ShoppingFailure:
        return requested, "replaced", "incompatible_or_unparseable_quantity"
