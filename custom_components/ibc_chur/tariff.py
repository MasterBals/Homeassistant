"""IBC 2026 electricity tariff model and account detection helpers."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any


@dataclass(frozen=True, slots=True)
class IBCTariffProfile:
    """Electricity tariff used for consumption-cost calculations."""

    year: int
    product_name: str
    tariff_group: str
    meter_type: str
    source: str
    energy_rp_per_kwh: float
    network_rp_per_kwh: float
    sdl_rp_per_kwh: float
    federal_surcharge_rp_per_kwh: float
    concession_rp_per_kwh: float
    network_base_chf_month: float
    meter_base_chf_month: float
    vat_rate: float
    power_tariff_chf_kw_month: float = 0.0

    @property
    def variable_excl_vat_chf_per_kwh(self) -> float:
        """Return all consumption-dependent components excluding VAT."""
        return (
            self.energy_rp_per_kwh
            + self.network_rp_per_kwh
            + self.sdl_rp_per_kwh
            + self.federal_surcharge_rp_per_kwh
            + self.concession_rp_per_kwh
        ) / 100.0

    @property
    def variable_incl_vat_chf_per_kwh(self) -> float:
        """Return all consumption-dependent components including VAT."""
        return self.variable_excl_vat_chf_per_kwh * (1.0 + self.vat_rate)

    @property
    def fixed_excl_vat_chf_month(self) -> float:
        """Return regular fixed monthly grid and metering charges."""
        return self.network_base_chf_month + self.meter_base_chf_month

    @property
    def fixed_incl_vat_chf_month(self) -> float:
        """Return regular fixed monthly charges including VAT."""
        return self.fixed_excl_vat_chf_month * (1.0 + self.vat_rate)

    def variable_cost(self, energy_kwh: float) -> float:
        """Calculate variable electricity cost including VAT."""
        return max(0.0, energy_kwh) * self.variable_incl_vat_chf_per_kwh

    def breakdown(self, energy_kwh: float, *, fixed_fraction: float = 0.0) -> dict[str, float]:
        """Return an itemized CHF cost breakdown including VAT."""
        energy_kwh = max(0.0, energy_kwh)
        multiplier = (1.0 + self.vat_rate) / 100.0
        energy = energy_kwh * self.energy_rp_per_kwh * multiplier
        network_usage = energy_kwh * self.network_rp_per_kwh * multiplier
        sdl = energy_kwh * self.sdl_rp_per_kwh * multiplier
        federal = energy_kwh * self.federal_surcharge_rp_per_kwh * multiplier
        concession = energy_kwh * self.concession_rp_per_kwh * multiplier
        network_base = self.network_base_chf_month * max(0.0, fixed_fraction) * (1.0 + self.vat_rate)
        meter_base = self.meter_base_chf_month * max(0.0, fixed_fraction) * (1.0 + self.vat_rate)
        total = energy + network_usage + sdl + federal + concession + network_base + meter_base
        return {
            "energie_chf": round(energy, 4),
            "netznutzung_chf": round(network_usage, 4),
            "systemdienstleistungen_chf": round(sdl, 4),
            "netzzuschlag_bund_chf": round(federal, 4),
            "konzessionsabgabe_chf": round(concession, 4),
            "grundtarif_netz_chf": round(network_base, 4),
            "messtarif_chf": round(meter_base, 4),
            "total_chf": round(total, 4),
        }


def _payload_text(payload: Any) -> str:
    """Serialize arbitrary portal JSON for resilient product-name discovery."""
    try:
        return json.dumps(payload, ensure_ascii=False, default=str).lower()
    except (TypeError, ValueError):
        return str(payload).lower()


def detect_2026_tariff(
    contract_payload: Any,
    *,
    annualized_kwh: float | None = None,
) -> IBCTariffProfile:
    """Detect the 2026 IBC tariff with conservative household fallbacks.

    IBC publishes VivaPower Grischa as the standard product and Stromnetz H for
    metering points below 50'000 kWh/year. The portal contract payload is used
    whenever it explicitly names another product/group/metering method.
    """
    text = _payload_text(contract_payload)

    if "vivapower europa" in text:
        product_name = "VivaPower Europa"
        energy_rate = 11.10
        source = "IBC Kundenportal"
    elif "vivapower grischa" in text or "plessurpower" in text:
        product_name = "VivaPower Grischa"
        energy_rate = 11.90
        source = "IBC Kundenportal"
    else:
        product_name = "VivaPower Grischa"
        energy_rate = 11.90
        source = "IBC Standardprodukt 2026"

    if "ne5" in text or "netzebene 5" in text:
        tariff_group = "NE5"
        network_rate = 5.90
        power_rate = 7.00
    elif "stromnetz g" in text or "tarifgruppe g" in text:
        tariff_group = "G"
        network_rate = 9.50
        power_rate = 8.00
    elif "stromnetz h" in text or "tarifgruppe h" in text:
        tariff_group = "H"
        network_rate = 10.00
        power_rate = 0.0
    elif annualized_kwh is not None and annualized_kwh >= 50000:
        tariff_group = "G"
        network_rate = 9.50
        power_rate = 8.00
        source += " / Gruppe aus Verbrauch abgeleitet"
    else:
        tariff_group = "H"
        network_rate = 10.00
        power_rate = 0.0
        source += " / Gruppe H gemäss IBC Standardzuordnung"

    if "wandlermessung" in text:
        meter_type = "Wandlermessung"
        meter_base = 60.00 if tariff_group == "NE5" else 6.50
    elif "virtuelle messung" in text or "virtuell" in text:
        meter_type = "Virtuelle Messung"
        meter_base = 2.00
    else:
        meter_type = "Direktmessung"
        meter_base = 4.20 if tariff_group in {"H", "G"} else 0.0

    return IBCTariffProfile(
        year=2026,
        product_name=product_name,
        tariff_group=tariff_group,
        meter_type=meter_type,
        source=source,
        energy_rp_per_kwh=energy_rate,
        network_rp_per_kwh=network_rate,
        sdl_rp_per_kwh=0.73,
        federal_surcharge_rp_per_kwh=2.30,
        concession_rp_per_kwh=2.00,
        network_base_chf_month=7.00,
        meter_base_chf_month=meter_base,
        vat_rate=0.081,
        power_tariff_chf_kw_month=power_rate,
    )
