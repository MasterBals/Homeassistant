"""Async client for the IBC Chur customer portal API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any

from aiohttp import ClientError, ClientResponseError, ClientSession

from .const import DEFAULT_BASE_URL


class IBCError(Exception):
    """Base IBC API error."""


class IBCAuthError(IBCError):
    """Authentication failed."""


class IBCConnectionError(IBCError):
    """Connection to IBC failed."""


class IBCDataError(IBCError):
    """IBC returned an unexpected payload."""


@dataclass(slots=True, frozen=True)
class IBCPowerPoint:
    """One average power sample returned by IBC."""

    timestamp: datetime
    power_kw: float


@dataclass(slots=True)
class IBCMeterDay:
    """Parsed meter data for one requested day."""

    requested_day: date
    points: list[IBCPowerPoint]
    unit: str
    obis: str | None
    internal_name: str | None
    direction: str | None

    @property
    def energy_kwh(self) -> float:
        """Return energy represented by 15-minute average power values."""
        return sum(point.power_kw for point in self.points) * 0.25


class IBCClient:
    """Client for the API used by portal.ibc-chur.ch."""

    def __init__(
        self,
        session: ClientSession,
        access_token: str,
        subject_id: str,
        meteringpoint: str,
        role: int = 2,
        aggregation: int = 1,
        base_url: str = DEFAULT_BASE_URL,
    ) -> None:
        self._session = session
        self._access_token = self._normalize_token(access_token)
        self.subject_id = str(subject_id)
        self.meteringpoint = str(meteringpoint)
        self.role = int(role)
        self.aggregation = int(aggregation)
        self.base_url = base_url.rstrip("/")

    @staticmethod
    def _normalize_token(value: str) -> str:
        value = value.strip()
        if value.lower().startswith("bearer "):
            return value[7:].strip()
        return value

    def update_access_token(self, access_token: str) -> None:
        """Replace the bearer token without recreating the client."""
        self._access_token = self._normalize_token(access_token)

    async def async_get_meter_day(self, day: date) -> IBCMeterDay:
        """Fetch one local calendar day in the portal's 15-minute resolution."""
        url = f"{self.base_url}/meterdatavalues/{self.meteringpoint}"
        params = {
            "subject_id": self.subject_id,
            "role": str(self.role),
            "date_from": datetime.combine(day, time.min).isoformat(),
            "date_to": datetime.combine(day, time(23, 59, 59)).isoformat(),
            "aggregation": str(self.aggregation),
            "compareActive": "false",
        }
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Accept": "application/json, text/plain, */*",
        }

        try:
            async with self._session.get(
                url,
                params=params,
                headers=headers,
                timeout=30,
            ) as response:
                if response.status in (401, 403):
                    raise IBCAuthError(f"IBC authentication failed ({response.status})")
                response.raise_for_status()
                payload = await response.json(content_type=None)
        except IBCAuthError:
            raise
        except (ClientResponseError, ClientError, TimeoutError) as err:
            raise IBCConnectionError(str(err)) from err
        except ValueError as err:
            raise IBCDataError("IBC response was not valid JSON") from err

        return self._parse_meter_day(day, payload)

    @staticmethod
    def _parse_meter_day(day: date, payload: Any) -> IBCMeterDay:
        if not isinstance(payload, dict):
            raise IBCDataError("Expected a JSON object")
        timeseries = payload.get("timeseries")
        if not isinstance(timeseries, list) or not timeseries:
            raise IBCDataError("No timeseries returned")

        selected: dict[str, Any] | None = None
        for series in timeseries:
            if not isinstance(series, dict):
                continue
            if series.get("internal_name") == "ActiveEnergy.Extraction":
                selected = series
                break
        if selected is None:
            selected = next(
                (series for series in timeseries if isinstance(series, dict)), None
            )
        if selected is None:
            raise IBCDataError("No usable timeseries returned")

        raw_points = selected.get("data")
        if not isinstance(raw_points, list):
            raise IBCDataError("Timeseries has no data array")

        points: list[IBCPowerPoint] = []
        for raw in raw_points:
            if not isinstance(raw, dict):
                continue
            timestamp = raw.get("x")
            value = raw.get("y")
            if timestamp is None or value is None:
                continue
            try:
                parsed_timestamp = datetime.fromisoformat(str(timestamp))
                parsed_value = float(value)
            except (TypeError, ValueError):
                continue
            points.append(IBCPowerPoint(parsed_timestamp, parsed_value))

        if not points:
            raise IBCDataError("Timeseries contains no valid values")

        return IBCMeterDay(
            requested_day=day,
            points=points,
            unit=str(selected.get("unit") or "kW"),
            obis=selected.get("obis"),
            internal_name=selected.get("internal_name"),
            direction=selected.get("direction"),
        )
