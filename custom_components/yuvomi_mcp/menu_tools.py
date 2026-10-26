"""Three opt-in menu tools; no incomplete shopping synchronization exposed."""

import json
from pathlib import Path

from .client import RemoteTool

DEFINITIONS = json.loads(Path(__file__).with_name("menu_tools.json").read_text(encoding="utf-8"))


def menu_tools():
    return {
        f["name"].removeprefix("yuvomi_mcp__"): RemoteTool(
            f["name"].removeprefix("yuvomi_mcp__"), f["description"], f["parameters"]
        )
        for t in DEFINITIONS
        for f in [t["function"]]
    }
