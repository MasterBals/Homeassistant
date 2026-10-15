# IBC Chur native login flow

Version 0.3.0 avoids the Home Assistant external OAuth redirect because the IBC Keycloak client `ebp-pkce` rejects the generic `my.home-assistant.io` redirect URI.

The integration now asks for the normal IBC portal username and password inside the Home Assistant config flow. The password is used only for the initial authentication and is never persisted. The integration first tries a Keycloak direct-access grant when enabled. If the public portal client does not allow direct access grants, it falls back to the portal's Authorization Code + PKCE flow server-side, using one of the registered IBC portal redirect URIs and intercepting the authorization code before the browser redirect is followed.

Only OAuth tokens and the username are stored in the Home Assistant config entry. Access tokens are refreshed automatically with the observed `grant_type=refresh_token`, `client_id=ebp-pkce`, and `scope=openid profile email` flow. If the refresh token eventually expires, Home Assistant starts a reauthentication flow and asks for the IBC credentials again.

No passwords, access tokens, refresh tokens, browser cookies, or Authorization headers are committed to GitHub or exposed through diagnostics.
