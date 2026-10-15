"""Coordinator and historical statistics importer for IBC Chur."""

from __future__ import annotations

import hashlib
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import EnergyConverter

from .api import IBCAuthError, IBCClient, IBCConnectionError, IBCDataError, IBCMeterDay
from .const import DEFAULT_HISTORY_DAYS, DEFAULT_UPDATE_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class IBCData:
    """Current display data exposed by sensors."""

    latest_power_kw: float | None
    latest_timestamp: datetime | None
    latest_day: date | None
    latest_day_energy_kwh: float | None
    yesterday_energy_kwh: float | None
    last_7_days_energy_kwh: float | None
    month_energy_kwh: float | None
    data_age_hours: float | None
    last_imported_day: date | None
    statistic_id: str
    imported_samples: int
    tracked_energy_kwh: float | None


class IBCDataUpdateCoordinator(DataUpdateCoordinator[IBCData]):
    """Fetch IBC data and backfill Home Assistant long-term statistics."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        api: IBCClient,
        history_days: int = DEFAULT_HISTORY_DAYS,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name="IBC Chur",
            update_interval=DEFAULT_UPDATE_INTERVAL,
        )
        self.api = api
        self.history_days = max(1, min(int(history_days), 365))
        digest = hashlib.sha1(api.meteringpoint.encode("utf-8")).hexdigest()[:12]
        self.statistic_id = f"{DOMAIN}:energy_consumption_hourly_{digest}"

    async def _async_update_data(self) -> IBCData:
        today = dt_util.now().date()
        yesterday = today - timedelta(days=1)

        last_stat = await get_instance(self.hass).async_add_executor_job(
            get_last_statistics,
            self.hass,
            1,
            self.statistic_id,
            True,
            set(),
        )

        if last_stat and self.statistic_id in last_stat:
            last_row = last_stat[self.statistic_id][0]
            last_start = dt_util.utc_from_timestamp(float(last_row["start"]))
            first_day = max(
                last_start.astimezone(dt_util.DEFAULT_TIME_ZONE).date()
                - timedelta(days=1),
                today - timedelta(days=3),
            )
        else:
            first_day = today - timedelta(days=self.history_days)

        days: list[IBCMeterDay] = []
        data_errors: list[str] = []
        day = first_day
        while day <= yesterday:
            try:
                days.append(await self.api.async_get_meter_day(day))
            except IBCAuthError as err:
                raise ConfigEntryAuthFailed(
                    "IBC access token is invalid or expired"
                ) from err
            except IBCConnectionError as err:
                raise UpdateFailed(f"IBC update failed: {err}") from err
            except IBCDataError as err:
                data_errors.append(f"{day.isoformat()}: {err}")
                _LOGGER.warning("Skipping malformed IBC meter day %s: %s", day, err)
            day += timedelta(days=1)

        valid_days = [meter_day for meter_day in days if meter_day.points]
        if not valid_days and data_errors:
            raise UpdateFailed(
                "IBC returned no usable meter data; first parse error: "
                f"{data_errors[0]}"
            )

        imported_samples, tracked_energy_kwh = await self._async_insert_statistics(
            valid_days, last_stat
        )
        latest_data = valid_days[-1] if valid_days else None
        yesterday_data = next(
            (d for d in reversed(valid_days) if d.requested_day == yesterday), None
        )

        latest_power_kw = None
        latest_timestamp = None
        data_age_hours = None
        if latest_data is not None:
            latest = latest_data.points[-1]
            latest_power_kw = latest.power_kw
            latest_timestamp = latest.timestamp
            try:
                age = dt_util.now() - latest.timestamp.astimezone(dt_util.DEFAULT_TIME_ZONE)
                data_age_hours = max(0.0, age.total_seconds() / 3600)
            except (ValueError, OverflowError):
                data_age_hours = None

        last_7_days_start = yesterday - timedelta(days=6)
        last_7_days_values = [
            d.energy_kwh
            for d in valid_days
            if last_7_days_start <= d.requested_day <= yesterday
        ]
        month_values = [
            d.energy_kwh
            for d in valid_days
            if d.requested_day.year == today.year and d.requested_day.month == today.month
        ]

        return IBCData(
            latest_power_kw=latest_power_kw,
            latest_timestamp=latest_timestamp,
            latest_day=latest_data.requested_day if latest_data else None,
            latest_day_energy_kwh=round(latest_data.energy_kwh, 6) if latest_data else None,
            yesterday_energy_kwh=round(yesterday_data.energy_kwh, 6) if yesterday_data else None,
            last_7_days_energy_kwh=round(sum(last_7_days_values), 6) if last_7_days_values else None,
            month_energy_kwh=round(sum(month_values), 6) if month_values else None,
            data_age_hours=round(data_age_hours, 2) if data_age_hours is not None else None,
            last_imported_day=latest_data.requested_day if latest_data else None,
            statistic_id=self.statistic_id,
            imported_samples=imported_samples,
            tracked_energy_kwh=round(tracked_energy_kwh, 6) if tracked_energy_kwh is not None else None,
        )

    async def _async_insert_statistics(
        self, days: list[IBCMeterDay], previous: dict | None
    ) -> tuple[int, float | None]:
        """Convert 15-minute average kW values to HA hourly kWh statistics."""
        last_start = None
        running_sum = 0.0
        has_previous_sum = False
        if previous and self.statistic_id in previous:
            row = previous[self.statistic_id][0]
            last_start = dt_util.utc_from_timestamp(float(row["start"]))
            running_sum = float(row.get("sum") or 0.0)
            has_previous_sum = True

        hourly_energy: dict[datetime, float] = defaultdict(float)
        seen_intervals: set[float] = set()
        for meter_day in days:
            for point in meter_day.points:
                interval_start = point.timestamp - timedelta(minutes=15)
                start_utc = interval_start.astimezone(UTC)
                stamp = start_utc.timestamp()
                if stamp in seen_intervals:
                    continue
                seen_intervals.add(stamp)
                hour_start = start_utc.replace(minute=0, second=0, microsecond=0)
                hourly_energy[hour_start] += max(0.0, point.power_kw * 0.25)

        rows: list[StatisticData] = []
        for hour_start in sorted(hourly_energy):
            if last_start is not None and hour_start <= last_start:
                continue
            state = hourly_energy[hour_start]
            running_sum += state
            rows.append(StatisticData(start=hour_start, state=state, sum=running_sum))

        if rows:
            metadata = StatisticMetaData(
                mean_type=StatisticMeanType.NONE,
                has_sum=True,
                name="IBC Strombezug",
                source=DOMAIN,
                statistic_id=self.statistic_id,
                unit_class=EnergyConverter.UNIT_CLASS,
                unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
            )
            async_add_external_statistics(self.hass, metadata, rows)
            _LOGGER.info(
                "Imported %s IBC hourly energy statistics from quarter-hour data",
                len(rows),
            )
            return len(rows), running_sum

        return 0, running_sum if has_previous_sum else None
