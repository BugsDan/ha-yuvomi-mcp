"""Plan metadata and ingredient scaling; no actual leftover inventory."""

import json
import re
from decimal import Decimal

from .planning_context import fail

START, END = "[yuvomi-menu:v1]", "[/yuvomi-menu]"


def metadata(notes):
    notes = notes or ""
    if START not in notes and END not in notes:
        if "[yuvomi-menu:" in notes:
            fail("invalid_metadata", "Unbekannte Planmetadatenversion.")
        return None
    if notes.count(START) != 1 or notes.count(END) != 1 or notes.count("[yuvomi-menu:") != 1:
        fail("invalid_metadata", "Mehrdeutige Mahlzeitmetadaten.")
    try:
        block = notes.split(START)[1].split(END)[0]
        data = json.loads(block[block.index("\n") :].strip())
        if (
            not isinstance(data, dict)
            or data.get("v") != 1
            or data.get("kind") not in {"cook", "reheat", "rest", "emergency"}
        ):
            raise ValueError
        return data
    except (ValueError, KeyError, TypeError):
        fail("invalid_metadata", "Beschädigte Mahlzeitmetadaten; in Yuvomi prüfen.")


def notes_block(old, data, summary):
    old = old or ""
    metadata(old)
    if START in old:
        prefix, tail = old.split(START)
        _, suffix = tail.split(END)
        old = prefix + suffix
    block = (
        START
        + " "
        + summary
        + "\n"
        + json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
        + END
    )
    value = old + ("\n\n" if old else "") + block
    if len(value) > 5000:
        fail("invalid_metadata", "Mahlzeitnotizen einschließlich Metadaten zu lang.")
    return value


def scale(ingredients, factor):
    result = []
    for row in ingredients:
        amount = row.get("quantity")
        if factor == 1:
            scaled = amount
        else:
            match = re.fullmatch(r"\s*(\d{1,6}(?:[.,]\d{1,3})?)\s*([^\d\r\n]*)", amount or "")
            if not match:
                fail("quantity_unclear", "Rezeptmenge nicht sicher skalierbar; Rezept in Yuvomi präzisieren.")
            number = Decimal(match[1].replace(",", ".")) * factor
            if number <= 0 or number > 1000000 or number.as_tuple().exponent < -8:
                fail("quantity_unclear", "Skalierte Menge nicht sicher darstellbar.")
            scaled = format(number.normalize(), "f") + (" " + match[2].strip() if match[2].strip() else "")
        result.append({"name": row["name"], "quantity": scaled, "category": row["category"]})
    return result
