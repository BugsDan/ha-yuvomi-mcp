"""Explicit, read-only live acceptance test. Token is entered hidden, never saved."""

import argparse
import asyncio
import getpass
import sys
from pathlib import Path
from types import ModuleType

import aiohttp

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
package = ModuleType("custom_components.yuvomi_mcp")
package.__path__ = [str(ROOT / "custom_components" / "yuvomi_mcp")]
sys.modules.setdefault(package.__name__, package)

from custom_components.yuvomi_mcp.client import MCPClient, MCPError  # noqa: E402
from custom_components.yuvomi_mcp.runtime import Runtime  # noqa: E402


async def run(url, tool):
    token = getpass.getpass("Yuvomi-Token (wird nicht gespeichert): ")
    async with aiohttp.ClientSession() as session:
        try:
            client = MCPClient(session, url, token)
            await client.initialize()
            tools = await client.list_tools()
            runtime = Runtime(client, tools, lambda: {tool} if tool else set())
            print("Protokoll:", client.protocol)
            print("Erkannte Werkzeuge:", ", ".join(sorted(tools)))
            if tool:
                result = await runtime.call(tool, {}, call_id="readonly-smoke", scope="", owner="local-test")
                print("Leseprüfung:", "FEHLER" if result["isError"] else "OK")
                # Do not print family data or remote error contents.
                if result["isError"]:
                    print("Details: Pflichtparameter im Input-Schema oder Serververbindung prüfen.")
                    return 1
            await runtime.close()
        except (MCPError, ValueError):
            print("Verbindungs-/Authentifizierungs-/Schemaprüfung fehlgeschlagen; keine Daten ausgegeben.")
            return 1
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True, help="Explicit Yuvomi MCP URL; no automatic live endpoint")
    parser.add_argument("--read", choices=["list_shopping_items", "list_tasks", "list_upcoming_events"])
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args.url, args.read)))
