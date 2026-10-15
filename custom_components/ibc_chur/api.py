"""Async client for the IBC Chur customer portal API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any

from aiohttp import ClientError, ClientResponseError, ClientSession

from .auth import IBCAuthConnectionError, IBCInvalidAuth, IBCTokenManager
from .const import DEFAULT_BASE_URL, DEFAULT_SETTINGS_URL


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
        *,
        token_manager: IBCTokenManager | None = None,
        access_token: str | None = None,
        subject_id: str | None = None,
        meteringpoint: str | None = None,
        role: int = 2,
        aggregation: int = 1,
        base_url: str = DEFAULT_BASE_URL,
        settings_url: str = DEFAULT_SETTINGS_URL,
    ) -> None:
        self._session = session
        self._token_manager = token_manager
        self._access_token = self._normalize_token(access_token or "")
        self.subject_id = str(subject_id) if subject_id is not None else None
        self.meteringpoint = str(meteringpoint) if meteringpoint is not None else None
        self.role = int(role)
        self.aggregation = int(aggregation)
        self.base_url = base_url.rstrip("/")
        self.settings_url = settings_url.rstrip("/")

    @staticmethod
    def _normalize_token(value: str) -> str:
        value = value.strip()
        if value.lower().startswith("bearer "):
            return value[7:].strip()
        return value

    async def _async_access_token(self, *, force_refresh: bool = False) -> str:
        if self._token_manager is not None:
            try:
                if force_refresh:
                    return await self._token_manager.async_force_refresh()
                return await self._token_manager.async_access_token()
            except IBCInvalidAuth as err:
                raise IBCAuthError(str(err)) from err
            except IBCAuthConnectionError as err:
                raise IBCConnectionError(str(err)) from err
        if not self._access_token:
            raise IBCAuthError("No IBC access token available")
        return self._access_token

    async def _async_request_json(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        settings: bool = False,
        allow_no_content: bool = False,
    ) -> Any:
        root = self.settings_url if settings else self.base_url
        url = f"{root}/{path.lstrip('/')}"

        for attempt in range(2):
            token = await self._async_access_token(force_refresh=attempt == 1)
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/json",
            }
            try:
                async with self._session.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=30,
                ) as response:
                    if (
                        response.status == 401
                        and self._token_manager is not None
                        and attempt == 0
                    ):
                        continue
                    if response.status in (401, 403):
                        raise IBCAuthError(
                            f"IBC authentication failed ({response.status})"
                        )
                    if response.status == 204:
                        return None
                    response.raise_for_status()
                    return await response.json(content_type=None)
            except IBCAuthError:
                raise
            except (ClientResponseError, ClientError, TimeoutError) as err:
                raise IBCConnectionError(str(err)) from err
            except ValueError as err:
                raise IBCDataError("IBC response was not valid JSON") from err

        if allow_no_content:
            return None
        raise IBCAuthError("IBC authentication failed after token refresh")

    async def async_get_subject(self, subject_id: str) -> Any:
        return await self._async_request_json(
            f"subject/{subject_id}/", params={"user_component": "false"}
        )

    async def async_try_list_subjects(self) -> Any | None:
        for path in ("subject/", "subject"):
            try:
                data = await self._async_request_json(
                    path,
                    params={"user_component": "false"},
                    allow_no_content=True,
                )
            except IBCConnectionError:
                continue
            if data is not None:
                return data
        return None

    async def async_get_subject_roles(self, subject_id: str) -> Any:
        return await self._async_request_json(f"subjectrole/{subject_id}/")

    async def async_get_objects(self, subject_id: str) -> Any:
        return await self._async_request_json(
            "objects", params={"subject_id": str(subject_id)}
        )

    async def async_get_contracts(self, object_id: str, subject_id: str, role: int) -> Any:
        return await self._async_request_json(
            f"contracts/{object_id}",
            params={"subject_id": str(subject_id), "role": str(role)},
        )

    async def async_get_invoice_categories(self) -> Any:
        return await self._async_request_json("invoicetypecategory/", settings=True)

    async def async_get_tariff_periods(self) -> Any:
        return await self._async_request_json("tariffperiod/", settings=True)

    async def async_get_meteringpoints(
        self,
        object_id: str,
        subject_id: str,
        role: int,
        invoice_category: int,
    ) -> Any:
        return await self._async_request_json(
            f"meteringpoints/{object_id}",
            params={
                "subject_id": str(subject_id),
                "role": str(role),
                "invoicetypecategory": str(invoice_category),
            },
            allow_no_content=True,
        )

    async def async_get_meteringpoints_evg(self, subject_id: str) -> Any | None:
        return await self._async_request_json(
            "meteringpoints_evg/",
            params={"subject_id": str(subject_id)},
            allow_no_content=True,
        )

    async def async_get_meter_sum(
        self,
        meteringpoint: str,
        subject_id: str,
        role: int,
        date_from: datetime,
        date_to: datetime,
    ) -> Any:
        return await self._async_request_json(
            f"meterdatasum/{meteringpoint}",
            params={
                "subject_id": str(subject_id),
                "role": str(role),
                "date_from": date_from.replace(tzinfo=None).isoformat(),
                "date_to": date_to.replace(tzinfo=None).isoformat(),
            },
            allow_no_content=True,
        )

    async def async_get_open_invoices(self, subject_id: str) -> Any:
        return await self._async_request_json(
            "open_invoices",
            params={"subject_id": str(subject_id)},
            allow_no_content=True,
        )

    async def async_get_open_messages_count(self, subject_id: str) -> Any:
        return await self._async_request_json(
            f"open_messages_count/{subject_id}/-1", allow_no_content=True
        )

    async def async_get_meter_day(self, day: date) -> IBCMeterDay:
        if self.subject_id is None or self.meteringpoint is None:
            raise IBCDataError("IBC subject or metering point is not configured")
        payload = await self._async_request_json(
            f"meterdatavalues/{self.meteringpoint}",
            params={
                "subject_id": self.subject_id,
                "role": str(self.role),
                "date_from": datetime.combine(day, time.min).isoformat(),
                "date_to": datetime.combine(day, time(23, 59, 59)).isoformat(),
                "aggregation": str(self.aggregation),
                "compareActive": "false",
            },
            allow_no_content=True,
        )
        return self._parse_meter_day(day, payload)

    @staticmethod
    def _empty_meter_day(day: date) -> IBCMeterDay:
        return IBCMeterDay(day, [], "kW", None, None, None)

    @classmethod
    def _parse_meter_day(cls, day: date, payload: Any) -> IBCMeterDay:
        if payload is None:
            return cls._empty_meter_day(day)
        if isinstance(payload, list):
            if not payload:
                return cls._empty_meter_day(day)
            if all(isinstance(item, dict) for item in payload):
                timeseries = payload
            else:
                raise IBCDataError(f"Unexpected meter payload list for {day.isoformat()}")
        elif isinstance(payload, dict):
            timeseries = payload.get("timeseries")
            if timeseries in (None, []):
                return cls._empty_meter_day(day)
            if not isinstance(timeseries, list):
                raise IBCDataError(
                    f"Unexpected timeseries type for {day.isoformat()}: {type(timeseries).__name__}"
                )
        else:
            raise IBCDataError(
                f"Unexpected meter payload type for {day.isoformat()}: {type(payload).__name__}"
            )

        selected = next(
            (
                series
                for series in timeseries
                if isinstance(series, dict)
                and series.get("internal_name") == "ActiveEnergy.Extraction"
            ),
            None,
        )
        if selected is None:
            selected = next(
                (
                    series
                    for series in timeseries
                    if isinstance(series, dict)
                    and str(series.get("direction", "")).lower() == "in"
                ),
                None,
            )
        if selected is None:
            selected = next((s for s in timeseries if isinstance(s, dict)), None)
        if selected is None:
            return cls._empty_meter_day(day)

        raw_points = selected.get("data")
        if raw_points in (None, []):
            return IBCMeterDay(
                day,
                [],
                str(selected.get("unit") or "kW"),
                str(selected.get("obis")) if selected.get("obis") else None,
                str(selected.get("internal_name")) if selected.get("internal_name") else None,
                str(selected.get("direction")) if selected.get("direction") else None,
            )
        if not isinstance(raw_points, list):
            raise IBCDataError(f"Timeseries data is not a list for {day.isoformat()}")

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
            if parsed_timestamp.tzinfo is None:
                raise IBCDataError(f"Meter timestamp has no timezone for {day.isoformat()}")
            points.append(IBCPowerPoint(parsed_timestamp, parsed_value))

        points.sort(key=lambda point: point.timestamp)
        return IBCMeterDay(
            day,
            points,
            str(selected.get("unit") or "kW"),
            str(selected.get("obis")) if selected.get("obis") else None,
            str(selected.get("internal_name")) if selected.get("internal_name") else None,
            str(selected.get("direction")) if selected.get("direction") else None,
        )
