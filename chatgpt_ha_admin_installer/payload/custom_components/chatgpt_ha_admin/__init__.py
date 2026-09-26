"""ChatGPT Home Assistant Admin integration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aiohue import LinkButtonNotPressed, create_app_key
from aiohue.discovery import DiscoveredHueBridge, discover_bridge, discover_nupnp
from aiohue.util import normalize_bridge_id

from homeassistant.components import persistent_notification
from homeassistant.const import CONF_API_KEY, CONF_API_VERSION, CONF_HOST
from homeassistant.core import EVENT_HOMEASSISTANT_STOP, HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import aiohttp_client, config_validation as cv, llm
from homeassistant.helpers.typing import ConfigType

from .api import ChatGPTHomeAssistantAdminAPI, jsonify
from .const import API_ID, API_NAME, DOMAIN
from .settings import load_settings

CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)
_RUNTIME_FILE = "hue_repair.json"


def _write_runtime(hass: HomeAssistant, payload: dict[str, Any]) -> None:
    path = Path(hass.config.path(".chatgpt_ha_admin", _RUNTIME_FILE))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(jsonify(payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


async def _discover_hue_bridge(
    hass: HomeAssistant,
    entry_id: str,
) -> tuple[Any, DiscoveredHueBridge]:
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None:
        raise HomeAssistantError(f"Config entry not found: {entry_id}")
    if entry.domain != "hue":
        raise HomeAssistantError(f"Config entry {entry_id} is not a Hue entry")

    websession = aiohttp_client.async_get_clientsession(
        hass,
        verify_ssl=False,
    )

    bridge = None
    configured_host = entry.data.get(CONF_HOST)
    if configured_host:
        try:
            bridge = await discover_bridge(
                str(configured_host),
                websession=websession,
            )
        except Exception:
            bridge = None

    try:
        bridges = await discover_nupnp(websession=websession)
    except Exception:
        bridges = []

    expected_id = normalize_bridge_id(entry.unique_id) if entry.unique_id else None
    if bridge is not None and expected_id is not None:
        if normalize_bridge_id(bridge.id) != expected_id:
            bridge = None

    if bridge is None and expected_id is not None:
        bridge = next(
            (
                candidate
                for candidate in bridges
                if normalize_bridge_id(candidate.id) == expected_id
            ),
            None,
        )
    if bridge is None and len(bridges) == 1:
        bridge = bridges[0]

    if bridge is None:
        visible = [
            {"id": normalize_bridge_id(candidate.id), "host": candidate.host}
            for candidate in bridges
        ]
        raise HomeAssistantError(
            f"Configured Hue bridge was not found. Visible bridges: {visible}"
        )
    return entry, bridge


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up ChatGPT Home Assistant Admin from YAML."""
    if DOMAIN in hass.data:
        return True

    api = ChatGPTHomeAssistantAdminAPI(
        hass=hass,
        id=API_ID,
        name=API_NAME,
        settings=load_settings(hass),
    )
    unregister = llm.async_register_api(hass, api)
    hass.data[DOMAIN] = {"api": api, "unregister": unregister}

    async def _flow_start(call: ServiceCall) -> None:
        domain = str(call.data["domain"])
        context: dict[str, Any] = {"source": str(call.data.get("source", "user"))}
        if call.data.get("entry_id"):
            context["entry_id"] = str(call.data["entry_id"])
        result = await hass.config_entries.flow.async_init(
            domain,
            context=context,
            data=call.data.get("data"),
        )
        _write_runtime(hass, {"operation": "flow_start", "result": result})

    async def _flow_configure(call: ServiceCall) -> None:
        result = await hass.config_entries.flow.async_configure(
            str(call.data["flow_id"]),
            user_input=call.data.get("user_input"),
        )
        _write_runtime(hass, {"operation": "flow_configure", "result": result})

    async def _flow_abort(call: ServiceCall) -> None:
        flow_id = str(call.data["flow_id"])
        result = await hass.config_entries.flow.async_abort(flow_id)
        _write_runtime(
            hass,
            {"operation": "flow_abort", "flow_id": flow_id, "result": result},
        )

    async def _hue_repair_prepare(call: ServiceCall) -> None:
        entry_id = str(call.data["entry_id"])
        try:
            entry, bridge = await _discover_hue_bridge(hass, entry_id)
            _write_runtime(
                hass,
                {
                    "operation": "hue_repair_prepare",
                    "status": "ready_for_button",
                    "entry_id": entry.entry_id,
                    "title": entry.title,
                    "unique_id": entry.unique_id,
                    "bridge_id": normalize_bridge_id(bridge.id),
                    "host": bridge.host,
                    "supports_v2": bridge.supports_v2,
                    "instruction": "Press the physical Hue Bridge link button now.",
                },
            )
        except Exception as err:
            _write_runtime(
                hass,
                {
                    "operation": "hue_repair_prepare",
                    "status": "error",
                    "entry_id": entry_id,
                    "error": f"{type(err).__name__}: {err}",
                },
            )
            raise

    async def _hue_repair_link(call: ServiceCall) -> None:
        entry_id = str(call.data["entry_id"])
        try:
            entry, bridge = await _discover_hue_bridge(hass, entry_id)
            device_name = str(hass.config.location_name or "home-assistant")[:19]
            try:
                app_key = await create_app_key(
                    bridge.host,
                    f"home-assistant#{device_name}",
                    websession=aiohttp_client.async_get_clientsession(
                        hass,
                        verify_ssl=False,
                    ),
                )
            except LinkButtonNotPressed:
                _write_runtime(
                    hass,
                    {
                        "operation": "hue_repair_link",
                        "status": "button_not_pressed",
                        "entry_id": entry_id,
                        "host": bridge.host,
                    },
                )
                return

            new_data = dict(entry.data)
            new_data[CONF_HOST] = bridge.host
            new_data[CONF_API_KEY] = app_key
            new_data[CONF_API_VERSION] = 2 if bridge.supports_v2 else 1
            hass.config_entries.async_update_entry(entry, data=new_data)
            reload_ok = await hass.config_entries.async_reload(entry.entry_id)
            _write_runtime(
                hass,
                {
                    "operation": "hue_repair_link",
                    "status": "success",
                    "entry_id": entry.entry_id,
                    "host": bridge.host,
                    "bridge_id": normalize_bridge_id(bridge.id),
                    "api_version": new_data[CONF_API_VERSION],
                    "reload_ok": reload_ok,
                },
            )
        except Exception as err:
            _write_runtime(
                hass,
                {
                    "operation": "hue_repair_link",
                    "status": "error",
                    "entry_id": entry_id,
                    "error": f"{type(err).__name__}: {err}",
                },
            )
            raise

    hass.services.async_register(DOMAIN, "flow_start", _flow_start)
    hass.services.async_register(DOMAIN, "flow_configure", _flow_configure)
    hass.services.async_register(DOMAIN, "flow_abort", _flow_abort)
    hass.services.async_register(DOMAIN, "hue_repair_prepare", _hue_repair_prepare)
    hass.services.async_register(DOMAIN, "hue_repair_link", _hue_repair_link)

    persistent_notification.async_create(
        hass,
        "ChatGPT Home Assistant Admin ist aktiv.\n\n"
        "MCP-Endpunkt: `/api/mcp/chatgpt_ha_admin`\n\n"
        "Der Endpunkt verwendet die Home-Assistant-Authentifizierung und verlangt einen Administrator:Innen-Zugang.",
        title="ChatGPT Home Assistant Admin",
        notification_id=DOMAIN,
    )

    @callback
    def _unregister(_event) -> None:
        unregister()
        for service in (
            "flow_start",
            "flow_configure",
            "flow_abort",
            "hue_repair_prepare",
            "hue_repair_link",
        ):
            hass.services.async_remove(DOMAIN, service)

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _unregister)
    return True
