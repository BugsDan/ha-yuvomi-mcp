"""Atomic execution journal; legacy product data is archived, never consulted."""

import asyncio
from copy import deepcopy
from datetime import datetime, timezone

SCHEMA_VERSION = 2
MAX_JOURNAL = 512


class JournalError(Exception):
    """Public storage failure with no private filesystem details."""


def now():
    return datetime.now(timezone.utc).isoformat()


def text(value, limit=256):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise JournalError("Name oder Text ist leer oder zu lang.")
    if any(ord(c) < 32 for c in value):
        raise JournalError("Steuerzeichen sind nicht erlaubt.")
    return value.strip()


def validate_journal(records):
    if not isinstance(records, dict) or len(records) > MAX_JOURNAL:
        raise JournalError("Ungültiges oder zu großes Ausführungsjournal. Nicht überschreiben.")
    for key, record in records.items():
        methods = (
            {"POST"}
            if isinstance(record, dict) and record.get("resource") == "meals"
            else {"POST", "PUT"}
            if isinstance(record, dict) and record.get("resource") == "recipes"
            else {"POST", "PATCH"}
        )
        if (
            not isinstance(key, str)
            or not isinstance(record, dict)
            or record.get("id") != key
            or record.get("state") not in {"prepared", "unknown", "done", "failed", "observed"}
            or type(record.get("list_id")) is not int
            or record["list_id"] < 1
            or record.get("resource", "shopping") not in {"shopping", "recipes", "meals"}
            or record.get("method") not in methods | {None}
            or not isinstance(record.get("name"), str)
            or (
                record["state"] in {"prepared", "unknown"}
                and (record.get("method") not in methods or not isinstance(record.get("body"), dict))
            )
            or (record["state"] in {"done", "observed"} and not isinstance(record.get("result"), dict))
        ):
            raise JournalError("Ungültiges Ausführungsjournal. Nicht überschreiben.")
        if "intent" in record and record["intent"] is not None:
            intent = record["intent"]
            if (
                not isinstance(intent, str)
                or len(intent) != 64
                or any(c not in "0123456789abcdef" for c in intent)
            ):
                raise JournalError("Ungültiger Wiederholungsschlüssel.")
        try:
            for field in ("created_at", "intent_created_at"):
                if field == "created_at" or field in record:
                    if datetime.fromisoformat(record[field]).tzinfo is None:
                        raise ValueError
        except (KeyError, TypeError, ValueError):
            raise JournalError("Ungültiger Journalzeitpunkt.") from None


class Journal:
    def __init__(self, store, binding, archive_store=None):
        self.store = store
        self.archive_store = archive_store
        self.binding = binding
        self.lock = asyncio.Lock()
        self.broken = False
        self.closed = False
        self.data = {"schema": SCHEMA_VERSION, "binding": binding, "journal": {}}

    async def load(self):
        try:
            data = await self.store.async_load()
            if data is None:
                return
            if not isinstance(data, dict) or data.get("schema") not in {1, SCHEMA_VERSION}:
                raise JournalError("Unbekannte Speicherversion; Sicherung erhalten und Update prüfen.")
            if data.get("binding") != self.binding:
                raise JournalError(
                    "Journal gehört zu einer anderen Yuvomi-URL. Keine automatische Übernahme."
                )
            validate_journal(data.get("journal"))
            if data["schema"] == 1:
                if self.archive_store is None:
                    raise JournalError("Altkatalog kann nicht sicher archiviert werden. Keine Migration.")
                archived = await self.archive_store.async_load()
                if archived is None:
                    await self.archive_store.async_save(deepcopy(data))
                    if await self.archive_store.async_load() != data:
                        raise JournalError(
                            "Archiv konnte nicht bestätigt werden. Altspeicher bleibt erhalten."
                        )
                elif archived != data:
                    raise JournalError(
                        "Abweichendes Altkatalogarchiv vorhanden. Manuell prüfen; nichts überschrieben."
                    )
                migrated = {
                    "schema": SCHEMA_VERSION,
                    "binding": self.binding,
                    "journal": deepcopy(data["journal"]),
                }
                await self.store.async_save(deepcopy(migrated))
                data = migrated
            elif set(data) != {"schema", "binding", "journal"}:
                raise JournalError("Unbekannte Journalfelder. Speicher bleibt erhalten.")
            self.data = deepcopy(data)
        except JournalError:
            raise
        except Exception:
            raise JournalError(
                "Journal/Migrationsarchiv kann nicht sicher gelesen oder gespeichert werden."
            ) from None

    async def change(self, operation):
        async with self.lock:
            if self.broken or self.closed:
                raise JournalError(
                    "Journalspeicher ist gesperrt. Sicherung prüfen und Integration neu laden."
                )
            candidate = deepcopy(self.data)
            result = operation(candidate)
            validate_journal(candidate["journal"])
            try:
                await self.store.async_save(deepcopy(candidate))
            except asyncio.CancelledError:
                self.broken = True
                raise
            except Exception:
                self.broken = True
                raise JournalError(
                    "Journalspeicherung fehlgeschlagen. Keine weiteren Schreibvorgänge erlaubt."
                ) from None
            self.data = candidate
            return deepcopy(result)

    async def close(self):
        async with self.lock:
            self.closed = True
