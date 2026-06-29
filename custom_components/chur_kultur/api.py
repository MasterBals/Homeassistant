"""Async client for Chur Kultur agenda data."""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import AGENDA_PATH, SOURCE_URL
from .parser import CultureEvent, parse_agenda_fragment, parse_detail_page

_LOGGER = logging.getLogger(__name__)


class ChurKulturApiError(Exception):
    """Raised when agenda data cannot be loaded."""


class ChurKulturApi:
    """HTTP API wrapper for Chur Kultur."""

    def __init__(self, hass: HomeAssistant, base_url: str = SOURCE_URL) -> None:
        self._hass = hass
        self._base_url = base_url.rstrip("/")

    async def _request(self, path: str, params: dict[str, Any] | None = None) -> str:
        session = async_get_clientsession(self._hass)
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                async with asyncio.timeout(25):
                    response = await session.get(
                        f"{self._base_url}{path}",
                        params=params,
                        headers={
                            "Accept": "text/html,*/*",
                            "User-Agent": "HomeAssistant ChurKultur/1.0",
                            "X-Requested-With": "XMLHttpRequest",
                        },
                    )
                    response.raise_for_status()
                    return await response.text()
            except Exception as err:  # noqa: BLE001
                last_error = err
                _LOGGER.warning(
                    "Failed loading Chur Kultur data on attempt %s: %s",
                    attempt + 1,
                    err,
                )
                await asyncio.sleep(2**attempt)
        raise ChurKulturApiError("Could not load Chur Kultur agenda") from last_error

    async def async_get_events(
        self,
        days: int,
        tag_ids: list[str],
        max_events: int,
        search: str = "",
    ) -> list[CultureEvent]:
        """Fetch filtered events and enrich them with detail pages."""
        today = date.today()
        params: dict[str, str | int] = {
            "yc": "dnk",
            "from": today.strftime("%d.%m.%Y"),
            "to": (today + timedelta(days=days)).strftime("%d.%m.%Y"),
            "resultsPerPage": max_events,
        }
        if tag_ids:
            params["tagIds"] = ",".join(tag_ids)
        if search:
            params["search"] = search

        html = await self._request(AGENDA_PATH, params)
        events = parse_agenda_fragment(html)[:max_events]
        if not events:
            return []

        semaphore = asyncio.Semaphore(4)

        async def enrich(event: CultureEvent) -> CultureEvent:
            async with semaphore:
                try:
                    detail_html = await self._request(
                        event.url.removeprefix(self._base_url)
                    )
                except ChurKulturApiError:
                    return event
            details = parse_detail_page(detail_html)
            event.summary = details.get("summary", event.summary)
            event.description = details.get("description", event.description)
            event.location = details.get("location", event.location)
            event.image = details.get("image", event.image)
            return event

        return sorted(
            await asyncio.gather(*(enrich(event) for event in events)),
            key=lambda event: (event.date, event.title),
        )
