"""Journal persistence and lossless one-time legacy migration."""

import asyncio
import json
from copy import deepcopy

import pytest

from custom_components.yuvomi_mcp.journal import Journal, JournalError, now


class MemoryStore:
    def __init__(self, data=None):
        self.data = deepcopy(data)
        self.fail = False

    async def async_load(self):
        return deepcopy(self.data)

    async def async_save(self, data):
        if self.fail:
            raise OSError("private filesystem details")
        self.data = deepcopy(data)


async def make_journal(store=None, archive=None):
    journal = Journal(store or MemoryStore(), "http://host/mcp", archive)
    await journal.load()
    return journal


def record(state="prepared", method="POST"):
    return {
        "id": "key",
        "list_id": 1,
        "method": method,
        "name": "Getränkeprodukt",
        "body": {"name": "Getränkeprodukt", "category": "Getränke", "quantity": None},
        "state": state,
        "created_at": now(),
        "result": {} if state in {"done", "observed"} else None,
        "product_id": "old-id",
        "item_id": 1,
        "delta": None,
    }


def legacy_data(records=None):
    return {
        "schema": 1,
        "binding": "http://host/mcp",
        "products": {"old": {"name": "Tee", "aliases": ["Eistee"]}},
        "proposals": {"keep": {"unknown": True}},
        "observations": {"keep": {}},
        "journal": records or {"key": record()},
    }


@pytest.mark.parametrize("state", ["prepared", "unknown", "done", "observed", "failed"])
async def test_migration_archives_complete_original_and_preserves_every_journal_state(state):
    original = legacy_data({"key": record(state)})
    store, archive = MemoryStore(original), MemoryStore()
    journal = await make_journal(store, archive)
    assert archive.data == original
    assert (
        journal.data
        == store.data
        == {"schema": 2, "binding": original["binding"], "journal": original["journal"]}
    )
    archive.fail = True  # Normal restarts neither read nor write the archive.
    assert (await make_journal(store, archive)).data == journal.data
    assert not hasattr(journal, "find")


async def test_archive_failure_never_replaces_legacy_store():
    original = legacy_data()
    store, archive = MemoryStore(original), MemoryStore()
    archive.fail = True
    with pytest.raises(JournalError):
        await make_journal(store, archive)
    assert store.data == original


async def test_failed_main_save_can_safely_resume_migration_with_existing_archive():
    original = legacy_data()
    store, archive = MemoryStore(original), MemoryStore()
    store.fail = True
    with pytest.raises(JournalError):
        await make_journal(store, archive)
    assert archive.data == original == store.data
    store.fail = False
    assert (await make_journal(store, archive)).data["journal"] == original["journal"]


async def test_conflicting_archive_is_never_overwritten():
    original = legacy_data()
    store, archive = MemoryStore(original), MemoryStore({"different": True})
    with pytest.raises(JournalError):
        await make_journal(store, archive)
    assert store.data == original and archive.data == {"different": True}


@pytest.mark.parametrize(
    "change",
    [
        {"schema": 99},
        {"binding": "http://other/mcp"},
        {"journal": []},
        {"journal": {"key": {**record(), "state": "unsafe"}}},
    ],
)
async def test_corruption_or_other_binding_is_not_replaced(change):
    original = {**legacy_data(), **change}
    store, archive = MemoryStore(original), MemoryStore()
    with pytest.raises(JournalError):
        await make_journal(store, archive)
    assert store.data == original and archive.data is None


async def test_failed_save_latches_closed_for_future_writes():
    journal = await make_journal()
    journal.store.fail = True
    with pytest.raises(JournalError):
        await journal.change(lambda data: data["journal"].update(key=record()))
    assert journal.broken and not journal.data["journal"]
    journal.store.fail = False
    with pytest.raises(JournalError):
        await journal.change(lambda data: None)


async def test_cancelled_save_latches_closed():
    journal = await make_journal()

    async def cancel(data):
        raise asyncio.CancelledError

    journal.store.async_save = cancel
    with pytest.raises(asyncio.CancelledError):
        await journal.change(lambda data: None)
    assert journal.broken


async def test_file_store_restore_preserves_unicode_and_unknown_barrier(tmp_path):
    path = tmp_path / "journal.json"

    class FileStore:
        async def async_load(self):
            return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

        async def async_save(self, data):
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    journal = await make_journal(FileStore())
    await journal.change(lambda data: data["journal"].update(key=record("unknown")))
    restored = await make_journal(FileStore())
    assert restored.data == journal.data
    assert restored.data["journal"]["key"]["state"] == "unknown"


async def test_unconfirmed_archive_write_keeps_original_store():
    class DroppingStore(MemoryStore):
        async def async_save(self, data):
            pass

    original = legacy_data()
    store = MemoryStore(original)
    with pytest.raises(JournalError, match="nicht bestätigt"):
        await make_journal(store, DroppingStore())
    assert store.data == original


async def test_no_archive_adapter_cannot_drop_legacy_data():
    original = legacy_data()
    store = MemoryStore(original)
    with pytest.raises(JournalError):
        await make_journal(store)
    assert store.data == original


@pytest.mark.parametrize(
    "change",
    [
        {"intent": "unsafe"},
        {"intent": []},
        {"intent_created_at": "bad"},
        {"intent_created_at": "2026-10-25T10:00:00"},
    ],
)
async def test_invalid_optional_retry_metadata_is_rejected_without_overwrite(change):
    data = {"schema": 2, "binding": "http://host/mcp", "journal": {"key": {**record("done"), **change}}}
    store = MemoryStore(data)
    with pytest.raises(JournalError):
        await make_journal(store)
    assert store.data == data
