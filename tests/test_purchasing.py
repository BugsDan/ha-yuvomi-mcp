"""Deterministic shopping with persistent crash barriers, never live Yuvomi."""

import asyncio
from copy import deepcopy

import pytest
from test_journal import MemoryStore, make_journal

from custom_components.yuvomi_mcp.journal import JournalError
from custom_components.yuvomi_mcp.purchasing import Purchasing
from custom_components.yuvomi_mcp.shopping_api import ShoppingFailure

CATEGORIES = [
    {"id": 1, "name": "Getränke"},
    {"id": 2, "name": "Obst & Gemüse"},
    {"id": 3, "name": "Sonstiges"},
]


def row(name="Tee", *, ident=1, checked=0, quantity=None, category="Getränke", list_id=1):
    return {
        "id": ident,
        "list_id": list_id,
        "name": name,
        "quantity": quantity,
        "category": category,
        "is_checked": checked,
        "notes": "Keep",
        "price_cents": 100,
    }


class API:
    def __init__(self, rows=None):
        self.rows = deepcopy(rows or [])
        self.writes = []
        self.reads = 0
        self.category_reads = 0
        self.error = None
        self.after_write = None
        self.categories_data = deepcopy(CATEGORIES)
        self.delay = 0

    async def lists(self):
        return [{"id": 1, "name": "Familie"}]

    async def categories(self):
        self.category_reads += 1
        return deepcopy(self.categories_data)

    async def items(self, list_id):
        self.reads += 1
        return deepcopy([r for r in self.rows if r["list_id"] == list_id])

    async def create(self, list_id, body, key):
        if self.delay:
            await asyncio.sleep(self.delay)
        self.writes.append(("POST", deepcopy(body), key))
        if self.error:
            raise self.error
        item = row(
            body["name"],
            ident=max([r["id"] for r in self.rows], default=0) + 1,
            list_id=list_id,
            quantity=body["quantity"],
            category=body["category"],
        )
        self.rows.append(item)
        if self.after_write:
            await self.after_write()
        return deepcopy(item)

    async def update(self, list_id, item_id, body):
        self.writes.append(("PATCH", deepcopy(body), item_id))
        if self.error:
            raise self.error
        item = next(r for r in self.rows if r["id"] == item_id)
        item.update(body)
        if self.after_write:
            await self.after_write()
        return deepcopy(item)


async def setup(rows=None, *, store=None):
    journal = await make_journal(store)
    api = API(rows)
    return Purchasing(api, journal), api, journal


async def run(engine, args=None, key="request", *, bulk=False, authorized=lambda: True):
    return await engine.run(args or {"name": "Tee", "category": "Getränke"}, key, authorized, bulk=bulk)


async def test_open_item_increases_without_duplicate_and_preserves_other_fields():
    engine, api, _ = await setup([row(quantity="3 l")])
    result = await run(engine)
    assert not result["isError"]
    assert result["items"][0]["status"] == "increased"
    assert len(api.rows) == 1 and len(api.writes) == 1
    assert api.rows[0]["quantity"] == "4 l" and api.rows[0]["notes"] == "Keep"


async def test_checked_item_reuses_id_defaults_new_quantity_and_preserves_metadata():
    engine, api, _ = await setup([row(checked=1, quantity="99 l")])
    result = await run(engine, {"name": "Tee"})
    assert result["items"][0]["status"] == "reactivated"
    assert api.writes == [("PATCH", {"is_checked": False, "quantity": "1"}, 1)]
    assert api.rows[0]["notes"] == "Keep" and api.rows[0]["price_cents"] == 100
    assert len(api.rows) == 1


@pytest.mark.parametrize("rows", [[row(), row(ident=2)], [row(checked=1), row(ident=2, checked=1)]])
async def test_ambiguous_existing_rows_are_not_cleaned_up(rows):
    engine, api, _ = await setup(rows)
    assert (await run(engine))["code"] == "product_unclear"
    assert not api.writes and api.rows == rows


async def test_open_match_takes_precedence_over_checked_old_copy():
    engine, api, _ = await setup([row(), row(ident=2, checked=1)])
    assert (await run(engine))["items"][0]["status"] == "replaced"
    assert len(api.writes) == 1 and api.writes[0][2] == 1


async def test_parallel_new_requests_are_serialized_by_list():
    engine, api, _ = await setup()
    api.delay = 0.02
    first, second = await asyncio.gather(run(engine, key="a"), run(engine, key="b"))
    assert {first["items"][0]["status"], second["items"][0]["status"]} == {"created"}
    assert len(api.writes) == 1


async def test_same_request_replays_after_restart_even_if_article_checked_again():
    store = MemoryStore()
    engine, api, _ = await setup(store=store)
    original = await run(engine)
    api.rows[0]["is_checked"] = 1
    engine = Purchasing(api, await make_journal(store))
    assert await run(engine) == original
    assert len(api.writes) == 1 and api.rows[0]["is_checked"] == 1


async def test_timeout_persists_unknown_and_blocks_new_request_after_restart():
    store = MemoryStore()
    engine, api, _ = await setup(store=store)
    api.error = ShoppingFailure("execution_unconfirmed", "timeout", uncertain=True)
    result = await run(engine)
    assert result["code"] == "execution_unconfirmed"
    engine = Purchasing(api, await make_journal(store))
    assert (await run(engine, key="another"))["code"] == "execution_unconfirmed"
    assert len(api.writes) == 1


async def test_timeout_after_commit_can_only_be_reconciled_by_reading_not_resending():
    engine, api, journal = await setup()

    async def timeout():
        raise ShoppingFailure("execution_unconfirmed", "lost reply", uncertain=True)

    api.after_write = timeout
    assert (await run(engine))["isError"]
    key = next(iter(journal.data["journal"]))
    result = await engine.reconcile(key)
    assert result["status"] == "state_observed"
    assert len(api.writes) == 1
    assert (await run(engine))["items"][0]["status"] == "state_observed"


async def test_unresolved_absent_item_remains_blocked_after_review():
    engine, api, journal = await setup()
    api.error = ShoppingFailure("execution_unconfirmed", "timeout", uncertain=True)
    await run(engine)
    with pytest.raises(JournalError, match="nicht eindeutig"):
        await engine.reconcile(next(iter(journal.data["journal"])))
    assert engine.blocked(1) and len(api.writes) == 1


async def test_disk_failure_before_network_never_writes():
    engine, api, journal = await setup()
    journal.store.fail = True
    assert (await run(engine))["isError"]
    assert not api.writes


async def test_disk_failure_after_remote_write_keeps_prepared_barrier_and_never_claims_not_executed():
    engine, api, journal = await setup()

    async def fail_disk():
        journal.store.fail = True

    api.after_write = fail_disk
    result = await run(engine)
    assert result["code"] == "execution_unconfirmed"
    assert result["items"][0]["error"] == "execution_unconfirmed"
    assert engine.blocked(1)
    assert len(api.writes) == 1


async def test_cancellation_leaves_durable_prepared_record():
    store = MemoryStore()
    engine, api, _ = await setup(store=store)

    async def cancel():
        raise asyncio.CancelledError

    api.after_write = cancel
    with pytest.raises(asyncio.CancelledError):
        await run(engine)
    restored = Purchasing(api, await make_journal(store))
    assert restored.blocked(1)


async def test_safe_rejection_is_not_claimed_as_success_or_unknown():
    engine, api, _ = await setup()
    api.error = ShoppingFailure("shopping_rejected", "403")
    assert (await run(engine))["code"] == "shopping_rejected"
    assert not engine.blocked(1)


async def test_bulk_reads_state_once_and_reports_each_item():
    engine, api, _ = await setup([row()])
    result = await run(
        engine,
        {"items": [{"name": "Tee", "category": "Getränke"}, {"name": "Apfel", "category": "Obst & Gemüse"}]},
        bulk=True,
    )
    assert [i["status"] for i in result["items"]] == ["replaced", "created"]
    assert api.reads == 2 and api.category_reads == 1
    assert len(api.writes) == 2


async def test_bulk_preflight_failure_saves_no_shopping_rows():
    engine, api, _ = await setup()
    result = await run(
        engine,
        {"items": [{"name": "Tee", "category": "Getränke"}, {"name": "X", "category": "nonexistent"}]},
        bulk=True,
    )
    assert result["code"] == "invalid_category"
    assert not api.writes


async def test_bulk_unknown_outcome_stops_and_marks_later_items_not_executed():
    engine, api, _ = await setup()
    api.error = ShoppingFailure("execution_unconfirmed", "timeout", uncertain=True)
    result = await run(
        engine,
        {"items": [{"name": "Tee", "category": "Getränke"}, {"name": "Apfel", "category": "Obst & Gemüse"}]},
        bulk=True,
    )
    assert result["items"][1]["error"] == "not_executed"
    assert len(api.writes) == 1


async def test_normalized_duplicates_in_bulk_require_clarification():
    engine, api, _ = await setup()
    assert (
        await run(
            engine,
            {"items": [{"name": "Tee", "category": "Getränke"}, {"name": " TEE ", "category": "Getränke"}]},
            bulk=True,
        )
    )["code"] == "product_unclear"
    assert not api.writes


async def test_additional_quantity_uses_absolute_target_and_is_not_added_twice():
    engine, api, _ = await setup([row(quantity="2 l")])
    args = {"items": [{"name": "Tee", "quantity": "1,5 Liter", "operation": "increase"}]}
    assert (await run(engine, args, bulk=True))["items"][0]["status"] == "increased"
    assert api.rows[0]["quantity"] == "3.5 l"
    await run(engine, args, bulk=True)
    assert len(api.writes) == 1


@pytest.mark.parametrize(
    "current,extra", [(None, "1 l"), ("2 l", "200 ml"), ("groß", "1 l"), ("2 l", "-1 l")]
)
async def test_uncertain_arithmetic_replaces_without_guessing(current, extra):
    engine, api, _ = await setup([row(quantity=current)])
    result = await run(
        engine, {"items": [{"name": "Tee", "quantity": extra, "operation": "increase"}]}, bulk=True
    )
    assert not result["isError"] and result["items"][0]["action"] == "replaced"
    assert api.rows[0]["quantity"] == extra


async def test_explicit_quantity_on_open_item_is_added():
    engine, api, _ = await setup([row(quantity="2 l")])
    assert (await run(engine, {"name": "Tee", "quantity": "3 l"}))["items"][0]["action"] == "increased"
    assert api.rows[0]["quantity"] == "5 l"


async def test_authorization_revoked_during_read_prevents_write():
    engine, api, _ = await setup()
    allowed = [True]
    original = api.items

    async def revoke(list_id):
        allowed[0] = False
        return await original(list_id)

    api.items = revoke
    assert (await run(engine, authorized=lambda: allowed[0]))["code"] == "not_allowed"
    assert not api.writes


async def test_same_additional_quantity_in_new_alexa_turn_is_replayed_conservatively():
    engine, api, _ = await setup([row(quantity="2 l")])
    args = {"items": [{"name": "Tee", "quantity": "1 l", "operation": "increase"}]}
    assert not (await run(engine, args, bulk=True, key="first-turn"))["isError"]
    result = await run(engine, args, bulk=True, key="new-alexa-request")
    assert not result["isError"] and result["items"][0]["replayed"]
    assert api.rows[0]["quantity"] == "3 l" and len(api.writes) == 1


async def test_foreign_change_before_patch_is_not_overwritten():
    engine, api, _ = await setup([row(checked=1)])
    original = api.items

    async def concurrent(list_id):
        if api.reads == 1:
            api.rows[0]["quantity"] = "5 l"
        return await original(list_id)

    api.items = concurrent
    assert (await run(engine))["code"] == "concurrent_change"
    assert not api.writes and api.rows[0]["quantity"] == "5 l"


async def test_partial_bulk_replay_reports_known_success_and_unknown_without_resending():
    store = MemoryStore()
    engine, api, _ = await setup(store=store)

    async def fail_second():
        if len(api.writes) == 2:
            raise ShoppingFailure("execution_unconfirmed", "lost reply", uncertain=True)

    api.after_write = fail_second
    args = {
        "items": [
            {"name": "Tee", "category": "Getränke"},
            {"name": "Apfel", "category": "Obst & Gemüse"},
            {"name": "Brot", "category": "Sonstiges"},
        ]
    }
    first = await run(engine, args, bulk=True)
    assert first["items"][0]["status"] == "created"
    restored = Purchasing(api, await make_journal(store))
    replay = await run(restored, args, bulk=True)
    assert replay["items"][0]["status"] == "created"
    assert replay["items"][1]["error"] == "execution_unconfirmed"
    assert replay["items"][2]["error"] == "not_executed"
    assert len(api.writes) == 2


async def test_shutdown_drains_writer_before_closing_journal():
    engine, api, journal = await setup()
    entered, release = asyncio.Event(), asyncio.Event()

    async def pause():
        entered.set()
        await release.wait()

    api.after_write = pause
    task = asyncio.create_task(run(engine))
    await entered.wait()
    closing = asyncio.create_task(engine.close())
    await asyncio.sleep(0)
    assert not closing.done()
    release.set()
    assert not (await task)["isError"]
    await closing
    assert journal.closed
    assert (await run(engine, key="later"))["code"] == "not_allowed"
    assert len(api.writes) == 1


async def test_recent_journal_entries_are_not_evicted_to_allow_duplicate_increases(monkeypatch):
    from custom_components.yuvomi_mcp import purchasing

    monkeypatch.setattr(purchasing, "MAX_JOURNAL", 1)
    engine, api, _ = await setup()
    assert not (await run(engine))["isError"]
    assert (await run(engine, {"name": "Apfel", "category": "Obst & Gemüse"}, key="new"))["isError"]
    assert len(api.writes) == 1


async def test_quantity_whitespace_is_preserved_before_server_echo_validation():
    engine, api, _ = await setup()
    result = await run(engine, {"name": "Tee", "quantity": " 2 Liter ", "category": "Getränke"})
    assert not result["isError"] and api.rows[0]["quantity"] == " 2 Liter "


async def test_categories_read_failure_prevents_every_shopping_write():
    engine, api, _ = await setup()

    async def unavailable():
        raise ShoppingFailure("shopping_read_failed", "no categories")

    api.categories = unavailable
    assert (await run(engine))["code"] == "shopping_read_failed"
    assert not api.writes


@pytest.mark.parametrize(
    "existing_name,requested",
    [
        ("Kochschokolade", "Schokolade"),
        ("Thon klein", "Thon gross"),
        ("Mais klein", "Mais gross"),
        ("Tee", "Eistee"),
        ("Migros Reis", "Coop Reis"),
        ("Apfel", "Äpfel"),
    ],
)
async def test_distinct_products_and_brands_are_never_merged(existing_name, requested):
    engine, api, _ = await setup([row(existing_name)])
    result = await run(engine, {"name": requested, "category": "Sonstiges"})
    assert result["items"][0]["status"] == "created"
    assert [r["name"] for r in api.rows] == [existing_name, requested]


@pytest.mark.parametrize("requested", ["  TEE  ", "tee", "Ｔｅｅ"])
async def test_case_unicode_and_whitespace_match_without_renaming(requested):
    engine, api, _ = await setup([row("Tee", checked=1)])
    result = await run(engine, {"name": requested, "category": "invented"})
    assert result["items"][0]["status"] == "reactivated"
    assert result["items"][0]["name"] == api.rows[0]["name"] == "Tee"
    assert api.rows[0]["category"] == "Getränke" and len(api.rows) == 1


@pytest.mark.parametrize("checked", [False, True])
@pytest.mark.parametrize("category", [None, "Sonstiges", "invented", "Getr_nke"])
async def test_current_yuvomi_category_always_wins(checked, category):
    engine, api, journal = await setup([row(checked=checked, category="Obst & Gemüse")])
    args = {"name": "Tee"}
    if category is not None:
        args["category"] = category
    result = await run(engine, args)
    assert not result["isError"] and result["items"][0]["category"] == "Obst & Gemüse"
    assert api.rows[0]["category"] == "Obst & Gemüse"
    assert set(journal.data) == {"schema", "binding", "journal"}


async def test_manual_category_change_is_immediately_used_after_restart():
    store = MemoryStore()
    engine, api, _ = await setup([row()], store=store)
    await run(engine)
    api.rows[0].update(category="Obst & Gemüse", is_checked=1)
    restored = Purchasing(api, await make_journal(store))
    result = await run(restored, {"name": "Tee", "category": "Getränke"}, key="new")
    assert result["items"][0]["category"] == "Obst & Gemüse"
    assert api.rows[0]["category"] == "Obst & Gemüse" and api.rows[0]["is_checked"] == 0


async def test_deleted_item_has_no_category_memory_in_journal():
    engine, api, journal = await setup()
    await run(engine)
    api.rows.clear()
    result = await run(engine, {"name": "Tee"}, key="new")
    assert result["code"] == "category_required"
    assert len(api.writes) == 1 and not api.rows
    result = await run(engine, {"name": "Tee", "category": "Sonstiges"}, key="corrected")
    assert result["items"][0]["category"] == "Sonstiges"
    assert not hasattr(journal, "find")


@pytest.mark.parametrize("bulk", [False, True])
async def test_category_followup_is_possible_without_prior_writes(bulk):
    engine, api, journal = await setup()
    args = {"items": [{"name": "Aubergine"}]} if bulk else {"name": "Aubergine"}
    result = await run(engine, args, bulk=bulk)
    assert result["code"] == "category_required"
    assert result["items"][0]["valid_categories"] == [c["name"] for c in CATEGORIES]
    assert not api.writes and not journal.data["journal"]
    item = args["items"][0] if bulk else args
    item["category"] = "Obst & Gemüse"
    result = await run(engine, args, bulk=bulk)
    assert not result["isError"] and api.rows[0]["category"] == "Obst & Gemüse"


async def test_bulk_reports_all_missing_categories_in_one_preflight():
    engine, api, journal = await setup([row()])
    args = {"items": [{"name": "Tee"}, {"name": "Avocado"}, {"name": "Reis"}]}
    result = await run(engine, args, bulk=True)
    assert [i["error"] for i in result["items"]] == ["not_executed", "category_required", "category_required"]
    assert api.reads == api.category_reads == 1
    assert not api.writes and not journal.data["journal"]


@pytest.mark.parametrize("category", ["Getränke", "Getr_nke", "Obst & Gemüse", "Süsses und Backzutaten"])
async def test_new_categories_validate_and_preserve_current_unicode(category):
    engine, api, _ = await setup()
    api.categories_data.append({"id": 4, "name": "Süsses und Backzutaten"})
    result = await run(engine, {"name": "My Brand", "category": category})
    assert not result["isError"]
    assert api.rows[0]["category"] == ("Getränke" if category == "Getr_nke" else category)
    assert api.rows[0]["name"] == "My Brand"


async def test_unknown_category_never_reaches_rest():
    engine, api, _ = await setup()
    result = await run(engine, {"name": "New", "category": "invented"})
    assert result["code"] == "invalid_category" and not api.writes


@pytest.mark.parametrize("bulk", [False, True])
async def test_explicit_total_sets_absolute_amount_and_replays_safely(bulk):
    store = MemoryStore()
    engine, api, _ = await setup([row(quantity="2 l")], store=store)
    item = {"name": "Tee", "quantity": "3 l", "operation": "set"}
    args = {"items": [item]} if bulk else item
    result = await run(engine, args, bulk=bulk)
    assert result["items"][0]["status"] == "quantity_set"
    assert api.rows[0]["quantity"] == "3 l"
    engine = Purchasing(api, await make_journal(store))
    assert await run(engine, args, bulk=bulk) == result
    assert len(api.writes) == 1
    assert (await run(engine, args, key="new", bulk=bulk))["items"][0]["status"] == "already_present"


async def test_checked_explicit_quantity_replaces_old_amount_and_keeps_id():
    engine, api, _ = await setup([row(checked=1, quantity="99 l")])
    result = await run(engine, {"name": "Tee", "quantity": "2 l", "operation": "set"})
    assert result["items"][0]["status"] == "reactivated"
    assert api.rows[0]["quantity"] == "2 l" and api.rows[0]["id"] == 1


@pytest.mark.parametrize(
    "operation,quantity",
    [
        ("set", None),
        ("set", ""),
        ("set", "   "),
    ],
)
async def test_ambiguous_quantity_operations_never_write(operation, quantity):
    engine, api, _ = await setup([row(quantity="2 l")])
    args = {"name": "Tee", "operation": operation}
    if quantity is not None:
        args["quantity"] = quantity
    result = await run(engine, args)
    assert result["code"] == "quantity_unclear" and not api.writes


async def test_foreign_category_change_between_read_and_patch_is_not_overwritten():
    engine, api, _ = await setup([row(checked=1)])
    original = api.items

    async def concurrent(list_id):
        if api.reads == 1:
            api.rows[0]["category"] = "Sonstiges"
        return await original(list_id)

    api.items = concurrent
    assert (await run(engine))["code"] == "concurrent_change"
    assert not api.writes and api.rows[0]["category"] == "Sonstiges"


async def test_migrated_unresolved_journal_blocks_writes_without_loading_products():
    from test_journal import legacy_data

    old = legacy_data()
    store, archive = MemoryStore(old), MemoryStore()
    journal = await make_journal(store, archive)
    api = API()
    engine = Purchasing(api, journal)
    result = await run(engine)
    assert result["code"] == "execution_unconfirmed" and not api.writes
    assert archive.data == old and journal.data["journal"] == old["journal"]


async def test_migrated_recent_increase_keeps_repeat_guard():
    from test_journal import legacy_data, record

    entry = record("done", "PATCH")
    entry.update(name="Tee", delta="1 l")
    journal = await make_journal(MemoryStore(legacy_data({"key": entry})), MemoryStore())
    api = API([row(quantity="3 l")])
    result = await run(Purchasing(api, journal), {"name": "Tee", "quantity": "1 l", "operation": "increase"})
    assert result["code"] == "execution_unconfirmed" and not api.writes


@pytest.mark.parametrize("bulk", [False, True])
@pytest.mark.parametrize(
    "quantity", ["1 Flasche", "2 Tuben", "1 Packung", " 2 Tuben ", "½ Flasche", "einige"]
)
@pytest.mark.parametrize("operation", ["ensure", "set"])
async def test_new_item_free_text_quantities_are_preserved(bulk, quantity, operation):
    engine, api, _ = await setup()
    item = {"name": "Mayonnaise", "quantity": quantity, "operation": operation, "category": "Sonstiges"}
    result = await run(engine, {"items": [item]} if bulk else item, bulk=bulk)
    assert not result["isError"]
    assert api.writes[0][1]["quantity"] == api.rows[0]["quantity"] == quantity
    assert result["items"][0]["quantity"] == quantity


@pytest.mark.parametrize("bulk", [False, True])
async def test_two_tubes_mayonnaise_automatically_replaces_open_pack(bulk):
    engine, api, _ = await setup([row("Mayonnaise", quantity="1 Packung")])
    item = {"name": "Mayonnaise", "quantity": "2 Tuben"}
    args = {"items": [item]} if bulk else item
    result = await run(engine, args, bulk=bulk)
    assert not result["isError"] and result["items"][0]["action"] == "replaced"
    assert api.rows[0]["quantity"] == "2 Tuben"
    item["operation"] = "set"
    result = await run(engine, args, bulk=bulk, key="correction")
    assert result["items"][0]["status"] == "already_present"
    assert result["items"][0]["quantity"] == api.rows[0]["quantity"] == "2 Tuben"
    assert len(api.rows) == 1 and api.rows[0]["id"] == 1
    assert await run(engine, args, bulk=bulk, key="correction") == result
    assert len(api.writes) == 1


@pytest.mark.parametrize("operation", ["ensure", "set"])
async def test_checked_free_text_reactivation_keeps_id_category_and_requested_quantity(operation):
    engine, api, _ = await setup([row("Mayonnaise", checked=1, quantity="1 Packung")])
    result = await run(engine, {"name": "Mayonnaise", "quantity": "2 Tuben", "operation": operation})
    assert result["items"][0]["status"] == "reactivated"
    assert api.writes == [("PATCH", {"is_checked": False, "quantity": "2 Tuben"}, 1)]
    assert api.rows[0]["category"] == "Getränke" and len(api.rows) == 1


async def test_open_identical_count_unit_is_added():
    engine, api, _ = await setup([row("Mayonnaise", quantity="2 Tuben")])
    result = await run(engine, {"name": "Mayonnaise", "quantity": "2 Tuben"})
    assert result["items"][0]["status"] == "increased" and api.rows[0]["quantity"] == "4 Tuben"


@pytest.mark.parametrize(
    "current,extra,expected,action",
    [
        ("1 Packung", "2 Tuben", "2 Tuben", "replaced"),
        ("1 Tube", "2 Tuben", "3 Tuben", "increased"),
        ("1 Flasche", "1 Flasche", "2 Flaschen", "increased"),
        ("einige", "2", "2", "replaced"),
        ("2 l", "½ Flasche", "½ Flasche", "replaced"),
    ],
)
async def test_free_text_addition_or_replacement_is_transparent(current, extra, expected, action):
    engine, api, _ = await setup([row("Mayonnaise", quantity=current)])
    result = await run(engine, {"name": "Mayonnaise", "quantity": extra, "operation": "increase"})
    assert not result["isError"] and result["items"][0]["action"] == action
    assert api.rows[0]["quantity"] == expected


@pytest.mark.parametrize("quantity", ["", "   ", "2\nTuben", "2\x00Tuben", "x" * 257, 2, True])
@pytest.mark.parametrize("operation", ["ensure", "set"])
async def test_free_text_still_rejects_empty_unsafe_or_invalid_quantities(quantity, operation):
    engine, api, _ = await setup()
    result = await run(
        engine, {"name": "Mayonnaise", "quantity": quantity, "category": "Sonstiges", "operation": operation}
    )
    assert result["code"] == "quantity_unclear" and not api.writes


async def test_free_text_set_is_replayed_after_restart_without_overwriting_later_remote_changes():
    store = MemoryStore()
    engine, api, _ = await setup([row("Mayonnaise", quantity="1 Packung")], store=store)
    args = {"name": "Mayonnaise", "quantity": "2 Tuben", "operation": "set"}
    original = await run(engine, args)
    api.rows[0]["quantity"] = "3 Flaschen"
    restored = Purchasing(api, await make_journal(store))
    assert await run(restored, args) == original
    assert api.rows[0]["quantity"] == "3 Flaschen" and len(api.writes) == 1


@pytest.mark.parametrize("bulk", [False, True])
@pytest.mark.parametrize("operation", ["ensure", "increase"])
@pytest.mark.parametrize(
    "current,incoming,expected,action",
    [
        ("1 Packung", "2 Packungen", "3 Packungen", "increased"),
        ("1", "2", "3", "increased"),
        ("1 Packung", "2 Tuben", "2 Tuben", "replaced"),
        ("1 Flasche", "½ Flasche", "½ Flasche", "replaced"),
        (None, "2 Tuben", "2 Tuben", "replaced"),
        ("1 Packung", " 2 Tuben ", " 2 Tuben ", "replaced"),
    ],
)
async def test_open_ensure_and_increase_share_transparent_quantity_results(
    bulk, operation, current, incoming, expected, action
):
    engine, api, _ = await setup([row("Chips", quantity=current)])
    item = {"name": "Chips", "quantity": incoming, "operation": operation}
    result = await run(engine, {"items": [item]} if bulk else item, bulk=bulk)
    assert not result["isError"]
    entry = result["items"][0]
    assert entry["old_quantity"] == current
    assert entry["new_quantity"] == entry["quantity"] == expected
    assert entry["action"] == entry["status"] == action
    assert bool(entry["replacement_reason"]) == (action == "replaced")
    assert len(api.rows) == 1 and api.rows[0]["id"] == 1
    assert api.rows[0]["quantity"] == expected and api.rows[0]["category"] == "Getränke"


@pytest.mark.parametrize("operation", ["ensure", "increase"])
@pytest.mark.parametrize("checked", [False, True])
async def test_new_and_checked_items_default_to_one_for_both_operations(operation, checked):
    engine, api, _ = await setup([row("Chips", quantity="99 Packungen", checked=True)] if checked else [])
    result = await run(engine, {"name": "Chips", "operation": operation, "category": "Sonstiges"})
    entry = result["items"][0]
    assert entry["quantity"] == entry["new_quantity"] == "1" and entry["quantity_defaulted"]
    assert entry["old_quantity"] == ("99 Packungen" if checked else None)
    assert entry["action"] == ("reactivated" if checked else "created")
    assert len(api.rows) == 1
    assert api.rows[0]["category"] == ("Getränke" if checked else "Sonstiges")


@pytest.mark.parametrize(
    "current,expected,action",
    [
        ("2", "3", "increased"),
        ("2 Packungen", "3 Packungen", "increased"),
        ("2 Tuben", "3 Tuben", "increased"),
        ("einige", "1", "replaced"),
    ],
)
async def test_missing_quantity_adds_one_current_unit_when_identifiable(current, expected, action):
    engine, api, _ = await setup([row(quantity=current)])
    result = await run(engine)
    assert result["items"][0]["action"] == action
    assert api.rows[0]["quantity"] == expected


@pytest.mark.parametrize("operation", ["ensure", "increase"])
async def test_explicit_checked_quantity_is_never_added_to_old_quantity(operation):
    engine, api, _ = await setup([row(quantity="99 l", checked=True)])
    entry = (await run(engine, {"name": "Tee", "quantity": "2 Tuben", "operation": operation}))["items"][0]
    assert (
        entry["action"] == "reactivated"
        and entry["old_quantity"] == "99 l"
        and entry["new_quantity"] == "2 Tuben"
    )
    assert api.writes == [("PATCH", {"is_checked": False, "quantity": "2 Tuben"}, 1)]


async def test_ensure_retry_after_restart_and_new_id_or_operation_does_not_add_again():
    store = MemoryStore()
    engine, api, _ = await setup([row(quantity="1 Packung")], store=store)
    args = {"name": "Tee", "quantity": "2 Packungen"}
    first = await run(engine, args, key="first")
    assert first["items"][0]["new_quantity"] == "3 Packungen"
    restored = Purchasing(api, await make_journal(store))
    assert await run(restored, args, key="first") == first
    replay = await run(restored, {**args, "operation": "increase"}, key="alexa-retry")
    assert replay["items"][0]["replayed"]
    assert replay["items"][0]["action"] == "increased" and replay["items"][0]["old_quantity"] == "1 Packung"
    assert api.rows[0]["quantity"] == "3 Packungen" and len(api.writes) == 1
    # The retry's own ID is durably remembered too.
    record = restored.journal.data["journal"][restored._key("alexa-retry", 0)]
    assert record["result"] == replay["items"][0]
    assert record["intent_created_at"] == next(iter(store.data["journal"].values()))["intent_created_at"]


async def test_replacement_retry_is_persisted_without_replacing_again():
    store = MemoryStore()
    engine, api, _ = await setup([row(quantity="1 Packung")], store=store)
    args = {"name": "Tee", "quantity": "2 Tuben"}
    await run(engine, args, key="first")
    engine = Purchasing(api, await make_journal(store))
    assert (await run(engine, args, key="second"))["items"][0]["replayed"]
    assert api.rows[0]["quantity"] == "2 Tuben" and len(api.writes) == 1


async def test_missing_quantity_retry_never_increments_twice():
    engine, api, _ = await setup([row(quantity="2")])
    await run(engine, key="first")
    replay = await run(engine, key="second")
    assert replay["items"][0]["replayed"] and api.rows[0]["quantity"] == "3"
    assert len(api.writes) == 1


async def test_retry_with_changed_remote_quantity_does_not_add_to_new_state():
    engine, api, _ = await setup([row(quantity="2")])
    await run(engine, key="first")
    api.rows[0]["quantity"] = "99"
    result = await run(engine, key="retry")
    assert result["code"] == "execution_unconfirmed" and len(api.writes) == 1
    assert api.rows[0]["quantity"] == "99"


async def test_retry_preserves_manual_category_change_without_adding_again():
    engine, api, _ = await setup([row(quantity="2")])
    await run(engine, key="first")
    api.rows[0]["category"] = "Sonstiges"
    result = await run(engine, key="retry")
    assert result["items"][0]["category"] == "Sonstiges" and result["items"][0]["replayed"]
    assert len(api.writes) == 1


async def test_distinct_requested_quantities_are_added_under_parallel_list_lock():
    engine, api, _ = await setup([row(quantity="1")])
    results = await asyncio.gather(
        run(engine, {"name": "Tee", "quantity": "2"}, key="a"),
        run(engine, {"name": "Tee", "quantity": "3"}, key="b"),
    )
    assert all(not result["isError"] for result in results)
    assert api.rows[0]["quantity"] == "6" and len(api.writes) == 2


async def test_same_new_request_different_owners_is_not_suppressed():
    engine, api, _ = await setup([row(quantity="1")])
    args = {"name": "Tee", "quantity": "2"}
    await engine.run(args, "a", lambda: True, owner="user-a")
    await engine.run(args, "b", lambda: True, owner="user-b")
    assert api.rows[0]["quantity"] == "5" and len(api.writes) == 2


async def test_set_is_absolute_and_does_not_suppress_following_addition():
    engine, api, _ = await setup([row(quantity="99")])
    result = await run(engine, {"name": "Tee", "quantity": "2", "operation": "set"}, key="set")
    assert (
        result["items"][0]["action"] == "replaced"
        and result["items"][0]["replacement_reason"] == "explicit_set"
    )
    await run(engine, {"name": "Tee", "quantity": "2"}, key="add")
    assert api.rows[0]["quantity"] == "4" and len(api.writes) == 2


async def test_partial_bulk_timeout_does_not_readd_first_item_on_retry():
    engine, api, _ = await setup([row(quantity="1"), row("Apfel", ident=2, quantity="1")])

    async def fail_second():
        if len(api.writes) == 2:
            raise ShoppingFailure("execution_unconfirmed", "lost response", uncertain=True)

    api.after_write = fail_second
    args = {"items": [{"name": "Tee", "quantity": "2"}, {"name": "Apfel", "quantity": "2"}]}
    first = await run(engine, args, bulk=True)
    assert first["items"][0]["new_quantity"] == "3"
    assert (await run(engine, args, bulk=True))["items"][1]["error"] == "execution_unconfirmed"
    assert len(api.writes) == 2 and api.rows[0]["quantity"] == "3"


async def test_retry_alias_does_not_extend_window_but_remains_durably_replayable():
    from datetime import datetime, timedelta, timezone

    engine, api, journal = await setup([row(quantity="1")])
    args = {"name": "Tee", "quantity": "2"}
    await run(engine, args, key="a")
    replay = await run(engine, args, key="b")
    past = (datetime.now(timezone.utc) - timedelta(seconds=121)).isoformat()

    def age(data):
        for entry in data["journal"].values():
            entry["intent_created_at"] = past

    await journal.change(age)
    assert not (await run(engine, args, key="c"))["isError"]
    assert api.rows[0]["quantity"] == "5" and len(api.writes) == 2
    assert await run(engine, args, key="b") == replay
    assert api.rows[0]["quantity"] == "5" and len(api.writes) == 2


async def test_single_retry_as_bulk_does_not_add_again():
    engine, api, _ = await setup([row(quantity="1")])
    item = {"name": "Tee", "quantity": "2"}
    await run(engine, item, key="single")
    result = await run(engine, {"items": [item]}, key="bulk", bulk=True)
    assert result["items"][0]["replayed"] and api.rows[0]["quantity"] == "3"
    assert len(api.writes) == 1


async def test_renamed_old_id_cannot_be_reported_as_replay_for_another_matching_item():
    engine, api, _ = await setup([row(quantity="1")])
    args = {"name": "Tee", "quantity": "2"}
    await run(engine, args, key="a")
    api.rows[0]["name"] = "Kaffee"
    api.rows.append(row("Tee", ident=2, quantity="1"))
    result = await run(engine, args, key="b")
    assert result["code"] == "execution_unconfirmed" and len(api.writes) == 1
    assert api.rows[1]["quantity"] == "1"


async def test_numeric_unit_variants_are_recognized_as_retry():
    engine, api, _ = await setup([row(quantity="1 Packung")])
    await run(engine, {"name": "Tee", "quantity": "2 Packungen"}, key="a")
    result = await run(engine, {"name": "TEE", "quantity": "2,0 Packung", "operation": "increase"}, key="b")
    assert result["items"][0]["replayed"] and len(api.writes) == 1
    assert api.rows[0]["quantity"] == "3 Packungen"
