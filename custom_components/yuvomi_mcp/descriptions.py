"""Conservative description overlays; schemas and authorization are never broadened."""

import json
from copy import deepcopy
from pathlib import Path

import probatio

from .client import RemoteTool

OVERLAYS = json.loads(Path(__file__).with_name("tool_descriptions.json").read_text(encoding="utf-8"))


def contract(value):
    if isinstance(value, dict):
        return {k: contract(v) for k, v in value.items() if not (k == "description" and isinstance(v, str))}
    if isinstance(value, list):
        return [contract(v) for v in value]
    return value


def optimize(tool):
    overlay = OVERLAYS.get(tool.name)
    if overlay is None:
        return tool
    try:
        exported = probatio.to_openapi(probatio.from_openapi(tool.schema), openapi_version="3.1.0")
        if contract(exported) != contract(overlay["schema"]):
            return tool
    except (ValueError, TypeError, KeyError, NotImplementedError):
        return tool
    schema = deepcopy(tool.schema)

    def visit(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "description" and isinstance(item, str):
                    value[key] = overlay["fields"].get(item, item)
                else:
                    visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(schema)
    return RemoteTool(tool.name, overlay["description"], schema)
