"""Official HA 2026.10 LLM tools platform; no replacement Assist API."""

import json

from homeassistant.components.llm import LLMTools
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import llm

from .const import DOMAIN, KNOWN_TOOLS, MENU_TOOLS, READ_TOOLS, RECIPE_READS
from .prompts import prompt_for_tools
from .runtime import Runtime


class YuvomiTool(llm.Tool):
    integration = DOMAIN

    def __init__(self, runtime: Runtime, remote_name: str, available=lambda: True):
        self.available = available
        self.runtime = runtime
        self.remote_name = remote_name
        self.name = f"{DOMAIN}__{remote_name}"
        self.description = runtime.tools[remote_name].description
        self.parameters = runtime.parameters[remote_name]
        self.annotations = llm.ToolAnnotations(
            read_only=remote_name in READ_TOOLS and remote_name not in MENU_TOOLS,
            destructive=remote_name not in KNOWN_TOOLS,
            idempotent=remote_name in READ_TOOLS and remote_name not in MENU_TOOLS,
            open_world=False,
        )

    async def async_call(self, hass, tool_input, llm_context):
        if not self.available():
            return llm.ToolResult(data={"isError": True, "code": "not_allowed"}, error=True)
        context = llm_context.context
        owner = json.dumps(
            [
                llm_context.platform,
                llm_context.assistant,
                llm_context.device_id,
                getattr(context, "user_id", None),
            ]
        )
        result = await self.runtime.call(
            self.remote_name,
            tool_input.tool_args,
            call_id=tool_input.id,
            scope=getattr(context, "id", ""),
            owner=owner,
            actor=context,
        )
        if self.remote_name in MENU_TOOLS | RECIPE_READS:
            result = {k: v for k, v in result.items() if k != "content"}
        return llm.ToolResult(data=result, error=bool(result.get("isError")))


@callback
def async_get_tools(hass: HomeAssistant, llm_context: llm.LLMContext, api_id: str) -> LLMTools | None:
    """Synchronous callback: all metadata was fetched asynchronously at setup."""
    if api_id != llm.LLM_API_ASSIST:
        return None
    runtimes = [
        r
        for r in hass.data.get(DOMAIN, {}).values()
        if getattr(r, "exposure", lambda: "assist")() == "assist"
    ]
    tools = [
        YuvomiTool(runtime, name, lambda r=runtime: getattr(r, "exposure", lambda: "assist")() == "assist")
        for runtime in runtimes
        for name in sorted(runtime.enabled())
    ]
    if not tools:
        return None
    return LLMTools(tools=tools, prompt=common_prompt(runtimes))


class YuvomiAPI(llm.API):
    """An opt-in carrier for the same authorized Runtime tools."""

    def __init__(self, hass, entry, runtime):
        super().__init__(hass=hass, id=f"yuvomi_family_{entry.entry_id}", name="Yuvomi MCP Familie")
        self.runtime = runtime

    async def async_get_api_instance(self, llm_context):
        runtime = self.runtime

        def available():
            return runtime.active and runtime.exposure() == "dedicated"

        tools = [YuvomiTool(runtime, n, available) for n in sorted(runtime.enabled())] if available() else []
        return llm.APIInstance(
            api=self,
            api_prompt=common_prompt([runtime]),
            llm_context=llm_context,
            tools=tools,
            custom_serializer=llm.selector_serializer,
        )


def common_prompt(runtimes):
    return prompt_for_tools(set().union(*(r.enabled() for r in runtimes)))
