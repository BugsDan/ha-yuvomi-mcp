"""Administrative execution review; never resend uncertain writes."""

import probatio as vol
from homeassistant.helpers import selector

from .journal import JournalError
from .shopping_api import ShoppingFailure


def select(options):
    return selector.SelectSelector(selector.SelectSelectorConfig(options=options))


class JournalOptions:
    def _journal(self):
        runtime = self._runtime()
        if runtime is None or runtime.journal is None:
            raise JournalError("Ausführungsjournal ist nicht geladen.")
        return runtime.journal

    async def async_step_execution_error(self, user_input=None):
        return await self.async_step_init()

    async def async_step_executions(self, user_input=None):
        try:
            journal = self._journal()
            if user_input is not None:
                result = await self._runtime().purchasing.reconcile(user_input["execution"])
                return self.async_show_form(
                    step_id="execution_result",
                    data_schema=vol.Schema({}),
                    description_placeholders={"message": result["message"]},
                )
            records = [j for j in journal.data["journal"].values() if j["state"] in {"prepared", "unknown"}]
            if not records:
                return self.async_abort(reason="no_executions")
            return self.async_show_form(
                step_id="executions",
                data_schema=vol.Schema(
                    {
                        vol.Required("execution"): select(
                            [
                                {
                                    "value": j["id"],
                                    "label": j["name"]
                                    + " · Liste "
                                    + str(j["list_id"])
                                    + " · "
                                    + j["created_at"],
                                }
                                for j in records
                            ]
                        )
                    }
                ),
            )
        except (JournalError, ShoppingFailure) as err:
            return self.async_show_form(
                step_id="execution_error",
                data_schema=vol.Schema({}),
                description_placeholders={"message": str(err)},
            )

    async def async_step_execution_result(self, user_input=None):
        return await self.async_step_init()
