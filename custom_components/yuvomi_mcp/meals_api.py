"""Bounded fixed-path meal access, never generic REST writes."""

from datetime import date, timedelta

from .shopping_api import ShoppingAPI, ShoppingFailure, positive_id


def slot(row):
    return row["date"], row["meal_type"]


def snapshot(row):
    return {
        k: row.get(k)
        for k in ("date", "meal_type", "title", "notes", "recipe_id", "recipe_url", "cook_user_id")
    } | {
        "ingredients": [
            {k: i.get(k) for k in ("name", "quantity", "category")} for i in row.get("ingredients", [])
        ]
    }


class MealAPI(ShoppingAPI):
    @staticmethod
    def validate(row):
        try:
            positive_id(row["id"])
            if date.fromisoformat(row["date"]).isoformat() != row["date"]:
                raise ValueError
            if (
                row["meal_type"] not in {"breakfast", "lunch", "dinner", "snack"}
                or not isinstance(row["title"], str)
                or not row["title"].strip()
                or not isinstance(row.get("notes"), (str, type(None)))
                or not isinstance(row.get("ingredients"), list)
            ):
                raise ValueError
            for i in row["ingredients"]:
                if (
                    not isinstance(i.get("name"), str)
                    or not isinstance(i.get("quantity"), (str, type(None)))
                    or not isinstance(i.get("category"), str)
                ):
                    raise ValueError
            return row
        except (KeyError, ValueError, TypeError):
            raise ShoppingFailure("invalid_response", "Mahlzeitantwort unvollständig.") from None

    async def meals(self, start, end):
        start, end = date.fromisoformat(str(start)), date.fromisoformat(str(end))
        if not 0 <= (end - start).days <= 95:
            raise ShoppingFailure("invalid_arguments", "Planungsbereich zu groß.")
        cursor, rows = start, {}
        while cursor <= end:
            data = await self._request("GET", f"/api/v1/meals?week={cursor.isoformat()}")
            try:
                first, last = date.fromisoformat(data["weekStart"]), date.fromisoformat(data["weekEnd"])
                if (
                    not first <= cursor <= last
                    or (last - first).days != 6
                    or not isinstance(data["data"], list)
                ):
                    raise ValueError
                for row in data["data"]:
                    self.validate(row)
                    if not first <= date.fromisoformat(row["date"]) <= last:
                        raise ValueError
                    if row["id"] in rows and rows[row["id"]] != row:
                        raise ValueError
                    rows[row["id"]] = row
                cursor = last + timedelta(days=1)
            except (KeyError, TypeError, ValueError):
                raise ShoppingFailure("invalid_response", "Yuvomi-Wochenbestand unvollständig.") from None
        return [r for r in rows.values() if start.isoformat() <= r["date"] <= end.isoformat()]

    async def apply(self, assignments, key, *, replace=False):
        body = {"assignments": assignments, "replace_existing" if replace else "skip_occupied": True}
        return await self._request("POST", "/api/v1/meals/apply-plan", body=body, key=key)
