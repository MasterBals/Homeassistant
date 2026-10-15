# IBC Energie Wasser Chur for Home Assistant

Custom integration for the authenticated IBC customer portal API.

## API

The customer portal uses the API root:

`https://portal.ibc-chur.ch/ebpapi/`

The load-profile endpoint is:

`GET https://portal.ibc-chur.ch/ebpapi/ebp/meterdatavalues/{meteringpoint}`

with `subject_id`, `role`, `date_from`, `date_to`, `aggregation` and `compareActive` query parameters.

For the observed portal configuration, `aggregation=1` is the 15-minute view. The returned import series uses `internal_name = ActiveEnergy.Extraction`, `unit = kW` and timestamp/value pairs.

IBC timestamps label the 15-minute intervals. The integration converts the average power to interval energy with `kWh = kW × 0.25` and imports it as Home Assistant external long-term statistics.

## Authentication

Version 0.2 uses the portal's OpenID Connect / OAuth 2.0 configuration instead of a manually copied Bearer token.

- OIDC discovery: `https://login.ibc-chur.ch/auth/realms/ibc/.well-known/openid-configuration`
- public client: `ebp-pkce`
- flow: Authorization Code with PKCE
- scopes: `openid profile email`
- token refresh: handled by Home Assistant's OAuth2 session helper

No access token, refresh token, password, cookie or Authorization header is stored in the repository. OAuth token data is kept in the Home Assistant config entry and is strictly redacted from integration diagnostics.

## Account discovery

After OAuth login the integration attempts to discover the IBC account hierarchy:

`Subject → role → object → medium/category → metering point`

It calls the portal APIs for roles, objects, invoice/media categories and metering points. If the EBP Subject-ID is not present in the OAuth token and the backend does not expose a collection endpoint, the setup flow asks for that single internal ID once. Object and metering point selection are then automatic/dynamic.

## Home Assistant entities

- Last 15-minute power (kW)
- Yesterday energy (kWh)
- Last measurement timestamp
- External statistic `ibc_chur:energy_consumption_<hash>` for Energy Dashboard use

## Installation

Copy `custom_components/ibc_chur` to `/config/custom_components/ibc_chur`, restart Home Assistant and add **IBC Energie Wasser Chur** under **Settings → Devices & services**.

The integration imports the public `ebp-pkce` client into Home Assistant's Application Credentials storage automatically. No user-created OAuth client secret is required.
