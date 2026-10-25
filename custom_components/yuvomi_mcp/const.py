"""Constants for the Yuvomi MCP integration."""

DOMAIN = "yuvomi_mcp"
CONF_TOKEN = "api_token"
CONF_TOOLS = "enabled_tools"
DEFAULT_URL = "http://yuvomi.example:3015/mcp"
DEFAULT_TOOLS = frozenset(
    {
        "list_shopping_items",
        "add_shopping_item",
        "list_tasks",
        "create_task",
        "list_upcoming_events",
        "create_event",
    }
)
READ_TOOLS = frozenset(
    {
        "list_shopping_items",
        "list_shopping_categories",
        "suggest_shopping_items",
        "list_tasks",
        "list_upcoming_events",
    }
)
# Recognition controls confirmation/annotations, never configuration opt-in.
# Keep DEFAULT_TOOLS separate so categories and future tools stay disabled
# until the user explicitly selects them in the integration options.
KNOWN_TOOLS = DEFAULT_TOOLS | READ_TOOLS | {"add_shopping_items"}
PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
VERSION = "1.4.2"
