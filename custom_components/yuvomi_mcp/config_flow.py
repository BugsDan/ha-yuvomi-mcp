"""UI setup, credential replacement, allowlist and trusted one-use approvals."""

import json

import probatio as vol
from homeassistant import config_entries
from homeassistant.const import CONF_URL
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import MCPClient, MCPError, normalize_url
from .const import CONF_EXPOSURE, CONF_TOKEN, CONF_TOOLS, DEFAULT_TOOLS, DEFAULT_URL, DOMAIN
from .journal_ui import JournalOptions
from .planning_ui import PlanningOptions
from .runtime import Runtime


def connection_schema(url=DEFAULT_URL, *, optional_token=False):
    token_key = vol.Optional(CONF_TOKEN) if optional_token else vol.Required(CONF_TOKEN)
    return vol.Schema(
        {
            vol.Required(CONF_URL, default=url): selector.TextSelector(),
            token_key: selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
        }
    )


async def validate_connection(hass, data):
    client = MCPClient(async_get_clientsession(hass), data[CONF_URL], data[CONF_TOKEN])
    await client.initialize()
    tools = await client.list_tools()
    # Check actual schema conversion before persisting any configuration.
    return Runtime(client, tools, lambda: set()).tools


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        errors = {}
        if user_input is not None:
            try:
                data = {CONF_URL: normalize_url(user_input[CONF_URL]), CONF_TOKEN: user_input[CONF_TOKEN]}
                tools = await validate_connection(self.hass, data)
            except ValueError:
                errors["base"] = "invalid_input"
            except MCPError as err:
                errors["base"] = err.code
            else:
                await self.async_set_unique_id(data[CONF_URL])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="Yuvomi MCP", data=data, options={CONF_TOOLS: sorted(DEFAULT_TOOLS & tools.keys())}
                )
        return self.async_show_form(step_id="user", data_schema=connection_schema(), errors=errors)

    async def async_step_reconfigure(self, user_input=None):
        return await self._credentials(self._get_reconfigure_entry(), "reconfigure", user_input)

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        return await self._credentials(self._get_reauth_entry(), "reauth_confirm", user_input)

    async def _credentials(self, entry, step_id, user_input):
        errors = {}
        if user_input is not None:
            try:
                data = {
                    CONF_URL: normalize_url(user_input[CONF_URL]),
                    CONF_TOKEN: user_input.get(CONF_TOKEN) or entry.data[CONF_TOKEN],
                }
                await validate_connection(self.hass, data)
            except ValueError:
                errors["base"] = "invalid_input"
            except MCPError as err:
                errors["base"] = err.code
            else:
                return self.async_update_reload_and_abort(entry, data=data, unique_id=data[CONF_URL])
        return self.async_show_form(
            step_id=step_id,
            data_schema=connection_schema(entry.data[CONF_URL], optional_token=True),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OptionsFlow()


class OptionsFlow(PlanningOptions, JournalOptions, config_entries.OptionsFlow):
    _tools = None
    _request_id = None

    async def async_step_init(self, user_input=None):
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "tools",
                "exposure",
                "planning",
                "approve",
                "executions",
            ],
        )

    async def async_step_exposure(self, user_input=None):
        errors = {}
        if user_input is not None:
            mode = user_input.get(CONF_EXPOSURE)
            if mode in {"assist", "dedicated"}:
                return self.async_create_entry(
                    title="", data={**self.config_entry.options, CONF_EXPOSURE: mode}
                )
            errors["base"] = "invalid_exposure"
        return self.async_show_form(
            step_id="exposure",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_EXPOSURE, default=self.config_entry.options.get(CONF_EXPOSURE, "assist")
                    ): selector.SelectSelector(selector.SelectSelectorConfig(options=["assist", "dedicated"]))
                }
            ),
        )

    async def async_step_tools(self, user_input=None):
        errors = {}
        if self._tools is None:
            try:
                self._tools = await validate_connection(self.hass, self.config_entry.data)
            except (MCPError, ValueError):
                return self.async_abort(reason="refresh_failed")
        choices = sorted(self._tools)
        if user_input is not None:
            selected = user_input.get(CONF_TOOLS, [])
            if not isinstance(selected, list) or not all(
                isinstance(n, str) and n in self._tools for n in selected
            ):
                errors["base"] = "invalid_tools"
            else:
                # Set options first so old tool instances lose authorization now,
                # even while an asynchronous reload is still pending.
                return self.async_create_entry(
                    title="", data={**self.config_entry.options, CONF_TOOLS: sorted(set(selected))}
                )
        enabled = self.config_entry.options.get(CONF_TOOLS, [])
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_TOOLS, default=[n for n in enabled if n in choices]
                ): selector.SelectSelector(selector.SelectSelectorConfig(options=choices, multiple=True))
            }
        )
        return self.async_show_form(step_id="tools", data_schema=schema, errors=errors)

    def _runtime(self):
        return self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id)

    async def async_step_approve(self, user_input=None):
        runtime = self._runtime()
        pending = runtime.pending() if runtime else []
        if not pending:
            return self.async_abort(reason="no_pending")
        if user_input is not None:
            self._request_id = user_input.get("request_id")
            return await self.async_step_confirm()
        return self.async_show_form(
            step_id="approve",
            data_schema=vol.Schema(
                {
                    vol.Required("request_id"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                {"value": item.request_id, "label": item.name + " · " + item.request_id[:8]}
                                for item in pending
                            ]
                        )
                    )
                }
            ),
        )

    async def async_step_confirm(self, user_input=None):
        runtime = self._runtime()
        pending = (
            next((p for p in runtime.pending() if p.request_id == self._request_id), None)
            if runtime
            else None
        )
        if not pending:
            return self.async_abort(reason="approval_expired")
        if user_input is not None:
            if user_input.get("confirm") is True and runtime.approve(self._request_id):
                return self.async_abort(reason="approved")
            return self.async_abort(reason="approval_cancelled")
        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema({vol.Required("confirm", default=False): selector.BooleanSelector()}),
            description_placeholders={
                "tool": pending.name,
                "arguments": runtime.client.redact(
                    json.dumps(pending.arguments, ensure_ascii=False, indent=2)
                ),
            },
        )
