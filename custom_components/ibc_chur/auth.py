"""Authentication helpers for IBC Energie Wasser Chur."""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

from aiohttp import ClientError, ClientSession, ClientTimeout, CookieJar
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    OAUTH_CLIENT_ID,
    OAUTH_REDIRECT_CANDIDATES,
    OAUTH_SCOPE,
    OIDC_DISCOVERY_URL,
)


class IBCAuthenticationError(Exception):
    """Base authentication error."""


class IBCInvalidAuth(IBCAuthenticationError):
    """IBC rejected credentials or a refresh token."""


class IBCAuthConnectionError(IBCAuthenticationError):
    """IBC authentication service could not be reached."""


class IBCAuthUnsupported(IBCAuthenticationError):
    """The IBC login requires a step the integration cannot automate."""


class _LoginFormParser(HTMLParser):
    """Extract a Keycloak login form."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.action: str | None = None
        self.fields: dict[str, str] = {}
        self._inside_form = False

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        values = {key: value or "" for key, value in attrs}
        if tag == "form":
            action = values.get("action", "")
            form_id = values.get("id", "")
            if "login-actions/authenticate" in action or form_id == "kc-form-login":
                self.action = action
                self._inside_form = True
            return
        if tag == "input" and self._inside_form:
            name = values.get("name")
            if name:
                self.fields[name] = values.get("value", "")

    def handle_endtag(self, tag: str) -> None:
        if tag == "form" and self._inside_form:
            self._inside_form = False


def _pkce_pair() -> tuple[str, str]:
    """Create an RFC 7636 S256 verifier/challenge pair."""
    verifier = secrets.token_urlsafe(72)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).decode("ascii").rstrip("=")
    return verifier, challenge


def _normalise_token(
    payload: dict[str, Any], old_refresh: str | None = None
) -> dict[str, Any]:
    """Add absolute expiry timestamps and preserve rotating refresh tokens."""
    token = dict(payload)
    if old_refresh and not token.get("refresh_token"):
        token["refresh_token"] = old_refresh
    now = time.time()
    try:
        token["expires_at"] = now + float(token.get("expires_in", 0))
    except (TypeError, ValueError):
        token["expires_at"] = now
    try:
        token["refresh_expires_at"] = now + float(token.get("refresh_expires_in", 0))
    except (TypeError, ValueError):
        pass
    return token


class IBCAuthenticator:
    """Authenticate against the Keycloak realm used by the IBC portal."""

    def __init__(self, session: ClientSession) -> None:
        self._session = session
        self._discovery: dict[str, Any] | None = None

    async def _async_discovery(self) -> dict[str, Any]:
        if self._discovery is not None:
            return self._discovery
        try:
            async with self._session.get(
                OIDC_DISCOVERY_URL, timeout=ClientTimeout(total=30)
            ) as response:
                response.raise_for_status()
                data = await response.json(content_type=None)
        except (ClientError, TimeoutError, ValueError) as err:
            raise IBCAuthConnectionError(str(err)) from err
        if not isinstance(data, dict):
            raise IBCAuthConnectionError("IBC OIDC discovery returned no JSON object")
        self._discovery = data
        return data

    async def async_login(self, username: str, password: str) -> dict[str, Any]:
        """Obtain OAuth tokens without retaining the user's password."""
        direct_result = await self._async_direct_grant(username, password)
        if direct_result is not None:
            return direct_result
        return await self._async_pkce_login(username, password)

    async def _async_direct_grant(
        self, username: str, password: str
    ) -> dict[str, Any] | None:
        """Use direct access grants when the public portal client permits them."""
        discovery = await self._async_discovery()
        token_endpoint = str(discovery.get("token_endpoint") or "")
        if not token_endpoint:
            raise IBCAuthConnectionError("IBC discovery has no token endpoint")
        form = {
            "grant_type": "password",
            "client_id": OAUTH_CLIENT_ID,
            "scope": OAUTH_SCOPE,
            "username": username,
            "password": password,
        }
        try:
            async with self._session.post(
                token_endpoint,
                data=form,
                timeout=ClientTimeout(total=30),
            ) as response:
                data = await response.json(content_type=None)
                if response.status == 200 and isinstance(data, dict):
                    if data.get("access_token"):
                        return _normalise_token(data)
                    raise IBCInvalidAuth("IBC returned no access token")
                error = str(data.get("error", "")) if isinstance(data, dict) else ""
                description = (
                    str(data.get("error_description", ""))
                    if isinstance(data, dict)
                    else ""
                )
        except (ClientError, TimeoutError, ValueError) as err:
            raise IBCAuthConnectionError(str(err)) from err

        if error in {"unauthorized_client", "unsupported_grant_type"} or (
            "direct access grants" in description.lower()
        ):
            return None
        if error in {"invalid_grant", "invalid_request"}:
            raise IBCInvalidAuth(description or "Invalid IBC username or password")
        return None

    async def _async_pkce_login(
        self, username: str, password: str
    ) -> dict[str, Any]:
        """Perform the portal's Authorization Code + PKCE login server-side."""
        discovery = await self._async_discovery()
        authorization_endpoint = str(discovery.get("authorization_endpoint") or "")
        token_endpoint = str(discovery.get("token_endpoint") or "")
        if not authorization_endpoint or not token_endpoint:
            raise IBCAuthConnectionError("IBC discovery is missing OAuth endpoints")

        last_redirect_error = False
        for redirect_uri in OAUTH_REDIRECT_CANDIDATES:
            verifier, challenge = _pkce_pair()
            state = secrets.token_urlsafe(24)
            params = {
                "response_type": "code",
                "client_id": OAUTH_CLIENT_ID,
                "redirect_uri": redirect_uri,
                "scope": OAUTH_SCOPE,
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
            authorize_url = f"{authorization_endpoint}?{urlencode(params)}"

            async with ClientSession(cookie_jar=CookieJar(unsafe=True)) as browser:
                try:
                    async with browser.get(
                        authorize_url,
                        timeout=ClientTimeout(total=30),
                    ) as response:
                        body = await response.text()
                        final_url = str(response.url)
                except (ClientError, TimeoutError) as err:
                    raise IBCAuthConnectionError(str(err)) from err

                lowered = body.lower()
                if response.status >= 400 and "redirect_uri" in lowered:
                    last_redirect_error = True
                    continue

                parser = _LoginFormParser()
                parser.feed(body)
                if not parser.action:
                    if "redirect_uri" in lowered and "ungültig" in lowered:
                        last_redirect_error = True
                        continue
                    raise IBCAuthUnsupported(
                        "IBC login form could not be recognised"
                    )

                login_url = urljoin(final_url, parser.action)
                form = dict(parser.fields)
                form["username"] = username
                form["password"] = password
                form.setdefault("credentialId", "")

                try:
                    async with browser.post(
                        login_url,
                        data=form,
                        allow_redirects=False,
                        timeout=ClientTimeout(total=30),
                    ) as response:
                        status = response.status
                        location = response.headers.get("Location")
                        body = await response.text()
                except (ClientError, TimeoutError) as err:
                    raise IBCAuthConnectionError(str(err)) from err

                for _ in range(10):
                    if location:
                        target = urljoin(login_url, location)
                        query = parse_qs(urlparse(target).query)
                        if "error" in query:
                            raise IBCInvalidAuth(
                                query.get("error_description", query["error"])[0]
                            )
                        if "code" in query:
                            returned_state = query.get("state", [state])[0]
                            if returned_state != state:
                                raise IBCAuthenticationError(
                                    "IBC OAuth state validation failed"
                                )
                            return await self._async_exchange_code(
                                token_endpoint,
                                query["code"][0],
                                redirect_uri,
                                verifier,
                            )
                        try:
                            async with browser.get(
                                target,
                                allow_redirects=False,
                                timeout=ClientTimeout(total=30),
                            ) as response:
                                status = response.status
                                location = response.headers.get("Location")
                                body = await response.text()
                                login_url = str(response.url)
                        except (ClientError, TimeoutError) as err:
                            raise IBCAuthConnectionError(str(err)) from err
                        continue
                    break

                lowered = body.lower()
                if "otp" in lowered or "totp" in lowered or "one-time" in lowered:
                    raise IBCAuthUnsupported(
                        "IBC requires an additional one-time-password step"
                    )
                if status in {200, 400, 401, 403}:
                    raise IBCInvalidAuth("Invalid IBC username or password")

        if last_redirect_error:
            raise IBCAuthUnsupported(
                "No known IBC portal redirect URI was accepted by the OAuth client"
            )
        raise IBCAuthUnsupported("IBC portal login could not be completed")

    async def _async_exchange_code(
        self,
        token_endpoint: str,
        code: str,
        redirect_uri: str,
        verifier: str,
    ) -> dict[str, Any]:
        form = {
            "grant_type": "authorization_code",
            "client_id": OAUTH_CLIENT_ID,
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": verifier,
        }
        try:
            async with self._session.post(
                token_endpoint,
                data=form,
                timeout=ClientTimeout(total=30),
            ) as response:
                data = await response.json(content_type=None)
                if response.status != 200 or not isinstance(data, dict):
                    description = (
                        str(data.get("error_description", "Token exchange failed"))
                        if isinstance(data, dict)
                        else "Token exchange failed"
                    )
                    raise IBCInvalidAuth(description)
        except IBCInvalidAuth:
            raise
        except (ClientError, TimeoutError, ValueError) as err:
            raise IBCAuthConnectionError(str(err)) from err
        if not data.get("access_token"):
            raise IBCInvalidAuth("IBC returned no access token")
        return _normalise_token(data)

    async def async_refresh(self, refresh_token: str) -> dict[str, Any]:
        """Refresh an IBC OAuth token."""
        discovery = await self._async_discovery()
        token_endpoint = str(discovery.get("token_endpoint") or "")
        if not token_endpoint:
            raise IBCAuthConnectionError("IBC discovery has no token endpoint")
        form = {
            "grant_type": "refresh_token",
            "client_id": OAUTH_CLIENT_ID,
            "scope": OAUTH_SCOPE,
            "refresh_token": refresh_token,
        }
        try:
            async with self._session.post(
                token_endpoint,
                data=form,
                timeout=ClientTimeout(total=30),
            ) as response:
                data = await response.json(content_type=None)
                if response.status != 200 or not isinstance(data, dict):
                    description = (
                        str(data.get("error_description", "Refresh token rejected"))
                        if isinstance(data, dict)
                        else "Refresh token rejected"
                    )
                    raise IBCInvalidAuth(description)
        except IBCInvalidAuth:
            raise
        except (ClientError, TimeoutError, ValueError) as err:
            raise IBCAuthConnectionError(str(err)) from err
        if not data.get("access_token"):
            raise IBCInvalidAuth("IBC refresh returned no access token")
        return _normalise_token(data, old_refresh=refresh_token)


class IBCTokenManager:
    """Keep an IBC config-entry token valid and persist token rotation."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        session: ClientSession,
    ) -> None:
        self._hass = hass
        self._entry = entry
        self._auth = IBCAuthenticator(session)

    @property
    def token(self) -> dict[str, Any]:
        value = self._entry.data.get("token", {})
        return dict(value) if isinstance(value, dict) else {}

    async def async_access_token(self) -> str:
        token = self.token
        access_token = token.get("access_token")
        expires_at = token.get("expires_at")
        try:
            valid_until = float(expires_at or 0)
        except (TypeError, ValueError):
            valid_until = 0

        if access_token and (valid_until == 0 or valid_until > time.time() + 60):
            return str(access_token)

        refresh_token = token.get("refresh_token")
        if not refresh_token:
            raise IBCInvalidAuth("IBC refresh token is missing")
        new_token = await self._auth.async_refresh(str(refresh_token))
        self._hass.config_entries.async_update_entry(
            self._entry,
            data={**self._entry.data, "token": new_token},
        )
        return str(new_token["access_token"])
