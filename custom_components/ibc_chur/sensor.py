"""Sensor platform for IBC Chur."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import IBCData, IBCDataUpdateCoordinator


@dataclass(frozen=True, kw_only=True)
class IBCSensorEntityDescription(SensorEntityDescription):
    """Describe an IBC sensor."""

    value_fn: Callable[[IBCData], Any]


SENSORS: tuple[IBCSensorEntityDescription, ...] = (
    IBCSensorEntityDescription(
        key="latest_power",
        translation_key="latest_power",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
        value_fn=lambda data: data.latest_power_kw,
    ),
    IBCSensorEntityDescription(
        key="latest_day_energy",
        translation_key="latest_day_energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        suggested_display_precision=3,
        value_fn=lambda data: data.latest_day_energy_kwh,
    ),
    IBCSensorEntityDescription(
        key="yesterday_energy",
        translation_key="yesterday_energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        suggested_display_precision=3,
        value_fn=lambda data: data.yesterday_energy_kwh,
    ),
    IBCSensorEntityDescription(
        key="last_7_days_energy",
        translation_key="last_7_days_energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        suggested_display_precision=2,
        value_fn=lambda data: data.last_7_days_energy_kwh,
    ),
    IBCSensorEntityDescription(
        key="month_energy",
        translation_key="month_energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        suggested_display_precision=2,
        value_fn=lambda data: data.month_energy_kwh,
    ),
    IBCSensorEntityDescription(
        key="avg_day_7d",
        translation_key="avg_day_7d",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda data: data.avg_day_7d_kwh,
    ),
    IBCSensorEntityDescription(
        key="avg_day_30d",
        translation_key="avg_day_30d",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda data: data.avg_day_30d_kwh,
    ),
    IBCSensorEntityDescription(
        key="trend_7d",
        translation_key="trend_7d",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda data: data.trend_7d_pct,
    ),
    IBCSensorEntityDescription(
        key="estimated_annual_energy",
        translation_key="estimated_annual_energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda data: data.estimated_annual_kwh,
    ),
    IBCSensorEntityDescription(
        key="base_load",
        translation_key="base_load",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda data: (
            data.base_load_kw * 1000.0 if data.base_load_kw is not None else None
        ),
    ),
    IBCSensorEntityDescription(
        key="base_load_cost_year",
        translation_key="base_load_cost_year",
        native_unit_of_measurement="CHF",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda data: data.base_load_cost_year_chf,
    ),
    IBCSensorEntityDescription(
        key="night_share",
        translation_key="night_share",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda data: data.night_share_pct,
    ),
    IBCSensorEntityDescription(
        key="peak_15m",
        translation_key="peak_15m",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
        value_fn=lambda data: data.peak_15m_kw,
    ),
    IBCSensorEntityDescription(
        key="peak_hour",
        translation_key="peak_hour",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
        value_fn=lambda data: data.peak_hour_kwh,
    ),
    IBCSensorEntityDescription(
        key="projected_month_energy",
        translation_key="projected_month_energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda data: data.projected_month_energy_kwh,
    ),
    IBCSensorEntityDescription(
        key="latest_day_cost",
        translation_key="latest_day_cost",
        native_unit_of_measurement="CHF",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda data: data.latest_day_cost_chf,
    ),
    IBCSensorEntityDescription(
        key="month_cost",
        translation_key="month_cost",
        native_unit_of_measurement="CHF",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda data: data.month_cost_chf,
    ),
    IBCSensorEntityDescription(
        key="projected_month_cost",
        translation_key="projected_month_cost",
        native_unit_of_measurement="CHF",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda data: data.projected_month_cost_chf,
    ),
    IBCSensorEntityDescription(
        key="variable_price",
        translation_key="variable_price",
        native_unit_of_measurement="CHF/kWh",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=5,
        value_fn=lambda data: data.variable_price_chf_kwh,
    ),
    IBCSensorEntityDescription(
        key="last_measurement",
        translation_key="last_measurement",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data: data.latest_timestamp,
    ),
    IBCSensorEntityDescription(
        key="data_age",
        translation_key="data_age",
        native_unit_of_measurement="h",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda data: data.data_age_hours,
    ),
    IBCSensorEntityDescription(
        key="analysis",
        translation_key="analysis",
        icon="mdi:chart-box-outline",
        value_fn=lambda data: "bereit" if data.days_analyzed else "keine Daten",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: IBCDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(IBCSensor(coordinator, entry, description) for description in SENSORS)


class IBCSensor(CoordinatorEntity[IBCDataUpdateCoordinator], SensorEntity):
    """Representation of one IBC sensor."""

    entity_description: IBCSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: IBCDataUpdateCoordinator,
        entry: ConfigEntry,
        description: IBCSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.api.meteringpoint}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.api.meteringpoint)},
            name="IBC Smart Meter",
            manufacturer="IBC Energie Wasser Chur",
            model="Kundenportal Lastgang + Analyse",
            configuration_url="https://portal.ibc-chur.ch/ebp/consumption/meterdata",
        )

    @property
    def native_value(self) -> Any:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        data = self.coordinator.data
        if data is None:
            return None

        if self.entity_description.key == "analysis":
            return {
                "tage_analysiert": data.days_analyzed,
                "typische_spitzenstunde": (
                    f"{data.typical_peak_hour:02d}:00"
                    if data.typical_peak_hour is not None
                    else None
                ),
                "spitze_15min_zeit": (
                    data.peak_15m_timestamp.isoformat()
                    if data.peak_15m_timestamp
                    else None
                ),
                "spitzenstunde_zeit": (
                    data.peak_hour_timestamp.isoformat()
                    if data.peak_hour_timestamp
                    else None
                ),
                "tarifprodukt": data.tariff_product,
                "tarifgruppe": data.tariff_group,
                "messart": data.tariff_meter_type,
                "tarifquelle": data.tariff_source,
                "variabler_preis_chf_kwh_inkl_mwst": data.variable_price_chf_kwh,
                "fixkosten_chf_monat_inkl_mwst": data.fixed_month_chf,
                "kostenaufteilung_laufender_monat": data.cost_breakdown_month,
                "groesste_lastspitzen": data.top_load_events,
                "hinweis_geraetezuordnung": (
                    "Die möglichen Verursacher werden aus Lastsignaturen abgeleitet und "
                    "sind Indizien, keine direkte Gerätemessung."
                ),
                "energy_statistic_id": data.statistic_id,
                "cost_statistic_id": data.cost_statistic_id,
            }

        if self.entity_description.key == "peak_15m":
            return {
                "zeitpunkt": (
                    data.peak_15m_timestamp.isoformat()
                    if data.peak_15m_timestamp
                    else None
                )
            }
        if self.entity_description.key == "peak_hour":
            return {
                "zeitpunkt": (
                    data.peak_hour_timestamp.isoformat()
                    if data.peak_hour_timestamp
                    else None
                )
            }

        if self.entity_description.key in {
            "latest_day_energy",
            "yesterday_energy",
            "last_7_days_energy",
            "month_energy",
        }:
            return {
                "statistic_id": data.statistic_id,
                "cost_statistic_id": data.cost_statistic_id,
                "latest_complete_day": (
                    data.latest_day.isoformat() if data.latest_day else None
                ),
                "tracked_energy_kwh": data.tracked_energy_kwh,
                "tracked_variable_cost_chf": data.tracked_cost_chf,
                "imported_hourly_statistics_last_refresh": data.imported_samples,
                "last_imported_day": (
                    data.last_imported_day.isoformat()
                    if data.last_imported_day
                    else None
                ),
            }

        if self.entity_description.key in {"latest_day_cost", "month_cost", "projected_month_cost"}:
            return {
                "tarifprodukt": data.tariff_product,
                "tarifgruppe": data.tariff_group,
                "variabler_preis_chf_kwh_inkl_mwst": data.variable_price_chf_kwh,
                "fixkosten_chf_monat_inkl_mwst": data.fixed_month_chf,
                "kostenaufteilung_laufender_monat": data.cost_breakdown_month,
            }

        return None
