"""Narrow same-origin Yuvomi 2.79 shopping transport, not a generic REST tool."""

import json
from urllib.parse import urlsplit, urlunsplit

import aiohttp

from .client import MAX_RESPONSE, ShoppingReadError


class ShoppingFailure(Exception):
    def __init__(self, code, message, *, uncertain=False):
        super().__init__(message)
        self.code = code
        self.uncertain = uncertain


def positive_id(value):
    if type(value) is not int or value < 1:
        raise ShoppingFailure("invalid_response", "Ungültige Yuvomi-ID.")
    return value


class ShoppingAPI:
    def __init__(self, client):
        self.client = client

    async def categories(self):
        try:
            return await self.client.get_shopping_category_records()
        except ShoppingReadError:
            raise ShoppingFailure(
                "shopping_read_failed", "Aktuelle Kategorien konnten nicht gelesen werden."
            ) from None

    async def lists(self):
        data = await self._request("GET", "/api/v1/shopping")
        rows = data.get("data")
        self._rows(rows)
        return [{"id": row["id"], "name": row["name"]} for row in rows]

    async def items(self, list_id):
        positive_id(list_id)
        data = await self._request("GET", f"/api/v1/shopping/{list_id}/items")
        rows = data.get("data")
        self._rows(rows)
        for row in rows:
            self._item(row, list_id)
        return rows

    @staticmethod
    def _rows(rows):
        if not isinstance(rows, list) or len(rows) > 10000:
            raise ShoppingFailure("invalid_response", "Unvollständige oder ungültige Yuvomi-Liste.")
        seen = set()
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("name"), str) or not row["name"].strip():
                raise ShoppingFailure("invalid_response", "Ungültiger Yuvomi-Name.")
            ident = positive_id(row.get("id"))
            if ident in seen:
                raise ShoppingFailure("invalid_response", "Mehrdeutige Yuvomi-IDs.")
            seen.add(ident)

    @staticmethod
    def _item(row, list_id):
        if (
            not isinstance(row, dict)
            or row.get("list_id") != list_id
            or not isinstance(row.get("name"), str)
            or not row["name"].strip()
            or not isinstance(row.get("category"), str)
            or type(row.get("is_checked")) not in {int, bool}
            or row["is_checked"] not in (0, 1)
            or not isinstance(row.get("quantity"), (str, type(None)))
            or "notes" not in row
            or not isinstance(row.get("notes"), (str, type(None)))
        ):
            raise ShoppingFailure("invalid_response", "Ungültiger Yuvomi-Einkaufsartikel.")
        positive_id(row.get("id"))

    async def create(self, list_id, body, key):
        positive_id(list_id)
        if (
            set(body) - {"name", "quantity", "category", "notes"}
            or not isinstance(key, str)
            or not key.isascii()
        ):
            raise ShoppingFailure("invalid_arguments", "Ungültige Einkaufsparameter.")
        return await self._write("POST", f"/api/v1/shopping/{list_id}/items", body, list_id, key)

    async def update(self, list_id, item_id, body):
        positive_id(list_id)
        positive_id(item_id)
        if set(body) - {"is_checked", "quantity", "category", "notes"}:
            raise ShoppingFailure("invalid_arguments", "Diese Artikeländerung ist nicht erlaubt.")
        result = await self._write("PATCH", f"/api/v1/shopping/items/{item_id}", body, list_id)
        if result["id"] != item_id:
            raise ShoppingFailure(
                "execution_unconfirmed", "Artikel-ID wurde nicht bestätigt.", uncertain=True
            )
        return result

    async def _write(self, method, path, body, list_id, key=None):
        data = await self._request(method, path, body=body, key=key)
        try:
            item = data["data"]
            self._item(item, list_id)
            if any(item.get(k) != v for k, v in body.items()):
                raise ValueError
            return item
        except (KeyError, TypeError, ValueError, ShoppingFailure):
            raise ShoppingFailure(
                "execution_unconfirmed", "Yuvomi-Schreibantwort ist nicht eindeutig.", uncertain=True
            ) from None

    async def _request(self, method, path, *, body=None, key=None):
        # Only this adapter constructs paths. Neither a schema field nor an LLM
        # can supply URLs, methods, headers or unrestricted request bodies.
        parsed = urlsplit(self.client._url)
        url = urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))
        headers = {**self.client._auth_headers(), "Accept": "application/json"}
        if key is not None:
            headers["Idempotency-Key"] = key
        writing = method != "GET"
        try:
            async with self.client._session.request(
                method,
                url,
                json=body,
                headers=headers,
                allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=8),
            ) as response:
                if response.status not in ({200, 201} if writing else {200}):
                    uncertain = writing and (
                        response.status >= 500
                        or response.status in {408, 409}
                        or 300 <= response.status < 400
                    )
                    raise ShoppingFailure(
                        "execution_unconfirmed" if uncertain else "shopping_rejected",
                        "Yuvomi hat die Anfrage nicht erfolgreich bestätigt. Berechtigungen und Zustand prüfen.",
                        uncertain=uncertain,
                    )
                content = bytearray()
                async for chunk in response.content.iter_chunked(65536):
                    content.extend(chunk)
                    if len(content) > MAX_RESPONSE:
                        raise ValueError
                if response.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    raise ValueError
                data = json.loads(content)
                if not isinstance(data, dict):
                    raise ValueError
                return self.client.redact(data)
        except ShoppingFailure:
            raise
        except (aiohttp.ClientError, OSError, TimeoutError, ValueError, UnicodeError, RecursionError):
            raise ShoppingFailure(
                "execution_unconfirmed" if writing else "shopping_read_failed",
                "Yuvomi-Antwort fehlt oder ist ungültig. Keine blinde Wiederholung.",
                uncertain=writing,
            ) from None
