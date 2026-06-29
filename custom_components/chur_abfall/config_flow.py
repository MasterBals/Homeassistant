"""Config flow for Chur Abfall."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import ChurWasteApi, ChurWasteApiError
from .const import CONF_STREETS, CONF_WASTE_TYPES, DEFAULT_WASTE_TYPES, DOMAIN


class ChurAbfallConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._streets: list[dict[str, str]] = []

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if not self._streets:
            try:
                self._streets = [
                    asdict(street)
                    for street in await ChurWasteApi(self.hass).async_get_streets()
                ]
            except ChurWasteApiError:
                errors["base"] = "cannot_connect"
        if user_input:
            selected_ids = set(user_input[CONF_STREETS])
            streets = [
                street for street in self._streets if street["id"] in selected_ids
            ]
            await self.async_set_unique_id("chur_abfall")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title="Chur Abfall",
                data={
                    CONF_STREETS: streets,
                    CONF_WASTE_TYPES: user_input.get(
                        CONF_WASTE_TYPES, DEFAULT_WASTE_TYPES
                    ),
                },
            )
        schema = vol.Schema(
            {
                vol.Required(CONF_STREETS): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {"value": s["id"], "label": s["name"]}
                            for s in self._streets
                        ],
                        multiple=True,
                        mode=SelectSelectorMode.DROPDOWN,
                        custom_value=False,
                    )
                ),
                vol.Optional(
                    CONF_WASTE_TYPES, default=DEFAULT_WASTE_TYPES
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=DEFAULT_WASTE_TYPES,
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                        custom_value=True,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return ChurAbfallOptionsFlow(config_entry)


class ChurAbfallOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self.entry = entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_WASTE_TYPES,
                        default=self.entry.options.get(
                            CONF_WASTE_TYPES,
                            self.entry.data.get(CONF_WASTE_TYPES, DEFAULT_WASTE_TYPES),
                        ),
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=DEFAULT_WASTE_TYPES,
                            multiple=True,
                            mode=SelectSelectorMode.LIST,
                            custom_value=True,
                        )
                    )
                }
            ),
        )
