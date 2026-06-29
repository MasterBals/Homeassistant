"""Async client for Chur waste collection data."""

from __future__ import annotations

import asyncio
from datetime import date
import logging
from typing import Any

from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.core import HomeAssistant

from .const import SOURCE_URL
from .parser import Street, WasteEvent, parse_events, parse_streets

_LOGGER = logging.getLogger(__name__)


class ChurWasteApiError(Exception):
    """Raised when the source page cannot be loaded or parsed."""


class ChurWasteApi:
    """HTTP API wrapper for the official Chur waste page."""

    def __init__(self, hass: HomeAssistant, url: str = SOURCE_URL) -> None:
        self._hass = hass
        self._url = url

    async def _request(self, params: dict[str, Any] | None = None) -> str:
        session = async_get_clientsession(self._hass)
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                async with asyncio.timeout(20):
                    response = await session.get(
                        self._url,
                        params=params,
                        headers={"User-Agent": "HomeAssistant ChurAbfall/1.0"},
                    )
                    response.raise_for_status()
                    return await response.text()
            except Exception as err:  # noqa: BLE001
                last_error = err
                _LOGGER.warning(
                    "Failed loading Chur waste page on attempt %s: %s", attempt + 1, err
                )
                await asyncio.sleep(2**attempt)
        raise ChurWasteApiError("Could not load Chur waste page") from last_error

    async def async_get_streets(self) -> list[Street]:
        html = await self._request()
        streets = parse_streets(html)
        if not streets:
            raise ChurWasteApiError("No streets found on Chur waste page")
        return streets

    async def async_get_events(self, streets: list[Street]) -> list[WasteEvent]:
        events: list[WasteEvent] = []
        today = date.today()
        for street in streets:
            html = await self._request(
                {"strassenabschnitt[strassenabschnittId]": street.id}
            )
            events.extend(parse_events(html, [street], today))
        return sorted(events, key=lambda event: (event.date, event.waste_type, event.street))
