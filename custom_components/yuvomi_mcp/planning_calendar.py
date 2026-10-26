"""Calendar reads restricted to configured entities and current actor permissions."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from homeassistant.auth.permissions.const import POLICY_READ
from homeassistant.helpers import entity_registry as er

from .shopping_api import ShoppingFailure


def calendar_reader(hass):
    async def read(config, start, end, actor):
        entities = sorted({r["entity"] for r in config["calendars"].values()})
        if not entities:
            return {}
        registry = er.async_get(hass)
        for rule in config["calendars"].values():
            if rule.get("registry_id"):
                entry = registry.async_get(rule["entity"])
                if entry is None or entry.id != rule["registry_id"]:
                    raise ShoppingFailure(
                        "calendar_not_allowed", "Kalenderreferenz geändert; Konfiguration prüfen."
                    )
        user = await hass.auth.async_get_user(actor.user_id) if actor and actor.user_id else None
        if user is None or any(not user.permissions.check_entity(e, POLICY_READ) for e in entities):
            raise ShoppingFailure(
                "calendar_not_allowed", "Kalenderzugriff erfordert nachgewiesene Entity-Leserechte."
            )
        if any(
            hass.states.get(e) is None or hass.states.get(e).state in {"unavailable", "unknown"}
            for e in entities
        ):
            raise ShoppingFailure("attendance_unclear", "Ausgewählter Kalender ist nicht verfügbar.")
        zone = ZoneInfo(config["timezone"])
        data = {
            "start_date_time": datetime.combine(start, time.min, zone).isoformat(),
            "end_date_time": datetime.combine(end + timedelta(days=1), time.min, zone).isoformat(),
        }
        try:
            response = await hass.services.async_call(
                "calendar",
                "get_events",
                data,
                target={"entity_id": entities},
                blocking=True,
                return_response=True,
                context=actor,
            )
            return {entity: response[entity]["events"] for entity in entities}
        except Exception:
            raise ShoppingFailure(
                "attendance_unclear", "Kalender konnten nicht vollständig gelesen werden."
            ) from None

    return read
