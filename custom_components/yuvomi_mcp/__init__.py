"""Yuvomi MCP tools contributed to Home Assistant Assist."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import AuthenticationError, MCPClient, MCPError
from .const import CONF_TOKEN, CONF_TOOLS, DOMAIN
from .journal import JournalError
from .persistence import load_journal
from .purchasing import Purchasing
from .runtime import Runtime
from .shopping_api import ShoppingAPI

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    client = MCPClient(async_get_clientsession(hass), entry.data[CONF_URL], entry.data[CONF_TOKEN])
    try:
        await client.initialize()
        tools = await client.list_tools()
        try:
            journal = await load_journal(hass, entry)
        except JournalError as err:
            _LOGGER.error("Yuvomi-Einkaufsjournal nicht verfügbar: %s", err)
            # Fail closed for shopping without taking unrelated MCP tools down.
            journal = None
        purchasing = Purchasing(ShoppingAPI(client), journal)
        runtime = Runtime(
            client, tools, lambda: set(entry.options.get(CONF_TOOLS, [])), purchasing=purchasing
        )
    except AuthenticationError:
        raise ConfigEntryAuthFailed("Der Yuvomi-API-Token ist ungültig.") from None
    except MCPError:
        raise ConfigEntryNotReady("Die Yuvomi-MCP-Verbindung konnte nicht eingerichtet werden.") from None
    entry.runtime_data = runtime
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime
    entry.async_on_unload(entry.add_update_listener(_async_update_options))
    return True


async def _async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    runtime = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if runtime:
        await runtime.close()
    return True
