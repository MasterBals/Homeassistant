"""Application credentials for IBC Energie Wasser Chur."""

from __future__ import annotations

from typing import Any

from homeassistant.components.application_credentials import (
    AuthorizationServer,
    ClientCredential,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.config_entry_oauth2_flow import (
    AbstractOAuth2Implementation,
    LocalOAuth2ImplementationWithPkce,
)

from .const import OAUTH_CLIENT_SECRET, OIDC_DISCOVERY_URL


async def _async_get_discovery(hass: HomeAssistant) -> dict[str, Any]:
    """Fetch the IBC OpenID Connect discovery document."""
    session = async_get_clientsession(hass)
    async with session.get(OIDC_DISCOVERY_URL, timeout=30) as response:
        response.raise_for_status()
        data = await response.json(content_type=None)
    if not isinstance(data, dict):
        raise TypeError("IBC OIDC discovery did not return a JSON object")
    return data


async def async_get_authorization_server(hass: HomeAssistant) -> AuthorizationServer:
    """Return the authorization and token endpoints from OIDC discovery."""
    data = await _async_get_discovery(hass)
    authorize_url = data.get("authorization_endpoint")
    token_url = data.get("token_endpoint")
    if not authorize_url or not token_url:
        raise ValueError("IBC OIDC discovery is missing required endpoints")
    return AuthorizationServer(
        authorize_url=str(authorize_url),
        token_url=str(token_url),
    )


async def async_get_auth_implementation(
    hass: HomeAssistant,
    auth_domain: str,
    credential: ClientCredential,
) -> AbstractOAuth2Implementation:
    """Return the IBC OAuth2 implementation using Authorization Code + PKCE."""
    server = await async_get_authorization_server(hass)
    return LocalOAuth2ImplementationWithPkce(
        hass,
        auth_domain,
        credential.client_id,
        authorize_url=server.authorize_url,
        token_url=server.token_url,
        client_secret=credential.client_secret or OAUTH_CLIENT_SECRET,
        code_verifier_length=128,
    )
