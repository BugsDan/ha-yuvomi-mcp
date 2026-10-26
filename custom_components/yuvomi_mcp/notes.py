"""Explicit, bounded note edits matching Yuvomi's trimmed text contract."""

from .shopping_api import ShoppingFailure


def note_text(value):
    try:
        size = len(value.encode("utf-16-le")) // 2 if isinstance(value, str) else 5001
    except UnicodeError:
        raise ShoppingFailure("invalid_note", "Notiz enthält ungültiges Unicode.") from None
    if size > 5000:
        raise ShoppingFailure("invalid_note", "Notiz muss Text mit höchstens 5000 Zeichen sein.")
    if any(ord(c) < 32 and c not in "\r\n\t" for c in value):
        raise ShoppingFailure("invalid_note", "Ungültige Steuerzeichen in Notiz.")
    return value.strip()


def edit_note(existing, arguments, *, field="note", mode_field="note_mode"):
    """Omission preserves notes; deletion requires explicit clear."""
    if field not in arguments and mode_field not in arguments:
        return existing
    mode = arguments.get(mode_field, "append")
    if mode == "clear":
        if field in arguments:
            raise ShoppingFailure("invalid_note", "Löschen mit clear ohne Notiztext anfordern.")
        return None
    if mode not in {"append", "replace"} or field not in arguments:
        raise ShoppingFailure("invalid_note", "Notiztext und gültige Notizoperation erforderlich.")
    value = note_text(arguments[field])
    if not value:
        raise ShoppingFailure("invalid_note", "Leere Notiz ist kein Löschauftrag. clear verwenden.")
    return note_text((existing + "\n" + value) if mode == "append" and existing else value)
