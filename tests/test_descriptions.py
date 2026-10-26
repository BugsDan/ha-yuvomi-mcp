"""Complete schema-compatible overlays, never remote schema guessing."""

import json
from copy import deepcopy
from pathlib import Path

import probatio

from custom_components.yuvomi_mcp.client import RemoteTool
from custom_components.yuvomi_mcp.descriptions import contract, optimize


def test_complete_snapshots_and_unknown_contract():
    base = Path(__file__).resolve().parents[1] / "docs"
    before = json.loads((base / "TOOL_DEFINITIONS_CURRENT_1.4.3.json").read_text(encoding="utf-8"))
    after = json.loads((base / "TOOL_DEFINITIONS_DRAFT_1.4.4.json").read_text(encoding="utf-8"))
    for old, new in zip(before, after, strict=True):
        a, b = old["function"], new["function"]
        tool = RemoteTool(a["name"].removeprefix("yuvomi_mcp__"), a["description"], a["parameters"])
        changed = optimize(tool)
        assert changed.description == b["description"]
        assert contract(changed.schema) == contract(tool.schema)
        assert (
            probatio.to_openapi(probatio.from_openapi(changed.schema), openapi_version="3.1.0")
            == b["parameters"]
        )
        altered = deepcopy(tool.schema)
        altered["properties"]["future"] = {"type": "boolean"}
        future = RemoteTool(tool.name, tool.description, altered)
        assert optimize(future) is future
    unknown = RemoteTool("unknown", "Keep", {"type": "object"})
    assert optimize(unknown) is unknown
