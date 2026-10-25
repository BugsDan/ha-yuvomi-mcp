"""Verify the actual, pinned HA APIs and record hashes. No HA server access."""

import ast
import hashlib
import json
import re
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://raw.githubusercontent.com/home-assistant/core/2026.10.2/"
PATHS = [
    "homeassistant/components/llm/__init__.py",
    "homeassistant/helpers/llm.py",
    "homeassistant/components/mcp/coordinator.py",
    "homeassistant/config_entries.py",
    "homeassistant/helpers/integration_platform.py",
    "pyproject.toml",
    "homeassistant/components/config/config_entries.py",
]


def main():
    evidence = {"version": "2026.10.2", "sources": {}}
    sources = {}
    for path in PATHS:
        data = urlopen(BASE + path, timeout=30).read()
        sources[path] = data.decode()
        evidence["sources"][path] = {"url": BASE + path, "sha256": hashlib.sha256(data).hexdigest()}
    tree = ast.parse(sources[PATHS[0]])
    platform = next(
        n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "LLMToolsPlatformProtocol"
    )
    method = next(n for n in platform.body if isinstance(n, ast.FunctionDef) and n.name == "async_get_tools")
    assert [a.arg for a in method.args.args] == ["self", "hass", "llm_context", "api_id"]
    assert ast.unparse(method.returns) == "LLMTools | None"
    aggregator = next(
        n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "async_get_tools"
    )
    assert [a.arg for a in aggregator.args.args] == ["hass", "llm_context", "api_id"]
    assert "platform.async_get_tools(hass, llm_context, api_id)" in sources[PATHS[0]]
    assert "parameters = from_openapi(tool.inputSchema)" in sources[PATHS[2]]
    helper_tree = ast.parse(sources[PATHS[1]])
    tool_class = next(n for n in helper_tree.body if isinstance(n, ast.ClassDef) and n.name == "Tool")
    tool_call = next(
        n for n in tool_class.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "async_call"
    )
    assert [a.arg for a in tool_call.args.args] == ["self", "hass", "tool_input", "llm_context"]
    assert "ToolResult" in ast.unparse(tool_call.returns)
    local_tree = ast.parse((ROOT / "custom_components/yuvomi_mcp/llm.py").read_text(encoding="utf-8"))
    local_callback = next(
        n for n in local_tree.body if isinstance(n, ast.FunctionDef) and n.name == "async_get_tools"
    )
    assert [a.arg for a in local_callback.args.args] == ["hass", "llm_context", "api_id"]
    assert "class ToolResult:" in sources[PATHS[1]]
    assert "error: bool = False" in sources[PATHS[1]]
    assert 'requires-python = ">=3.14.2"' in sources["pyproject.toml"]
    # ConfigEntry has type parameter defaults that Python 3.12 cannot parse.
    # Inspect the original signature without altering the upstream source.
    update = re.search(
        r"^    def async_update_reload_and_abort\((.*?)^    \) -> ConfigFlowResult:",
        sources["homeassistant/config_entries.py"],
        re.MULTILINE | re.DOTALL,
    )
    assert update is not None
    assert "unique_id:" in update.group(1) and "data:" in update.group(1)
    options_source = sources["homeassistant/components/config/config_entries.py"]
    assert "class OptionManagerFlowIndexView" in options_source
    assert "@require_admin(perm_category=CAT_CONFIG_ENTRIES, permission=POLICY_EDIT)" in options_source
    evidence["verified_contract"] = {
        "platform_callback": "def async_get_tools(hass, llm_context, api_id) -> LLMTools | None",
        "parameters": "probatio.Schema via probatio.from_openapi(inputSchema)",
        "tool_call": "async_call(hass, tool_input, llm_context) -> ToolResult",
        "tool_error": "ToolResult(data=JSON object, error=bool)",
        "discovery": "LazyIntegrationPlatforms discovers llm.py for loaded integrations",
        "minimum_python": "3.14.2",
    }
    target = ROOT / "docs" / "ha_api_evidence.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print("HA 2026.10.2 source contracts verified; evidence: docs/ha_api_evidence.json")


if __name__ == "__main__":
    main()
