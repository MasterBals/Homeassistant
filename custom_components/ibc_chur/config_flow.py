"""Config flow for IBC Energie Wasser Chur."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.util import dt as dt_util
import voluptuous as vol

from .api import IBCAuthError, IBCClient, IBCConnectionError, IBCDataError
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_AGGREGATION,
    CONF_HISTORY_DAYS,
    CONF_METERINGPOINT,
    CONF_ROLE,
    CONF_SUBJECT_ID,
    DEFAULT_AGGREGATION,
    DEFAULT_HISTORY_DAYS,
    DEFAULT_ROLE,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def _validate(hass, data: dict[str, Any]) -> None:
    client = IBCClient(
        async_get_clientsession(hass),
        access_token=data[CONF_ACCESS_TOKEN],
        subject_id=str(data[CONF_SUBJECT_ID]),
        meteringpoint=data[CONF_METERINGPOINT],
        role=int(data.get(CONF_ROLE, DEFAULT_ROLE)),
        aggregation=int(data.get(CONF_AGGREGATION, DEFAULT_AGGREGATION)),
    )
    await client.async_get_meter_day(dt_util.now().date() - timedelta(days=1))


class IBCChurConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle an IBC Chur config flow."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await _validate(self.hass, user_input)
            except IBCAuthError:
                errors["base"] = "invalid_auth"
            except (IBCConnectionError, IBCDataError):
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error validating IBC configuration")
                errors["base"] = "unknown"
            else:
                meteringpoint = user_input[CONF_METERINGPOINT].strip()
                await self.async_set_unique_id(meteringpoint)
                self._abort_if_unique_id_configured()
                clean = dict(user_input)
                clean[CONF_METERINGPOINT] = meteringpoint
                clean[CONF_SUBJECT_ID] = str(clean[CONF_SUBJECT_ID]).strip()
                return self.async_create_entry(title="IBC Smart Meter", data=clean)

        return self.async_show_form(
            step_id="user",
            data_schema=_schema(user_input or {}),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]):
        self._reauth_entry = self._get_reauth_entry()
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        entry = self._reauth_entry
        if user_input is not None:
            candidate = dict(entry.data)
            candidate[CONF_ACCESS_TOKEN] = user_input[CONF_ACCESS_TOKEN]
            try:
                await _validate(self.hass, candidate)
            except IBCAuthError:
                errors["base"] = "invalid_auth"
            except (IBCConnectionError, IBCDataError):
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error reauthenticating IBC")
                errors["base"] = "unknown"
            else:
                self.hass.config_entries.async_update_entry(entry, data=candidate)
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ACCESS_TOKEN): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    )
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return IBCChurOptionsFlow(config_entry)


class IBCChurOptionsFlow(config_entries.OptionsFlow):
    """Options for IBC Chur."""

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self.entry = entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            merged = {**self.entry.data, **self.entry.options, **user_input}
            try:
                await _validate(self.hass, merged)
            except IBCAuthError:
                return self.async_show_form(
                    step_id="init",
                    data_schema=_options_schema(merged),
                    errors={"base": "invalid_auth"},
                )
            except (IBCConnectionError, IBCDataError):
                return self.async_show_form(
                    step_id="init",
                    data_schema=_options_schema(merged),
                    errors={"base": "cannot_connect"},
                )
            return self.async_create_entry(title="", data=user_input)

        defaults = {**self.entry.data, **self.entry.options}
        return self.async_show_form(step_id="init", data_schema=_options_schema(defaults))


def _schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_ACCESS_TOKEN, default=defaults.get(CONF_ACCESS_TOKEN, "")
            ): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
            vol.Required(
                CONF_SUBJECT_ID, default=defaults.get(CONF_SUBJECT_ID, "")
            ): TextSelector(),
            vol.Required(
                CONF_METERINGPOINT, default=defaults.get(CONF_METERINGPOINT, "")
            ): TextSelector(),
            vol.Required(
                CONF_ROLE, default=defaults.get(CONF_ROLE, DEFAULT_ROLE)
            ): NumberSelector(
                NumberSelectorConfig(
                    min=1, max=20, step=1, mode=NumberSelectorMode.BOX
                )
            ),
            vol.Required(
                CONF_AGGREGATION,
                default=defaults.get(CONF_AGGREGATION, DEFAULT_AGGREGATION),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=1, max=20, step=1, mode=NumberSelectorMode.BOX
                )
            ),
            vol.Required(
                CONF_HISTORY_DAYS,
                default=defaults.get(CONF_HISTORY_DAYS, DEFAULT_HISTORY_DAYS),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=1, max=365, step=1, mode=NumberSelectorMode.BOX
                )
            ),
        }
    )


def _options_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_ACCESS_TOKEN, default=defaults.get(CONF_ACCESS_TOKEN, "")
            ): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
            vol.Required(
                CONF_HISTORY_DAYS,
                default=defaults.get(CONF_HISTORY_DAYS, DEFAULT_HISTORY_DAYS),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=1, max=365, step=1, mode=NumberSelectorMode.BOX
                )
            ),
        }
    )
