# IBC Energie Wasser Chur for Home Assistant

Custom integration for the authenticated IBC customer portal endpoint used by the load-profile view.

## Confirmed API behaviour

The portal retrieves 15-minute average import power from:

`GET https://portal.ibc-chur.ch/ebp/api/ebp/meterdatavalues/{meteringpoint}`

with `subject_id`, `role`, `date_from`, `date_to`, `aggregation` and `compareActive` query parameters and a Bearer token. The returned series uses `internal_name = ActiveEnergy.Extraction`, `unit = kW` and contains timestamp/value pairs.

IBC timestamps label the end of each 15-minute interval. The integration converts every average-power value to energy with `kWh = kW × 0.25` and imports the result as Home Assistant external long-term statistics.

## Home Assistant entities

- Last 15-minute power (kW)
- Yesterday energy (kWh)
- Last measurement timestamp
- External statistic `ibc_chur:energy_consumption_<hash>` for Energy Dashboard use

## Authentication

Version 0.1 uses the Bearer token already issued to the logged-in IBC portal session. If the token expires, Home Assistant starts a reauthentication flow. Automatic token refresh is intentionally not guessed; it will be added once the portal's token request has been captured and verified.

## Installation

Copy `custom_components/ibc_chur` to `/config/custom_components/ibc_chur`, restart Home Assistant and add **IBC Energie Wasser Chur** under **Settings → Devices & services**.
