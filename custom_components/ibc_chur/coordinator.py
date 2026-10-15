"""Coordinator, historical statistics and consumption analytics for IBC Chur."""

from __future__ import annotations

import hashlib
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from calendar import monthrange
from typing import Any

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
from .const import (
    CONF_OBJECT_ID,
    CONF_ROLE,
    CONF_SUBJECT_ID,
    DEFAULT_HISTORY_DAYS,
    DEFAULT_ROLE,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)
from .tariff import IBCTariffProfile, detect_2026_tariff

_LOGGER = logging.getLogger(__name__)
_MIN_COMPLETE_POINTS = 90
_ANALYSIS_MIN_DAYS = 30


@dataclass(slots=True)
class IBCData:
    """Current display and analysis data exposed by sensors."""

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
    cost_statistic_id: str
    imported_samples: int
    imported_cost_samples: int
    tracked_energy_kwh: float | None
    tracked_cost_chf: float | None
    days_analyzed: int
    avg_day_7d_kwh: float | None
    avg_day_30d_kwh: float | None
    trend_7d_pct: float | None
    estimated_annual_kwh: float | None
    base_load_kw: float | None
    base_load_cost_year_chf: float | None
    night_share_pct: float | None
    peak_15m_kw: float | None
    peak_15m_timestamp: datetime | None
    peak_hour_kwh: float | None
    peak_hour_timestamp: datetime | None
    typical_peak_hour: int | None
    projected_month_energy_kwh: float | None
    latest_day_cost_chf: float | None
    month_cost_chf: float | None
    projected_month_cost_chf: float | None
    variable_price_chf_kwh: float | None
    fixed_month_chf: float | None
    tariff_product: str | None
    tariff_group: str | None
    tariff_meter_type: str | None
    tariff_source: str | None
    cost_breakdown_month: dict[str, float]
    top_load_events: list[dict[str, Any]]


class IBCDataUpdateCoordinator(DataUpdateCoordinator[IBCData]):
    """Fetch IBC data, import statistics and derive optimization analytics."""

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
        # v2 intentionally separates the corrected complete-day/hourly model
        # from early development statistics that may contain partial days.
        self.statistic_id = f"{DOMAIN}:energy_consumption_v2_{digest}"
        self.cost_statistic_id = f"{DOMAIN}:energy_cost_v2_{digest}"
        self._day_cache: dict[date, IBCMeterDay] = {}
        self._contract_payload: Any = None
        self._contract_checked = False
        self._tariff: IBCTariffProfile | None = None

    @staticmethod
    def _is_complete_day(meter_day: IBCMeterDay) -> bool:
        """Treat normal and DST days as complete while rejecting partial publishes."""
        return len(meter_day.points) >= _MIN_COMPLETE_POINTS

    async def _async_update_data(self) -> IBCData:
        today = dt_util.now().date()
        yesterday = today - timedelta(days=1)
        analysis_days = max(self.history_days, _ANALYSIS_MIN_DAYS)
        cache_start = today - timedelta(days=analysis_days)

        # On first load fetch the analysis window once. During normal operation
        # refresh only the last three days; the in-memory cache keeps the older
        # daily curves without hammering the IBC portal every hour.
        fetch_start = cache_start if not self._day_cache else max(cache_start, today - timedelta(days=3))

        day = fetch_start
        while day <= yesterday:
            try:
                meter_day = await self.api.async_get_meter_day(day)
            except IBCAuthError as err:
                raise ConfigEntryAuthFailed(
                    "IBC access token is invalid or expired"
                ) from err
            except IBCConnectionError as err:
                raise UpdateFailed(f"IBC update failed: {err}") from err
            except IBCDataError as err:
                _LOGGER.warning("Skipping malformed IBC meter day %s: %s", day, err)
                day += timedelta(days=1)
                continue

            # Never replace a previously complete day with a temporary empty or
            # partial portal response. Partial recent days remain cached so they
            # can still expose the latest known power value.
            previous = self._day_cache.get(day)
            if previous is None or meter_day.points or not previous.points:
                if previous is None or not self._is_complete_day(previous) or self._is_complete_day(meter_day):
                    self._day_cache[day] = meter_day
            day += timedelta(days=1)

        for cached_day in list(self._day_cache):
            if cached_day < cache_start:
                self._day_cache.pop(cached_day, None)

        all_days = sorted(
            (item for item in self._day_cache.values() if item.points),
            key=lambda item: item.requested_day,
        )
        complete_days = [item for item in all_days if self._is_complete_day(item)]

        if not complete_days:
            raise UpdateFailed(
                "IBC has not yet returned a complete day of 15-minute meter data"
            )

        annualized_kwh = self._annualized_consumption(complete_days)
        await self._async_prepare_tariff(annualized_kwh)
        assert self._tariff is not None

        (
            imported_energy,
            imported_cost,
            tracked_energy,
            tracked_cost,
        ) = await self._async_insert_statistics(complete_days)

        latest_any = all_days[-1] if all_days else complete_days[-1]
        latest_complete = complete_days[-1]
        yesterday_data = next(
            (item for item in reversed(complete_days) if item.requested_day == yesterday),
            None,
        )

        latest_point = latest_any.points[-1]
        try:
            age = dt_util.now() - latest_point.timestamp.astimezone(dt_util.DEFAULT_TIME_ZONE)
            data_age_hours = max(0.0, age.total_seconds() / 3600)
        except (ValueError, OverflowError):
            data_age_hours = None

        daily = {item.requested_day: item.energy_kwh for item in complete_days}
        recent7_days = [d for d in sorted(daily) if d >= yesterday - timedelta(days=6)]
        previous7_days = [
            d
            for d in sorted(daily)
            if yesterday - timedelta(days=13) <= d <= yesterday - timedelta(days=7)
        ]
        recent30_days = [d for d in sorted(daily) if d >= yesterday - timedelta(days=29)]
        month_days = [
            d
            for d in sorted(daily)
            if d.year == today.year and d.month == today.month
        ]

        recent7_total = sum(daily[d] for d in recent7_days)
        previous7_total = sum(daily[d] for d in previous7_days)
        recent30_total = sum(daily[d] for d in recent30_days)
        month_total = sum(daily[d] for d in month_days)

        avg7 = recent7_total / len(recent7_days) if recent7_days else None
        avg30 = recent30_total / len(recent30_days) if recent30_days else None
        trend7 = None
        if recent7_days and previous7_days and previous7_total > 0:
            recent_avg = recent7_total / len(recent7_days)
            previous_avg = previous7_total / len(previous7_days)
            if previous_avg > 0:
                trend7 = (recent_avg / previous_avg - 1.0) * 100.0

        profile = self._build_load_profile(complete_days)
        days_in_month = monthrange(today.year, today.month)[1]
        projected_month_energy = None
        if month_days:
            projected_month_energy = (month_total / len(month_days)) * days_in_month

        latest_day_fixed_fraction = 1.0 / monthrange(
            latest_complete.requested_day.year, latest_complete.requested_day.month
        )[1]
        latest_day_cost = (
            self._tariff.variable_cost(latest_complete.energy_kwh)
            + self._tariff.fixed_incl_vat_chf_month * latest_day_fixed_fraction
        )
        month_fixed_fraction = len(month_days) / days_in_month if month_days else 0.0
        month_cost = (
            self._tariff.variable_cost(month_total)
            + self._tariff.fixed_incl_vat_chf_month * month_fixed_fraction
        ) if month_days else None
        projected_month_cost = (
            self._tariff.variable_cost(projected_month_energy)
            + self._tariff.fixed_incl_vat_chf_month
        ) if projected_month_energy is not None else None

        month_breakdown = self._tariff.breakdown(
            month_total,
            fixed_fraction=month_fixed_fraction,
        ) if month_days else {}

        base_load_kw = profile["base_load_kw"]
        base_load_cost_year = (
            base_load_kw * 8760.0 * self._tariff.variable_incl_vat_chf_per_kwh
            if base_load_kw is not None
            else None
        )

        return IBCData(
            latest_power_kw=latest_point.power_kw,
            latest_timestamp=latest_point.timestamp,
            latest_day=latest_complete.requested_day,
            latest_day_energy_kwh=round(latest_complete.energy_kwh, 6),
            yesterday_energy_kwh=(
                round(yesterday_data.energy_kwh, 6) if yesterday_data else None
            ),
            last_7_days_energy_kwh=(round(recent7_total, 6) if recent7_days else None),
            month_energy_kwh=(round(month_total, 6) if month_days else None),
            data_age_hours=(round(data_age_hours, 2) if data_age_hours is not None else None),
            last_imported_day=latest_complete.requested_day,
            statistic_id=self.statistic_id,
            cost_statistic_id=self.cost_statistic_id,
            imported_samples=imported_energy,
            imported_cost_samples=imported_cost,
            tracked_energy_kwh=(round(tracked_energy, 6) if tracked_energy is not None else None),
            tracked_cost_chf=(round(tracked_cost, 4) if tracked_cost is not None else None),
            days_analyzed=len(complete_days),
            avg_day_7d_kwh=(round(avg7, 3) if avg7 is not None else None),
            avg_day_30d_kwh=(round(avg30, 3) if avg30 is not None else None),
            trend_7d_pct=(round(trend7, 1) if trend7 is not None else None),
            estimated_annual_kwh=(round(annualized_kwh, 0) if annualized_kwh is not None else None),
            base_load_kw=(round(base_load_kw, 3) if base_load_kw is not None else None),
            base_load_cost_year_chf=(round(base_load_cost_year, 2) if base_load_cost_year is not None else None),
            night_share_pct=profile["night_share_pct"],
            peak_15m_kw=profile["peak_15m_kw"],
            peak_15m_timestamp=profile["peak_15m_timestamp"],
            peak_hour_kwh=profile["peak_hour_kwh"],
            peak_hour_timestamp=profile["peak_hour_timestamp"],
            typical_peak_hour=profile["typical_peak_hour"],
            projected_month_energy_kwh=(round(projected_month_energy, 2) if projected_month_energy is not None else None),
            latest_day_cost_chf=round(latest_day_cost, 2),
            month_cost_chf=(round(month_cost, 2) if month_cost is not None else None),
            projected_month_cost_chf=(round(projected_month_cost, 2) if projected_month_cost is not None else None),
            variable_price_chf_kwh=round(self._tariff.variable_incl_vat_chf_per_kwh, 5),
            fixed_month_chf=round(self._tariff.fixed_incl_vat_chf_month, 2),
            tariff_product=self._tariff.product_name,
            tariff_group=self._tariff.tariff_group,
            tariff_meter_type=self._tariff.meter_type,
            tariff_source=self._tariff.source,
            cost_breakdown_month=month_breakdown,
            top_load_events=profile["top_load_events"],
        )

    async def _async_prepare_tariff(self, annualized_kwh: float | None) -> None:
        """Detect the customer's product from portal contract data when possible."""
        if not self._contract_checked:
            self._contract_checked = True
            object_id = self.config_entry.data.get(CONF_OBJECT_ID)
            subject_id = self.config_entry.data.get(CONF_SUBJECT_ID)
            role = self.config_entry.data.get(CONF_ROLE, DEFAULT_ROLE)
            if object_id is not None and subject_id is not None:
                try:
                    self._contract_payload = await self.api.async_get_contracts(
                        str(object_id), str(subject_id), int(role)
                    )
                except (IBCConnectionError, IBCDataError, IBCAuthError) as err:
                    _LOGGER.debug("IBC contract metadata unavailable: %s", err)
                    self._contract_payload = None

        self._tariff = detect_2026_tariff(
            self._contract_payload,
            annualized_kwh=annualized_kwh,
        )

    @staticmethod
    def _annualized_consumption(days: list[IBCMeterDay]) -> float | None:
        """Annualize the latest available daily consumption average."""
        usable = days[-30:]
        if not usable:
            return None
        return (sum(item.energy_kwh for item in usable) / len(usable)) * 365.0

    @staticmethod
    def _candidate_label(power_kw: float) -> str:
        """Return deliberately broad appliance candidates for an aggregate peak."""
        if power_kw >= 3.0:
            return "Kochfeld/Backofen, Wasserkocher, Trockner oder anderes Heizgerät"
        if power_kw >= 1.5:
            return "Geschirrspüler, Waschmaschine, Backofen oder Heizgerät"
        if power_kw >= 0.8:
            return "Haushaltsgerät, Computer/AV oder Heiz-/Kühlgerät"
        return "Grundlast beziehungsweise mehrere kleinere Verbraucher"

    def _build_load_profile(self, days: list[IBCMeterDay]) -> dict[str, Any]:
        """Derive load-shape metrics from complete quarter-hour curves."""
        points = [point for meter_day in days[-30:] for point in meter_day.points]
        if not points:
            return {
                "base_load_kw": None,
                "night_share_pct": None,
                "peak_15m_kw": None,
                "peak_15m_timestamp": None,
                "peak_hour_kwh": None,
                "peak_hour_timestamp": None,
                "typical_peak_hour": None,
                "top_load_events": [],
            }

        sorted_powers = sorted(max(0.0, point.power_kw) for point in points)
        percentile_index = max(0, min(len(sorted_powers) - 1, int((len(sorted_powers) - 1) * 0.10)))
        base_load_kw = sorted_powers[percentile_index]

        hourly: dict[datetime, float] = defaultdict(float)
        hourly_by_clock: dict[int, list[float]] = defaultdict(list)
        night_energy = 0.0
        total_energy = 0.0
        for point in points:
            interval_start = point.timestamp - timedelta(minutes=15)
            local_start = interval_start.astimezone(dt_util.DEFAULT_TIME_ZONE)
            energy = max(0.0, point.power_kw) * 0.25
            total_energy += energy
            if 0 <= local_start.hour < 6:
                night_energy += energy
            local_hour = local_start.replace(minute=0, second=0, microsecond=0)
            hourly[local_hour] += energy

        for hour_start, energy in hourly.items():
            hourly_by_clock[hour_start.hour].append(energy)

        peak_point = max(points, key=lambda point: point.power_kw)
        peak_hour_timestamp = None
        peak_hour_kwh = None
        if hourly:
            peak_hour_timestamp, peak_hour_kwh = max(hourly.items(), key=lambda item: item[1])

        typical_peak_hour = None
        if hourly_by_clock:
            typical_peak_hour = max(
                hourly_by_clock,
                key=lambda hour: sum(hourly_by_clock[hour]) / len(hourly_by_clock[hour]),
            )

        top_events: list[dict[str, Any]] = []
        for point in sorted(points, key=lambda item: item.power_kw, reverse=True):
            local_ts = point.timestamp.astimezone(dt_util.DEFAULT_TIME_ZONE)
            if any(
                abs((local_ts - existing["_ts"]).total_seconds()) < 45 * 60
                for existing in top_events
            ):
                continue
            top_events.append(
                {
                    "_ts": local_ts,
                    "zeit": local_ts.isoformat(),
                    "leistung_kw": round(point.power_kw, 3),
                    "moegliche_verursacher": self._candidate_label(point.power_kw),
                }
            )
            if len(top_events) >= 5:
                break
        for event in top_events:
            event.pop("_ts", None)

        return {
            "base_load_kw": base_load_kw,
            "night_share_pct": (round(night_energy / total_energy * 100.0, 1) if total_energy > 0 else None),
            "peak_15m_kw": round(peak_point.power_kw, 3),
            "peak_15m_timestamp": peak_point.timestamp,
            "peak_hour_kwh": (round(peak_hour_kwh, 3) if peak_hour_kwh is not None else None),
            "peak_hour_timestamp": peak_hour_timestamp,
            "typical_peak_hour": typical_peak_hour,
            "top_load_events": top_events,
        }

    async def _async_insert_statistics(
        self,
        days: list[IBCMeterDay],
    ) -> tuple[int, int, float | None, float | None]:
        """Convert complete 15-minute curves into hourly energy and cost statistics."""
        assert self._tariff is not None
        recorder = get_instance(self.hass)
        last_energy = await recorder.async_add_executor_job(
            get_last_statistics,
            self.hass,
            1,
            self.statistic_id,
            True,
            {"sum"},
        )
        last_cost = await recorder.async_add_executor_job(
            get_last_statistics,
            self.hass,
            1,
            self.cost_statistic_id,
            True,
            {"sum"},
        )

        energy_last_start: datetime | None = None
        energy_sum = 0.0
        if last_energy and self.statistic_id in last_energy:
            row = last_energy[self.statistic_id][0]
            energy_last_start = dt_util.utc_from_timestamp(float(row["start"]))
            energy_sum = float(row.get("sum") or 0.0)

        cost_last_start: datetime | None = None
        cost_sum = 0.0
        if last_cost and self.cost_statistic_id in last_cost:
            row = last_cost[self.cost_statistic_id][0]
            cost_last_start = dt_util.utc_from_timestamp(float(row["start"]))
            cost_sum = float(row.get("sum") or 0.0)

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

        energy_rows: list[StatisticData] = []
        cost_rows: list[StatisticData] = []
        for hour_start in sorted(hourly_energy):
            energy = hourly_energy[hour_start]
            if energy_last_start is None or hour_start > energy_last_start:
                energy_sum += energy
                energy_rows.append(
                    StatisticData(start=hour_start, state=energy, sum=energy_sum)
                )
            if cost_last_start is None or hour_start > cost_last_start:
                hourly_cost = self._tariff.variable_cost(energy)
                cost_sum += hourly_cost
                cost_rows.append(
                    StatisticData(start=hour_start, state=hourly_cost, sum=cost_sum)
                )

        if energy_rows:
            energy_metadata = StatisticMetaData(
                mean_type=StatisticMeanType.NONE,
                has_sum=True,
                name="IBC Strombezug stündlich",
                source=DOMAIN,
                statistic_id=self.statistic_id,
                unit_class=EnergyConverter.UNIT_CLASS,
                unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
            )
            async_add_external_statistics(self.hass, energy_metadata, energy_rows)
            _LOGGER.info("Imported %s corrected IBC hourly energy statistics", len(energy_rows))

        if cost_rows:
            cost_metadata = StatisticMetaData(
                mean_type=StatisticMeanType.NONE,
                has_sum=True,
                name="IBC variable Stromkosten stündlich",
                source=DOMAIN,
                statistic_id=self.cost_statistic_id,
                unit_class=None,
                unit_of_measurement=None,
            )
            async_add_external_statistics(self.hass, cost_metadata, cost_rows)
            _LOGGER.info("Imported %s IBC hourly cost statistics", len(cost_rows))

        return (
            len(energy_rows),
            len(cost_rows),
            energy_sum if (energy_rows or last_energy) else None,
            cost_sum if (cost_rows or last_cost) else None,
        )
