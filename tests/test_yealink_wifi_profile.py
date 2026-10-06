from __future__ import annotations

import pytest

from ha_intelligence_bridge.app.yealink_wifi_profile import (
    get_target_wifi_credentials,
    target_wifi_status,
)


def test_target_wifi_status_redacts_secret() -> None:
    options = {
        'yealink_target_wifi_ssid': 'Office-WLAN',
        'yealink_target_wifi_passphrase': 'supersecret123',
    }

    status = target_wifi_status(options)

    assert status['ok'] is True
    assert status['ssid'] == 'Office-WLAN'
    assert status['secret_configured'] is True
    assert status['ready_for_protocol_use'] is True
    assert status['secret_redacted'] is True
    assert 'passphrase' not in status
    assert 'supersecret123' not in repr(status)


def test_incomplete_profile_is_not_ready() -> None:
    status = target_wifi_status({'yealink_target_wifi_ssid': 'Office-WLAN'})

    assert status['ok'] is True
    assert status['ssid_configured'] is True
    assert status['secret_configured'] is False
    assert status['ready_for_protocol_use'] is False


def test_internal_resolver_requires_complete_profile() -> None:
    with pytest.raises(ValueError):
        get_target_wifi_credentials({'yealink_target_wifi_ssid': 'Office-WLAN'})


def test_internal_resolver_accepts_64_hex_psk() -> None:
    psk = 'a' * 64
    profile = get_target_wifi_credentials({
        'yealink_target_wifi_ssid': 'Office-WLAN',
        'yealink_target_wifi_passphrase': psk,
    })

    assert profile['ssid'] == 'Office-WLAN'
    assert profile['passphrase'] == psk
    assert profile['security'] == 'WPA2-PSK'
