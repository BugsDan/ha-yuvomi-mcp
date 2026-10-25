"""Keep the installed integration, MCP client identity and package in sync."""

import json
import tomllib
from pathlib import Path

from custom_components.yuvomi_mcp.const import VERSION


def test_release_versions_match():
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "custom_components/yuvomi_mcp/manifest.json").read_text(encoding="utf-8"))
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    assert manifest["version"] == VERSION == project["project"]["version"]


def test_no_active_product_database_or_options_remain():
    root = Path(__file__).resolve().parents[1]
    component = root / "custom_components/yuvomi_mcp"
    assert not (component / "catalog.py").exists()
    assert not (component / "catalog_ui.py").exists()
    strings = json.loads((component / "strings.json").read_text(encoding="utf-8"))
    assert set(strings["options"]["step"]["init"]["menu_options"]) == {"tools", "approve", "executions"}
