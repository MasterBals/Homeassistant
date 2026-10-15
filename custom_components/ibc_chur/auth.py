"""Authentication helpers for IBC Energie Wasser Chur."""

from __future__ import annotations

import asyncio
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
    OAUTH_LOCALE,
    OAUTH_REDIRECT_URI,
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
    """The IBC login requires an unsupported additional step."""


class _LoginFormParser(HTMLParser):
    """Extract the Keycloak login form and hidden values."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.action: str | None = None
        self.fields: dict[str, str] = {}
        self._inside_login_form = False

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        values = {key: value or "" for key, value in attrs}
        if tag == "form":
            action = values.get("action", "")
            form_id = values.get("id", "")
            self._inside_login_form = (
                "login-actions/authenticate" in action or form_id == "kc-form-login"
            )
            if self._inside_login_form:
                self.action = action
            return
        if tag == "input" and self._inside_login_form:
            name = values.get("name")
            if name:
                self.fields[name] = values.get("value", "")

    def handle_endtag(self, tag: str) -> None:
        if tag == "form" and self._inside_login_form:
            self._inside_login_form = False


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
        token.pop("refresh_expires_at", None)
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
        """Run the same Authorization Code + PKCE flow as the IBC web portal."""
        discovery = await self._async_discovery()
        authorization_endpoint = str(discovery.get("authorization_endpoint") or "")
        token_endpoint = str(discovery.get("token_endpoint") or "")
        if not authorization_endpoint or not token_endpoint:
            raise IBCAuthConnectionError("IBC discovery is missing OAuth endpoints")

        verifier, challenge = _pkce_pair()
        state = secrets.token_urlsafe(42)
        params = {
            "response_type": "code",
            "client_id": OAUTH_CLIENT_ID,
            "state": state,
            "redirect_uri": OAUTH_REDIRECT_URI,
            "scope": OAUTH_SCOPE,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "nonce": state,
            "ui_locales": OAUTH_LOCALE,
            "kc_locale": OAUTH_LOCALE,
        }
        authorize_url = f"{authorization_endpoint}?{urlencode(params)}"

        async with ClientSession(cookie_jar=CookieJar(unsafe=True)) as browser:
            try:
                async with browser.get(
                    authorize_url,
                    timeout=ClientTimeout(total=30),
                ) as response:
                    body = await response.text()
                    current_url = str(response.url)
                    status = response.status
            except (ClientError, TimeoutError) as err:
                raise IBCAuthConnectionError(str(err)) from err

            lowered = body.lower()
            if "redirect_uri" in lowered and (
                "ungültig" in lowered or "invalid" in lowered
            ):
                raise IBCAuthUnsupported("IBC rejected its portal redirect URI")

            parser = _LoginFormParser()
            parser.feed(body)
            if not parser.action:
                if "otp" in lowered or "totp" in lowered or "one-time" in lowered:
                    raise IBCAuthUnsupported(
                        "IBC requires an additional one-time-password step"
                    )
                raise IBCAuthUnsupported("IBC login form could not be recognised")

            login_url = urljoin(current_url, parser.action)
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
                    current_url = str(response.url)
            except (ClientError, TimeoutError) as err:
                raise IBCAuthConnectionError(str(err)) from err

            for _ in range(12):
                if location:
                    target = urljoin(current_url, location)
                    query = parse_qs(urlparse(target).query)
                    if "error" in query:
                        description = query.get("error_description", query["error"])[0]
                        raise IBCInvalidAuth(description)
                    if "code" in query:
                        returned_state = query.get("state", [""])[0]
                        if returned_state != state:
                            raise IBCAuthenticationError(
                                "IBC OAuth state validation failed"
                            )
                        return await self._async_exchange_code(
                            token_endpoint,
                            query["code"][0],
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
                            current_url = str(response.url)
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

        raise IBCAuthUnsupported("IBC portal login could not be completed")

    async def _async_exchange_code(
        self,
        token_endpoint: str,
        code: str,
        verifier: str,
    ) -> dict[str, Any]:
        form = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": OAUTH_REDIRECT_URI,
            "code_verifier": verifier,
            "client_id": OAUTH_CLIENT_ID,
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
        if not data.get("access_token") or not data.get("refresh_token"):
            raise IBCInvalidAuth("IBC returned incomplete OAuth tokens")
        return _normalise_token(data)

    async def async_refresh(self, refresh_token: str) -> dict[str, Any]:
        """Refresh an IBC OAuth token using the portal's public client."""
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
        self._refresh_lock = asyncio.Lock()

    @property
    def token(self) -> dict[str, Any]:
        value = self._entry.data.get("token", {})
        return dict(value) if isinstance(value, dict) else {}

    async def async_access_token(self) -> str:
        """Return a valid access token, refreshing shortly before expiry."""
        token = self.token
        access_token = token.get("access_token")
        try:
            valid_until = float(token.get("expires_at") or 0)
        except (TypeError, ValueError):
            valid_until = 0
        if access_token and (valid_until == 0 or valid_until > time.time() + 90):
            return str(access_token)
        return await self.async_force_refresh()

    async def async_force_refresh(self) -> str:
        """Refresh now and persist a rotated refresh token atomically."""
        async with self._refresh_lock:
            token = self.token
            refresh_token = token.get("refresh_token")
            if not refresh_token:
                raise IBCInvalidAuth("IBC refresh token is missing")
            new_token = await self._auth.async_refresh(str(refresh_token))
            self._hass.config_entries.async_update_entry(
                self._entry,
                data={**self._entry.data, "token": new_token},
            )
            return str(new_token["access_token"])
