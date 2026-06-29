"""Config flow for Chur Kultur."""

from __future__ import annotations

from typing import Any

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)
import voluptuous as vol

from .const import (
    CONF_DAYS,
    CONF_MAX_EVENTS,
    CONF_SEARCH,
    CONF_TAG_IDS,
    DEFAULT_DAYS,
    DEFAULT_MAX_EVENTS,
    DEFAULT_TAG_IDS,
    DOMAIN,
)


class ChurKulturConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle Chur Kultur config flow."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Create the integration entry."""
        if user_input is not None:
            await self.async_set_unique_id("chur_kultur")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title="Chur Kultur", data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=_schema(
                {
                    CONF_DAYS: DEFAULT_DAYS,
                    CONF_MAX_EVENTS: DEFAULT_MAX_EVENTS,
                    CONF_TAG_IDS: DEFAULT_TAG_IDS,
                    CONF_SEARCH: "",
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        """Return options flow."""
        return ChurKulturOptionsFlow(config_entry)


class ChurKulturOptionsFlow(config_entries.OptionsFlow):
    """Handle Chur Kultur options."""

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self.entry = entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Update options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        defaults = {
            CONF_DAYS: self.entry.options.get(
                CONF_DAYS, self.entry.data.get(CONF_DAYS, DEFAULT_DAYS)
            ),
            CONF_MAX_EVENTS: self.entry.options.get(
                CONF_MAX_EVENTS,
                self.entry.data.get(CONF_MAX_EVENTS, DEFAULT_MAX_EVENTS),
            ),
            CONF_TAG_IDS: self.entry.options.get(
                CONF_TAG_IDS, self.entry.data.get(CONF_TAG_IDS, DEFAULT_TAG_IDS)
            ),
            CONF_SEARCH: self.entry.options.get(
                CONF_SEARCH, self.entry.data.get(CONF_SEARCH, "")
            ),
        }
        return self.async_show_form(step_id="init", data_schema=_schema(defaults))


def _schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_DAYS, default=defaults[CONF_DAYS]): NumberSelector(
                NumberSelectorConfig(
                    min=1,
                    max=365,
                    step=1,
                    mode=NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_MAX_EVENTS, default=defaults[CONF_MAX_EVENTS]
            ): NumberSelector(
                NumberSelectorConfig(
                    min=1,
                    max=100,
                    step=1,
                    mode=NumberSelectorMode.BOX,
                )
            ),
            vol.Optional(CONF_TAG_IDS, default=defaults[CONF_TAG_IDS]): SelectSelector(
                SelectSelectorConfig(
                    options=DEFAULT_TAG_IDS,
                    multiple=True,
                    custom_value=True,
                    mode=SelectSelectorMode.LIST,
                )
            ),
            vol.Optional(CONF_SEARCH, default=defaults[CONF_SEARCH]): TextSelector(),
        }
    )
