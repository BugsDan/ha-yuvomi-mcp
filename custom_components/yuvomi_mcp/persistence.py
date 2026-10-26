"""HA atomic storage adapter; version 1 envelope permits reading the legacy Store."""

from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .journal import Journal


async def load_journal(hass, entry):
    store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}", atomic_writes=True)
    archive = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.catalog_archive_v1", atomic_writes=True)
    journal = Journal(store, entry.data["url"], archive)
    await journal.load()
    return journal


def planning_store(hass, entry):
    from .planning_config import PlanningStore

    return PlanningStore(
        Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.planning", atomic_writes=True), entry.data["url"]
    )
