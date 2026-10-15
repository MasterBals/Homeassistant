"""Config flow for IBC Energie Wasser Chur."""

from __future__ import annotations

import base64
import json
import logging
import re
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import IBCClient, IBCConnectionError, IBCDataError
from .auth import IBCAuthConnectionError, IBCAuthUnsupported, IBCAuthenticator, IBCInvalidAuth
from .const import (
    CONF_AGGREGATION,
    CONF_HISTORY_DAYS,
    CONF_INVOICE_CATEGORY,
    CONF_METERINGPOINT,
    CONF_OBJECT_ID,
    CONF_ROLE,
    CONF_SUBJECT_ID,
    DEFAULT_AGGREGATION,
    DEFAULT_HISTORY_DAYS,
    DEFAULT_INVOICE_CATEGORY,
    DEFAULT_ROLE,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)
_METERINGPOINT_RE = re.compile(r"^CH[0-9A-Z]{12,}$", re.IGNORECASE)
_SUBJECT_KEYS = {
    "subject_id",
    "subjectid",
    "subject-id",
    "ebp_subject_id",
    "ebpsubjectid",
    "customer_subject_id",
    "customersubjectid",
}


class IBCChurConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle IBC login and account discovery."""

    VERSION = 3

    def __init__(self) -> None:
        """Initialize flow state."""
        self._auth_data: dict[str, Any] | None = None
        self._subject_id: str | None = None
        self._role: int = DEFAULT_ROLE
        self._object_id: str | None = None
        self._invoice_category: int = DEFAULT_INVOICE_CATEGORY
        self._client: IBCClient | None = None
        self._objects: dict[str, str] = {}
        self._roles: list[int] = []
        self._meteringpoints: dict[str, tuple[int, str]] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Log in to IBC and continue with automatic account discovery."""
        errors: dict[str, str] = {}
        if user_input is not None:
            username = str(user_input[CONF_USERNAME]).strip()
            password = str(user_input[CONF_PASSWORD])
            session = async_get_clientsession(self.hass)
            authenticator = IBCAuthenticator(session)
            try:
                token = await authenticator.async_login(username, password)
            except IBCInvalidAuth:
                errors["base"] = "invalid_auth"
            except IBCAuthConnectionError:
                errors["base"] = "cannot_connect"
            except IBCAuthUnsupported:
                errors["base"] = "auth_unsupported"
            except Exception:
                _LOGGER.exception("Unexpected error during IBC authentication")
                errors["base"] = "unknown"
            else:
                self._auth_data = {
                    "token": token,
                    CONF_USERNAME: username,
                }
                access_token = str(token.get("access_token", ""))
                self._client = IBCClient(session, access_token=access_token)
                return await self._async_after_login(access_token)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): TextSelector(),
                    vol.Required(CONF_PASSWORD): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                }
            ),
            errors=errors,
        )

    async def _async_after_login(self, access_token: str):
        """Discover the IBC subject after a successful token exchange."""
        assert self._client is not None
        subjects = _subjects_from_token(access_token)
        try:
            listed = await self._client.async_try_list_subjects()
        except (IBCConnectionError, IBCDataError):
            listed = None
        subjects.update(_extract_subjects(listed))

        if len(subjects) == 1:
            self._subject_id = next(iter(subjects))
            return await self._async_prepare_roles_and_objects()
        if len(subjects) > 1:
            return self.async_show_form(
                step_id="subject_select",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_SUBJECT_ID): SelectSelector(
                            SelectSelectorConfig(
                                options=[
                                    {"value": value, "label": value}
                                    for value in sorted(subjects)
                                ],
                                mode=SelectSelectorMode.DROPDOWN,
                            )
                        )
                    }
                ),
            )
        return await self.async_step_subject()

    async def async_step_subject(self, user_input: dict[str, Any] | None = None):
        """Ask for subject ID only when the API/token cannot expose it automatically."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._subject_id = str(user_input[CONF_SUBJECT_ID]).strip()
            try:
                return await self._async_prepare_roles_and_objects()
            except (IBCConnectionError, IBCDataError):
                errors["base"] = "subject_not_found"

        return self.async_show_form(
            step_id="subject",
            data_schema=vol.Schema(
                {vol.Required(CONF_SUBJECT_ID): TextSelector()}
            ),
            errors=errors,
        )

    async def async_step_subject_select(
        self, user_input: dict[str, Any] | None = None
    ):
        """Select one subject when several are available."""
        if user_input is None:
            return await self.async_step_subject()
        self._subject_id = str(user_input[CONF_SUBJECT_ID])
        return await self._async_prepare_roles_and_objects()

    async def _async_prepare_roles_and_objects(self):
        """Discover roles and supply objects."""
        assert self._client is not None
        assert self._subject_id is not None

        role_payload = await self._client.async_get_subject_roles(self._subject_id)
        self._roles = sorted(_extract_roles(role_payload)) or [DEFAULT_ROLE]
        if len(self._roles) > 1:
            return self.async_show_form(
                step_id="role",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_ROLE): SelectSelector(
                            SelectSelectorConfig(
                                options=[
                                    {"value": str(role), "label": f"Rolle {role}"}
                                    for role in self._roles
                                ],
                                mode=SelectSelectorMode.DROPDOWN,
                            )
                        )
                    }
                ),
            )
        self._role = self._roles[0]
        return await self._async_prepare_objects()

    async def async_step_role(self, user_input: dict[str, Any] | None = None):
        """Select an IBC role when several relationships exist."""
        if user_input is None:
            return await self._async_prepare_roles_and_objects()
        self._role = int(user_input[CONF_ROLE])
        return await self._async_prepare_objects()

    async def _async_prepare_objects(self):
        """Discover customer supply objects."""
        assert self._client is not None
        assert self._subject_id is not None
        payload = await self._client.async_get_objects(self._subject_id)
        self._objects = _extract_object_options(payload)
        if not self._objects:
            return self.async_abort(reason="no_objects")
        if len(self._objects) == 1:
            self._object_id = next(iter(self._objects))
            return await self._async_prepare_meteringpoints()
        return self.async_show_form(
            step_id="object",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_OBJECT_ID): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                {"value": key, "label": label}
                                for key, label in self._objects.items()
                            ],
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )

    async def async_step_object(self, user_input: dict[str, Any] | None = None):
        """Select one supply object."""
        if user_input is None:
            return await self._async_prepare_objects()
        self._object_id = str(user_input[CONF_OBJECT_ID])
        return await self._async_prepare_meteringpoints()

    async def _async_prepare_meteringpoints(self):
        """Discover metering points across all available media categories."""
        assert self._client is not None
        assert self._subject_id is not None
        assert self._object_id is not None

        try:
            categories_payload = await self._client.async_get_invoice_categories()
            categories = _extract_category_options(categories_payload)
        except (IBCConnectionError, IBCDataError):
            categories = {DEFAULT_INVOICE_CATEGORY: "Kategorie 1"}
        if not categories:
            categories = {DEFAULT_INVOICE_CATEGORY: "Kategorie 1"}

        discovered: dict[str, tuple[int, str]] = {}
        for category, category_label in categories.items():
            try:
                payload = await self._client.async_get_meteringpoints(
                    self._object_id,
                    self._subject_id,
                    self._role,
                    category,
                )
            except (IBCConnectionError, IBCDataError):
                continue
            for meteringpoint, label in _extract_meteringpoints(payload).items():
                display = label
                if category_label and category_label.lower() not in display.lower():
                    display = f"{category_label}: {display}"
                discovered[meteringpoint] = (category, display)

        self._meteringpoints = discovered
        if not discovered:
            return self.async_abort(reason="no_meteringpoints")
        if len(discovered) == 1:
            meteringpoint, (category, _) = next(iter(discovered.items()))
            self._invoice_category = category
            return await self._async_finish(meteringpoint)

        return self.async_show_form(
            step_id="meteringpoint",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_METERINGPOINT): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                {"value": key, "label": value[1]}
                                for key, value in discovered.items()
                            ],
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )

    async def async_step_meteringpoint(
        self, user_input: dict[str, Any] | None = None
    ):
        """Select a metering point."""
        if user_input is None:
            return await self._async_prepare_meteringpoints()
        meteringpoint = str(user_input[CONF_METERINGPOINT])
        self._invoice_category = self._meteringpoints[meteringpoint][0]
        return await self._async_finish(meteringpoint)

    async def _async_finish(self, meteringpoint: str):
        """Validate the selected metering point and create the config entry."""
        assert self._client is not None
        assert self._auth_data is not None
        assert self._subject_id is not None
        assert self._object_id is not None

        self._client.subject_id = self._subject_id
        self._client.meteringpoint = meteringpoint
        self._client.role = self._role
        self._client.aggregation = DEFAULT_AGGREGATION

        await self.async_set_unique_id(meteringpoint)
        self._abort_if_unique_id_configured()

        data = {
            **self._auth_data,
            CONF_SUBJECT_ID: self._subject_id,
            CONF_ROLE: self._role,
            CONF_OBJECT_ID: self._object_id,
            CONF_INVOICE_CATEGORY: self._invoice_category,
            CONF_METERINGPOINT: meteringpoint,
            CONF_AGGREGATION: DEFAULT_AGGREGATION,
            CONF_HISTORY_DAYS: DEFAULT_HISTORY_DAYS,
        }
        object_label = self._objects.get(self._object_id, "IBC Smart Meter")
        title = f"{object_label} · {meteringpoint[-8:]}"
        return self.async_create_entry(title=title, data=data)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]):
        """Start native IBC reauthentication."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ):
        """Ask for IBC credentials again when the refresh token expires."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            username = str(user_input[CONF_USERNAME]).strip()
            password = str(user_input[CONF_PASSWORD])
            authenticator = IBCAuthenticator(async_get_clientsession(self.hass))
            try:
                token = await authenticator.async_login(username, password)
            except IBCInvalidAuth:
                errors["base"] = "invalid_auth"
            except IBCAuthConnectionError:
                errors["base"] = "cannot_connect"
            except IBCAuthUnsupported:
                errors["base"] = "auth_unsupported"
            except Exception:
                _LOGGER.exception("Unexpected error during IBC reauthentication")
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={
                        "token": token,
                        CONF_USERNAME: username,
                    },
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_USERNAME,
                        default=str(entry.data.get(CONF_USERNAME, "")),
                    ): TextSelector(),
                    vol.Required(CONF_PASSWORD): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        """Return options flow."""
        return IBCChurOptionsFlow(config_entry)


class IBCChurOptionsFlow(config_entries.OptionsFlow):
    """Handle non-authentication IBC options."""

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self.entry = entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Configure historical import depth."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        defaults = {**self.entry.data, **self.entry.options}
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_HISTORY_DAYS,
                        default=defaults.get(
                            CONF_HISTORY_DAYS, DEFAULT_HISTORY_DAYS
                        ),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=1,
                            max=365,
                            step=1,
                            mode=NumberSelectorMode.BOX,
                        )
                    )
                }
            ),
        )


def _decode_jwt_payload(access_token: str) -> dict[str, Any]:
    """Decode JWT claims only for discovery hints; signature validation stays with OIDC."""
    try:
        encoded = access_token.split(".")[1]
        encoded += "=" * (-len(encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode(encoded).decode("utf-8"))
    except (IndexError, ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _subjects_from_token(access_token: str) -> set[str]:
    """Find explicit EBP subject claims when the realm provides them."""
    return _extract_subjects(_decode_jwt_payload(access_token), explicit_only=True)


def _extract_subjects(value: Any, explicit_only: bool = False) -> set[str]:
    """Recursively extract subject IDs without treating generic JWT sub as EBP subject."""
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in {key.replace("-", "_") for key in _SUBJECT_KEYS}:
                if isinstance(item, (str, int)) and str(item).strip():
                    found.add(str(item).strip())
            elif not explicit_only and normalized == "id" and isinstance(item, int):
                found.add(str(item))
            if isinstance(item, (dict, list)):
                found.update(_extract_subjects(item, explicit_only=explicit_only))
    elif isinstance(value, list):
        for item in value:
            found.update(_extract_subjects(item, explicit_only=explicit_only))
    return found


def _extract_roles(value: Any) -> set[int]:
    """Extract numeric role IDs from subjectrole responses."""
    found: set[int] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            key_lower = str(key).lower()
            if "role" in key_lower and isinstance(item, (int, str)):
                try:
                    found.add(int(item))
                except ValueError:
                    pass
            if isinstance(item, (dict, list)):
                found.update(_extract_roles(item))
    elif isinstance(value, list):
        for item in value:
            found.update(_extract_roles(item))
    return {role for role in found if 0 < role < 1000}


def _extract_object_options(value: Any) -> dict[str, str]:
    """Extract object IDs and human-readable labels from the EBP objects response."""
    result: dict[str, str] = {}

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return

        object_id = None
        for key in ("object_id", "objectId", "id", "pk"):
            if key in node and isinstance(node[key], (str, int)):
                object_id = str(node[key])
                break
        if object_id is not None:
            label = None
            for key in (
                "display_name",
                "displayName",
                "name",
                "label",
                "description",
                "address",
                "object_name",
                "objectName",
            ):
                item = node.get(key)
                if isinstance(item, str) and item.strip():
                    label = item.strip()
                    break
            result.setdefault(object_id, label or f"Objekt {object_id}")

        for item in node.values():
            if isinstance(item, (dict, list)):
                walk(item)

    walk(value)
    return result


def _extract_category_options(value: Any) -> dict[int, str]:
    """Extract invoice type category IDs and labels."""
    result: dict[int, str] = {}

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return
        raw_id = None
        for key in ("id", "value", "category_id", "invoicetypecategory"):
            if key in node and isinstance(node[key], (int, str)):
                try:
                    raw_id = int(node[key])
                except ValueError:
                    pass
                if raw_id is not None:
                    break
        if raw_id is not None and 0 < raw_id < 1000:
            label = None
            for key in ("name", "label", "description", "text", "translation"):
                item = node.get(key)
                if isinstance(item, str) and item.strip():
                    label = item.strip()
                    break
                if isinstance(item, dict):
                    for lang in ("de", "en", "fr", "it"):
                        translated = item.get(lang)
                        if isinstance(translated, str) and translated.strip():
                            label = translated.strip()
                            break
            result.setdefault(raw_id, label or f"Kategorie {raw_id}")
        for item in node.values():
            if isinstance(item, (dict, list)):
                walk(item)

    walk(value)
    return result


def _extract_meteringpoints(value: Any) -> dict[str, str]:
    """Extract Swiss metering point identifiers from arbitrary EBP JSON shapes."""
    result: dict[str, str] = {}

    def walk(node: Any, inherited_label: str | None = None) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item, inherited_label)
            return
        if isinstance(node, str):
            text = node.strip()
            if _METERINGPOINT_RE.match(text):
                result.setdefault(text, inherited_label or text)
            return
        if not isinstance(node, dict):
            return

        label = inherited_label
        for key in (
            "name",
            "label",
            "description",
            "medium",
            "product",
            "meteringpoint_name",
        ):
            item = node.get(key)
            if isinstance(item, str) and item.strip() and not _METERINGPOINT_RE.match(item.strip()):
                label = item.strip()
                break

        point = None
        for key, item in node.items():
            if not isinstance(item, str):
                continue
            candidate = item.strip()
            key_lower = str(key).lower()
            if _METERINGPOINT_RE.match(candidate) or (
                "metering" in key_lower and candidate.upper().startswith("CH")
            ):
                point = candidate
                break
        if point:
            result.setdefault(point, f"{label} ({point})" if label else point)

        for item in node.values():
            if isinstance(item, (dict, list)):
                walk(item, label)
            elif isinstance(item, str) and _METERINGPOINT_RE.match(item.strip()):
                result.setdefault(item.strip(), label or item.strip())

    walk(value)
    return result
