"""Small async client for Yuvomi's stateless POST MCP transport.

No retries, redirects or background streams. Shopping writes use the narrow shopping_api adapter.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import aiohttp

from .const import PROTOCOL_VERSIONS, VERSION

MAX_RESPONSE = 2 * 1024 * 1024
MAX_TOOLS = 256
REST_TIMEOUT = 5


class MCPError(Exception):
    """An error containing only a fixed, credential-free public message."""

    code = "protocol_error"


class AuthenticationError(MCPError):
    """The token was refused."""

    code = "invalid_auth"


class ConnectionError(MCPError):
    """Network/HTTP failure; a write may already have reached the server."""

    code = "cannot_connect"


class RPCError(MCPError):
    """A JSON-RPC error without the remote message or data."""

    def __init__(self, rpc_code: int):
        super().__init__("Yuvomi hat die MCP-Anfrage abgelehnt.")
        self.rpc_code = rpc_code


class ShoppingReadError(MCPError):
    """Optional shopping REST reads failed, without affecting MCP availability."""

    code = "shopping_read_failed"


def normalize_url(value: str) -> str:
    """Accept only an explicit MCP endpoint without embedded credentials."""
    try:
        parsed = urlsplit(value.strip())
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path.rstrip("/") != "/mcp"
            or parsed.port == 0
            or any(c.isspace() for c in value)
            or "\\" in value
        ):
            raise ValueError
        return urlunsplit((parsed.scheme, parsed.netloc.lower(), "/mcp", "", ""))
    except (ValueError, AttributeError):
        raise ValueError("Eine HTTP(S)-URL mit dem Pfad /mcp ist erforderlich.") from None


@dataclass(frozen=True)
class RemoteTool:
    """Metadata, without any family data."""

    name: str
    description: str
    schema: dict[str, Any]


class MCPClient:
    """Reuse Home Assistant's managed aiohttp session."""

    def __init__(self, session: aiohttp.ClientSession, url: str, token: str):
        self._session = session
        self._url = normalize_url(url)
        if not token or any(ord(c) < 33 or ord(c) > 126 for c in token):
            raise ValueError("Ein gültiger API-Token ist erforderlich.")
        self._token = token
        self.protocol: str | None = None

    def redact(self, value: Any) -> Any:
        """Defensively remove reflected credentials from tool content."""
        if isinstance(value, str):
            return value.replace(self._token, "[REDACTED]")
        if isinstance(value, list):
            return [self.redact(item) for item in value]
        if isinstance(value, dict):
            return {self.redact(k): self.redact(v) for k, v in value.items()}
        return value

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    async def _shopping_get(self, endpoint: str, query: str | None = None) -> list:
        """GET only two fixed same-origin paths; no LLM-controlled endpoints."""
        if endpoint not in {"categories", "suggestions"}:
            raise ShoppingReadError("Dieser Yuvomi-Lesezugriff ist nicht erlaubt.")
        parsed = urlsplit(self._url)
        url = urlunsplit((parsed.scheme, parsed.netloc, f"/api/v1/shopping/{endpoint}", "", ""))
        headers = {**self._auth_headers(), "Accept": "application/json"}
        try:
            async with self._session.get(
                url,
                params={"q": query} if query is not None else None,
                headers=headers,
                allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=REST_TIMEOUT),
            ) as response:
                if response.status != 200:
                    raise ShoppingReadError(
                        "Yuvomi-Lesezugriff fehlgeschlagen. Verbindung und shopping:read-Rechte prüfen."
                    )
                body = bytearray()
                async for chunk in response.content.iter_chunked(65536):
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE:
                        raise ShoppingReadError("Die Yuvomi-Leseantwort überschreitet das Größenlimit.")
                if response.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    raise ShoppingReadError("Ungültiges Yuvomi-Leseantwortformat.")
                result = json.loads(body)
        except (aiohttp.ClientError, TimeoutError, OSError, ValueError, UnicodeError, RecursionError):
            raise ShoppingReadError("Yuvomi-Lesezugriff nicht verfügbar oder Antwort ungültig.") from None
        if not isinstance(result, dict) or not isinstance(result.get("data"), list):
            raise ShoppingReadError("Ungültige Yuvomi-Leseantwort.")
        return self.redact(result["data"])

    async def get_shopping_categories(self) -> list[dict]:
        data = await self._shopping_get("categories")
        if any(
            not isinstance(item, dict) or not isinstance(item.get("name"), str) or not item["name"].strip()
            for item in data
        ):
            raise ShoppingReadError("Ungültige Yuvomi-Kategorienantwort.")
        return [{"name": item["name"]} for item in data]

    async def get_shopping_category_records(self) -> list[dict]:
        """Internal category IDs are stable across a category rename."""
        data = await self._shopping_get("categories")
        if any(
            not isinstance(i, dict)
            or type(i.get("id")) is not int
            or i["id"] < 1
            or not isinstance(i.get("name"), str)
            or not i["name"].strip()
            for i in data
        ):
            raise ShoppingReadError("Ungültige Yuvomi-Kategorienantwort.")
        if len({i["id"] for i in data}) != len(data) or len({i["name"] for i in data}) != len(data):
            raise ShoppingReadError("Mehrdeutige Yuvomi-Kategorienantwort.")
        return [{"id": i["id"], "name": i["name"]} for i in data]

    async def get_shopping_suggestions(self, query: str) -> list[dict]:
        if not isinstance(query, str) or not query.strip() or len(query) > 256:
            raise ShoppingReadError("Ein gültiger Artikelname ist erforderlich.")
        data = await self._shopping_get("suggestions", query)
        for item in data:
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("name"), str)
                or not item["name"].strip()
                or not isinstance(item.get("category"), (str, type(None)))
                or type(item.get("quantity")) not in {str, int, float, type(None)}
                or (isinstance(item.get("quantity"), float) and not math.isfinite(item["quantity"]))
            ):
                raise ShoppingReadError("Ungültige Yuvomi-Vorschlagsantwort.")
        return [
            {"name": item["name"], "category": item.get("category"), "quantity": item.get("quantity")}
            for item in data
        ]

    async def _post(self, method: str, params: dict | None = None, *, notification: bool = False) -> dict:
        request_id = uuid4().hex
        message: dict = {"jsonrpc": "2.0", "method": method}
        if not notification:
            message["id"] = request_id
        if params is not None:
            message["params"] = params
        headers = {**self._auth_headers(), "Accept": "application/json, text/event-stream"}
        if self.protocol:
            headers["MCP-Protocol-Version"] = self.protocol
        try:
            async with self._session.post(
                self._url,
                json=message,
                headers=headers,
                allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as response:
                if response.status in {401, 403}:
                    raise AuthenticationError("Yuvomi hat den API-Token abgelehnt.")
                if not 200 <= response.status < 300 and not (notification and response.status == 400):
                    raise ConnectionError("Der Yuvomi-MCP-Endpunkt antwortet nicht erfolgreich.")
                if response.headers.get("Mcp-Session-Id"):
                    raise MCPError("Dieser Client benötigt einen zustandslosen MCP-Endpunkt.")
                body = bytearray()
                async for chunk in response.content.iter_chunked(65536):
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE:
                        raise MCPError("Die MCP-Antwort überschreitet das Größenlimit.")
                if notification and not body and 200 <= response.status < 300:
                    return {}
                content_type = response.headers.get("Content-Type", "").split(";")[0]
                if content_type == "text/event-stream":
                    text = body.decode("utf-8").replace("\r\n", "\n")
                    messages = [
                        json.loads(
                            "\n".join(
                                line[5:].lstrip(" ")
                                for line in event.splitlines()
                                if line.startswith("data:")
                            )
                        )
                        for event in text.split("\n\n")
                        if any(line.startswith("data:") for line in event.splitlines())
                    ]
                    matches = [
                        item for item in messages if isinstance(item, dict) and item.get("id") == request_id
                    ]
                    if len(matches) != 1:
                        raise MCPError("Keine eindeutige MCP-Antwort empfangen.")
                    result = matches[0]
                elif content_type == "application/json":
                    result = json.loads(body)
                else:
                    raise MCPError("Nicht unterstütztes MCP-Antwortformat.")
        except (aiohttp.ClientError, TimeoutError, OSError):
            raise ConnectionError("Yuvomi ist nicht erreichbar oder die Anfrage ist abgelaufen.") from None
        except (ValueError, UnicodeError, RecursionError):
            raise MCPError("Yuvomi hat eine ungültige MCP-Antwort gesendet.") from None
        if not isinstance(result, dict) or result.get("jsonrpc") != "2.0":
            raise MCPError("Ungültige JSON-RPC-Antwort.")
        # Some Yuvomi builds explicitly reject the optional-for-them notification.
        if notification:
            if isinstance(result.get("error"), dict) and result["error"].get("code") == -32601:
                return {}
            raise MCPError("Die MCP-Initialisierungsmitteilung wurde nicht akzeptiert.")
        if result.get("id") != request_id or ("result" in result) == ("error" in result):
            raise MCPError("Die MCP-Antwort passt nicht zur Anfrage.")
        if "error" in result:
            error = result["error"]
            if not isinstance(error, dict) or type(error.get("code")) is not int:
                raise MCPError("Ungültiger JSON-RPC-Fehler.")
            raise RPCError(error["code"])
        if not isinstance(result["result"], dict):
            raise MCPError("Ungültiges MCP-Ergebnis.")
        return result["result"]

    async def initialize(self) -> None:
        """Negotiate a supported version; fallback only for initialize rejection."""
        for version in PROTOCOL_VERSIONS:
            try:
                result = await self._post(
                    "initialize",
                    {
                        "protocolVersion": version,
                        "capabilities": {},
                        "clientInfo": {"name": "yuvomi_mcp", "version": VERSION},
                    },
                )
            except RPCError as err:
                if err.rpc_code == -32602:
                    continue
                raise
            negotiated = result.get("protocolVersion")
            if negotiated not in PROTOCOL_VERSIONS:
                raise MCPError("Yuvomi hat keine unterstützte MCP-Version ausgehandelt.")
            if not isinstance(result.get("capabilities"), dict) or "tools" not in result["capabilities"]:
                raise MCPError("Der MCP-Server bietet keine Werkzeuge an.")
            self.protocol = negotiated
            await self._post("notifications/initialized", notification=True)
            return
        raise MCPError("Keine gemeinsame MCP-Protokollversion gefunden.")

    async def list_tools(self) -> dict[str, RemoteTool]:
        """Read paginated metadata only at setup or an explicit options refresh."""
        tools: dict[str, RemoteTool] = {}
        cursor = None
        seen: set[str] = set()
        for _ in range(32):
            result = await self._post("tools/list", {"cursor": cursor} if cursor else {})
            if not isinstance(result.get("tools"), list):
                raise MCPError("Ungültige MCP-Werkzeugliste.")
            for item in result["tools"]:
                if not isinstance(item, dict):
                    raise MCPError("Ungültige MCP-Werkzeugmetadaten.")
                name, schema = item.get("name"), item.get("inputSchema")
                description = item.get("description", "")
                if (
                    not isinstance(name, str)
                    or not re.fullmatch(r"[A-Za-z0-9_-]{1,50}", name)
                    or name in tools
                    or not isinstance(schema, dict)
                    or schema.get("type") != "object"
                    or not isinstance(description, str)
                ):
                    raise MCPError("Nicht unterstützte oder doppelte MCP-Werkzeugmetadaten.")
                tools[name] = RemoteTool(name, self.redact(description[:1500]), self.redact(schema))
                if len(tools) > MAX_TOOLS:
                    raise MCPError("Zu viele MCP-Werkzeuge.")
            cursor = result.get("nextCursor")
            if cursor is None:
                return tools
            if not isinstance(cursor, str) or not cursor or cursor in seen:
                raise MCPError("Ungültige MCP-Paginierung.")
            seen.add(cursor)
        raise MCPError("Zu viele Seiten mit MCP-Werkzeugen.")

    async def call_tool(self, name: str, arguments: dict) -> dict:
        result = await self._post("tools/call", {"name": name, "arguments": arguments})
        if not isinstance(result.get("content"), list) or type(result.get("isError", False)) is not bool:
            raise MCPError("Ungültiges MCP-Werkzeugergebnis; Ausführung bitte prüfen.")
        if any(
            not isinstance(item, dict) or item.get("type") != "text" or not isinstance(item.get("text"), str)
            for item in result["content"]
        ):
            raise MCPError("Nicht unterstütztes MCP-Werkzeugergebnis; Ausführung bitte prüfen.")
        # Do not surface remote errors: they may echo credentials or request data.
        if result.get("isError"):
            return {
                "isError": True,
                "content": [
                    {
                        "type": "text",
                        "text": "Yuvomi meldet einen Werkzeugfehler. Keine erfolgreiche Ausführung bestätigt.",
                    }
                ],
            }
        return self.redact({"content": result["content"], "isError": False})
