"""Schema validation, authorization, one-use approval and bounded deduplication."""

from __future__ import annotations

import asyncio
import json
import re
from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from time import monotonic
from typing import Any, Callable
from uuid import uuid4

import probatio
from jsonschema import FormatChecker, validators
from jsonschema.exceptions import SchemaError, ValidationError

from .client import AuthenticationError, MCPClient, MCPError, RemoteTool
from .const import KNOWN_TOOLS, READ_TOOLS
from .shopping import CATEGORIES, SHOPPING_READS, shopping_tools

TTL = 120.0
MAX_CACHE = 128
FORMAT_CHECKER = FormatChecker()


@FORMAT_CHECKER.checks("date-time", raises=(ValueError, TypeError))
def _date_time(value):
    """Always validate RFC3339 timestamps, even without jsonschema extras."""
    if not isinstance(value, str):
        return True  # the schema's type check owns non-strings
    if not re.fullmatch(r"\d{4}-\d\d-\d\d[Tt]\d\d:\d\d:\d\d(?:\.\d+)?(?:[Zz]|[+-]\d\d:\d\d)", value):
        return False
    return datetime.fromisoformat(value.upper()).tzinfo is not None


def failure(message: str, code: str) -> dict:
    return {"isError": True, "code": code, "content": [{"type": "text", "text": message}]}


def _local_references_only(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"$ref", "$dynamicRef", "$recursiveRef"} and (
                not isinstance(item, str) or not item.startswith("#")
            ):
                raise MCPError("Externe Schema-Referenzen sind nicht erlaubt.")
            if key == "$id":
                raise MCPError("Schema-IDs mit eigener Referenzbasis werden nicht unterstützt.")
            _local_references_only(item)
    elif isinstance(value, list):
        for item in value:
            _local_references_only(item)


@dataclass
class Approval:
    request_id: str
    key: str
    name: str
    arguments: dict
    expires: float
    approved: bool = False


class Runtime:
    """Generic approvals/deduplication are memory-only; shopping owns a durable journal."""

    def __init__(
        self,
        client: MCPClient,
        tools: dict[str, RemoteTool],
        enabled: Callable[[], set[str]],
        clock=monotonic,
        purchasing=None,
    ):
        self.client = client
        self.purchasing = purchasing
        self.journal = purchasing.journal if purchasing else None
        # Local REST reads take precedence over an optional same-named remote
        # tool, avoiding duplicate LLM names and any need for a patched server.
        self.tools = {**tools, **shopping_tools(include_single=purchasing is not None)}
        self._enabled = enabled
        self.clock = clock
        self.active = True
        self.parameters: dict[str, probatio.Schema] = {}
        self.validators: dict[str, Any] = {}
        self._cache: OrderedDict[str, tuple[float, dict]] = OrderedDict()
        self._locks: dict[str, tuple[asyncio.Lock, int]] = {}
        self._approvals: OrderedDict[str, Approval] = OrderedDict()
        self._cleanup_handle: asyncio.TimerHandle | None = None
        for name, tool in self.tools.items():
            try:
                _local_references_only(tool.schema)
                validator_cls = validators.validator_for(tool.schema)
                validator_cls.check_schema(tool.schema)
                self.validators[name] = validator_cls(tool.schema, format_checker=FORMAT_CHECKER)
                self.parameters[name] = probatio.from_openapi(tool.schema)
            except MCPError:
                raise
            except (SchemaError, ValueError, TypeError, KeyError, NotImplementedError, RecursionError):
                raise MCPError("Mindestens ein MCP-Input-Schema wird nicht unterstützt.") from None

    def enabled(self) -> set[str]:
        return self._enabled() & self.tools.keys() if self.active else set()

    def _prune(self):
        now = self.clock()
        for key in list(self._cache):
            if self._cache[key][0] <= now:
                del self._cache[key]
        for key in list(self._approvals):
            if self._approvals[key].expires <= now:
                del self._approvals[key]

    def _schedule_cleanup(self):
        if self._cleanup_handle is not None or not self.active:
            return
        expirations = [expiry for expiry, _ in self._cache.values()]
        expirations.extend(item.expires for item in self._approvals.values())
        if expirations:
            self._cleanup_handle = asyncio.get_running_loop().call_later(
                max(0.01, min(expirations) - self.clock()), self._cleanup
            )

    def _cleanup(self):
        self._cleanup_handle = None
        self._prune()
        self._schedule_cleanup()

    def pending(self) -> list[Approval]:
        self._prune()
        return [item for item in self._approvals.values() if not item.approved]

    def approve(self, request_id: str) -> bool:
        """Called only from the authenticated HA options UI, never from an LLM."""
        self._prune()
        for approval in self._approvals.values():
            if approval.request_id == request_id and approval.name in self.enabled():
                approval.approved = True
                return True
        return False

    async def close(self):
        self.active = False
        if self.purchasing:
            await self.purchasing.close()
        self._cache.clear()
        self._approvals.clear()
        if self._cleanup_handle is not None:
            self._cleanup_handle.cancel()
            self._cleanup_handle = None

    async def call(self, name: str, arguments: dict, *, call_id: str, scope: str, owner: str) -> dict:
        """Recheck authorization even for tools held by an older API instance."""
        if name not in self.enabled():
            return failure("Dieses Yuvomi-Werkzeug ist nicht freigegeben.", "not_allowed")
        if not isinstance(arguments, dict):
            return failure("Die Werkzeugparameter müssen ein Objekt sein.", "invalid_arguments")
        try:
            serialized = json.dumps(arguments, sort_keys=True, separators=(",", ":"), allow_nan=False)
            if len(serialized) > 65536:
                return failure("Die Werkzeugparameter sind zu umfangreich.", "invalid_arguments")
            self.validators[name].validate(arguments)
        except (ValidationError, ValueError, TypeError, RecursionError):
            return failure(
                "Die Parameter entsprechen nicht dem Yuvomi-Schema. Fehlende oder unklare Angaben bitte erfragen.",
                "invalid_arguments",
            )
        except Exception:
            # Reference-resolution errors must also never expose remote schemas/data.
            return failure("Das Yuvomi-Schema kann nicht sicher validiert werden.", "invalid_schema")
        fingerprint = sha256(f"{owner}\0{name}\0{serialized}".encode()).hexdigest()
        # HA context identifies the request/turn; absent context falls back to call ID.
        key = sha256(f"{scope or call_id}\0{fingerprint}".encode()).hexdigest()
        self._prune()
        if len(self._locks) >= MAX_CACHE and key not in self._locks:
            return failure("Zu viele gleichzeitige Yuvomi-Anfragen.", "busy")
        lock, users = self._locks.get(key, (asyncio.Lock(), 0))
        self._locks[key] = (lock, users + 1)
        try:
            async with lock:
                if name not in self.enabled():
                    return failure("Dieses Yuvomi-Werkzeug ist nicht mehr freigegeben.", "not_allowed")
                self._prune()
                if name not in READ_TOOLS and key in self._cache:
                    return deepcopy(self._cache[key][1])
                if name not in KNOWN_TOOLS:
                    # All unknown tools, including generic API access, require
                    # explicit approval of the exact arguments in HA's options UI.
                    approval = self._approvals.get(fingerprint)
                    if not approval:
                        if len(self._approvals) >= MAX_CACHE:
                            return failure("Zu viele ausstehende Bestätigungen.", "busy")
                        approval = Approval(
                            uuid4().hex, fingerprint, name, deepcopy(arguments), self.clock() + TTL
                        )
                        self._approvals[fingerprint] = approval
                        self._schedule_cleanup()
                    if not approval.approved:
                        return failure(
                            "Vor dieser Aktion ist eine ausdrückliche Bestätigung nötig. "
                            "In Home Assistant: Yuvomi MCP → Konfigurieren → Aktion bestätigen. "
                            "Danach dieselbe Aktion innerhalb von zwei Minuten erneut anfordern.",
                            "confirmation_required",
                        )
                    del self._approvals[fingerprint]  # consume before I/O
                try:
                    if self.purchasing is not None and name in {"add_shopping_item", "add_shopping_items"}:
                        result = await self.purchasing.run(
                            arguments,
                            key,
                            lambda: name in self.enabled(),
                            bulk=name == "add_shopping_items",
                            owner=owner,
                        )
                    elif name in {"add_shopping_item", "add_shopping_items"}:
                        return failure("Ausführungsjournal ist nicht geladen.", "storage_unavailable")
                    elif name in SHOPPING_READS:
                        data = (
                            await self.client.get_shopping_categories()
                            if name == CATEGORIES
                            else await self.client.get_shopping_suggestions(arguments["q"])
                        )
                        if name not in self.enabled():
                            return failure(
                                "Dieses Yuvomi-Werkzeug ist nicht mehr freigegeben.", "not_allowed"
                            )
                        result = {
                            "isError": False,
                            "content": [
                                {
                                    "type": "text",
                                    "text": json.dumps(data, ensure_ascii=False, allow_nan=False),
                                }
                            ],
                        }
                    else:
                        forwarded = deepcopy(arguments)
                        if name not in self.enabled():
                            return failure(
                                "Dieses Yuvomi-Werkzeug ist nicht mehr freigegeben.", "not_allowed"
                            )
                        result = await self.client.call_tool(name, forwarded)
                except AuthenticationError:
                    result = failure(
                        "Yuvomi hat den API-Token abgelehnt. Token und Berechtigungen in den "
                        "Integrations-Einstellungen prüfen. Keine erfolgreiche Ausführung bestätigt.",
                        "invalid_auth",
                    )
                except MCPError:
                    result = (
                        failure(
                            "Yuvomi-Lesezugriff fehlgeschlagen. Verbindung und shopping:read-Rechte prüfen.",
                            "shopping_read_failed",
                        )
                        if name in SHOPPING_READS
                        else failure(
                            "Yuvomi hat die Ausführung nicht bestätigt. Bei Schreibaktionen kann "
                            "der Ausgang unbekannt sein: Daten prüfen, nicht blind wiederholen.",
                            "execution_unconfirmed",
                        )
                    )
                except asyncio.CancelledError:
                    self._remember(
                        key,
                        failure("Anfrage abgebrochen; Ausführung in Yuvomi prüfen.", "execution_unconfirmed"),
                    )
                    raise
                if name not in READ_TOOLS:
                    self._remember(key, result)
                return deepcopy(result)
        finally:
            _, users = self._locks[key]
            if users == 1:
                del self._locks[key]
            else:
                self._locks[key] = (lock, users - 1)

    def _remember(self, key: str, result: dict):
        if not self.active:
            return
        self._cache[key] = (self.clock() + TTL, deepcopy(result))
        while len(self._cache) > MAX_CACHE:
            self._cache.popitem(last=False)
        self._schedule_cleanup()
