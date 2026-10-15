"""Coordinator and historical statistics importer for IBC Chur."""

from __future__ import annotations

import hashlib
import logging
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
    yesterday_energy_kwh: float | None
    last_imported_day: date | None
    statistic_id: str
    imported_samples: int


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
        self.statistic_id = f"{DOMAIN}:energy_consumption_{digest}"

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
        day = first_day
        try:
            while day <= yesterday:
                days.append(await self.api.async_get_meter_day(day))
                day += timedelta(days=1)
        except IBCAuthError as err:
            raise ConfigEntryAuthFailed(
                "IBC access token is invalid or expired"
            ) from err
        except (IBCConnectionError, IBCDataError) as err:
            raise UpdateFailed(f"IBC update failed: {err}") from err

        imported_samples = await self._async_insert_statistics(days, last_stat)
        yesterday_data = next(
            (
                meter_day
                for meter_day in reversed(days)
                if meter_day.requested_day == yesterday
            ),
            None,
        )

        if yesterday_data is None:
            return IBCData(
                latest_power_kw=None,
                latest_timestamp=None,
                yesterday_energy_kwh=None,
                last_imported_day=None,
                statistic_id=self.statistic_id,
                imported_samples=imported_samples,
            )

        latest = yesterday_data.points[-1]
        return IBCData(
            latest_power_kw=latest.power_kw,
            latest_timestamp=latest.timestamp,
            yesterday_energy_kwh=round(yesterday_data.energy_kwh, 6),
            last_imported_day=yesterday,
            statistic_id=self.statistic_id,
            imported_samples=imported_samples,
        )

    async def _async_insert_statistics(
        self,
        days: list[IBCMeterDay],
        previous: dict | None,
    ) -> int:
        """Convert average kW values to 15-minute kWh statistics."""
        last_start: datetime | None = None
        running_sum = 0.0
        if previous and self.statistic_id in previous:
            row = previous[self.statistic_id][0]
            last_start = dt_util.utc_from_timestamp(float(row["start"]))
            running_sum = float(row.get("sum") or 0.0)

        rows: list[StatisticData] = []
        seen: set[float] = set()
        for meter_day in days:
            for point in meter_day.points:
                # IBC labels each 15-minute mean at the end of its interval.
                interval_start = point.timestamp - timedelta(minutes=15)
                start_utc = interval_start.astimezone(UTC)
                stamp = start_utc.timestamp()
                if stamp in seen:
                    continue
                seen.add(stamp)
                if last_start is not None and start_utc <= last_start:
                    continue
                energy_kwh = max(0.0, point.power_kw * 0.25)
                running_sum += energy_kwh
                rows.append(
                    StatisticData(
                        start=start_utc,
                        state=energy_kwh,
                        sum=running_sum,
                    )
                )

        if not rows:
            return 0

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
        _LOGGER.info("Imported %s IBC quarter-hour statistics", len(rows))
        return len(rows)
