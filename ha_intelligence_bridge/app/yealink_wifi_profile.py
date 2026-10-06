from __future__ import annotations

import re
from typing import Any


SSID_MAX_BYTES = 32


def get_target_wifi_credentials(options: dict[str, Any], *, require_complete: bool = True) -> dict[str, str]:
    """Resolve the VCM36-W target WLAN profile from add-on options.

    This helper is intended for internal protocol/write tools. It deliberately
    keeps the passphrase out of public MCP status payloads and logs.
    """
    ssid = str(options.get('yealink_target_wifi_ssid', '')).strip()
    passphrase = str(options.get('yealink_target_wifi_passphrase', ''))

    if ssid:
        if '\n' in ssid or '\r' in ssid or len(ssid.encode('utf-8')) > SSID_MAX_BYTES:
            raise ValueError('yealink_target_wifi_ssid must contain 1-32 UTF-8 bytes and no line breaks')

    if passphrase:
        if '\n' in passphrase or '\r' in passphrase:
            raise ValueError('yealink_target_wifi_passphrase must not contain line breaks')
        is_passphrase = 8 <= len(passphrase) <= 63
        is_raw_psk = bool(re.fullmatch(r'[0-9A-Fa-f]{64}', passphrase))
        if not (is_passphrase or is_raw_psk):
            raise ValueError('yealink_target_wifi_passphrase must contain 8-63 characters or a 64-digit hexadecimal PSK')

    if require_complete and (not ssid or not passphrase):
        raise ValueError('Configure yealink_target_wifi_ssid and yealink_target_wifi_passphrase first')

    return {
        'ssid': ssid,
        'passphrase': passphrase,
        'security': 'WPA2-PSK',
    }


def target_wifi_status(options: dict[str, Any]) -> dict[str, Any]:
    try:
        profile = get_target_wifi_credentials(options, require_complete=False)
        ssid = profile['ssid']
        secret_configured = bool(profile['passphrase'])
        return {
            'ok': True,
            'ssid': ssid,
            'ssid_configured': bool(ssid),
            'secret_configured': secret_configured,
            'ready_for_protocol_use': bool(ssid) and secret_configured,
            'security': profile['security'],
            'secret_redacted': True,
            'source': '/data/options.json',
        }
    except Exception as exc:
        return {
            'ok': False,
            'ssid': str(options.get('yealink_target_wifi_ssid', '')).strip(),
            'ssid_configured': bool(str(options.get('yealink_target_wifi_ssid', '')).strip()),
            'secret_configured': bool(str(options.get('yealink_target_wifi_passphrase', ''))),
            'ready_for_protocol_use': False,
            'security': 'WPA2-PSK',
            'secret_redacted': True,
            'source': '/data/options.json',
            'error': str(exc),
        }


def register_target_wifi_tools(mcp: Any, options: dict[str, Any]) -> None:
    @mcp.tool()
    async def yealink_wifi_profile_status() -> dict[str, Any]:
        """Show the stored VCM36-W target WLAN profile without exposing its passphrase."""
        return target_wifi_status(options)
