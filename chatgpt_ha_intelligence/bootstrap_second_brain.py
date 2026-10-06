from __future__ import annotations

import json
from pathlib import Path

from state_store import brain_get, brain_upsert, utcnow

MARKER = Path('/data/second_brain_bootstrap_2.5.0.done')

VERIFIED_ENTRIES = [
    {
        'topic': 'yealink',
        'key': 'vcm36w_pair_request_mac_only',
        'title': 'VCM36-W WiFiMic pairing request carries microphone MAC only',
        'content': (
            'Verified static analysis: /devctl/system/pair/wifimic-config/request does not take eight semantic '
            'pairing fields. The apparent eight 32-bit stack values represent one 24-byte std::string plus two '
            'output handles. The string is produced by transSetMicMacToString and contains JSON with the key '
            'mac and the VCM36-W MAC address. pair_config and ext_params are not request arguments; they arrive '
            'later in the asynchronous report.'
        ),
        'tags': ['vcm36w', 'pairing', 'wifimic', 'ucp', 'verified'],
        'metadata': {
            'request_endpoint': '/devctl/system/pair/wifimic-config/request',
            'request_builder': '0x108EFA50',
            'transport_helper': '0x108E6580',
            'secrets_stored': False,
        },
    },
    {
        'topic': 'yealink',
        'key': 'vcm36w_pair_report_layout',
        'title': 'VCM36-W WiFiMic report and PairTaskConfigData layout',
        'content': (
            'Verified static analysis: /devctl/system/pair/wifimic-config/report returns strings mac, pair_config '
            'and ext_params. The MAC is checked against the current UsbDevInfo MAC. PairTaskConfigData is exactly '
            '0x404 bytes: offset 0x000 is a four-byte header/status observed as zero in this path; offset 0x004 is '
            'pair_config[0x200]; offset 0x204 is ext_params[0x200]. Each text payload is bounded to 0x1FF bytes '
            'plus a terminator.'
        ),
        'tags': ['vcm36w', 'pairing', 'wifimic', 'pair_config', 'ext_params', 'verified'],
        'metadata': {
            'report_endpoint': '/devctl/system/pair/wifimic-config/report',
            'pair_task_size': 1028,
            'pair_config_offset': 4,
            'ext_params_offset': 516,
            'secrets_stored': False,
        },
    },
    {
        'topic': 'yealink',
        'key': 'vcm36w_pair_write_transport',
        'title': 'VCM36-W verified RC8 PairTaskConfigData write path',
        'content': (
            'Verified static analysis: the Linux/HID backend NS_USBCOM::Rc8IfLinux uses vtable slot +0x5EC '
            'for the PairTaskConfigData write. The wrapper at 0x109467E0 sends the complete 0x404-byte payload '
            'through MsgSet using command family 0x0246 and waits for acknowledgement with the caller-provided '
            '1000 ms timeout. MsgSet requires the complete 0x404-byte transfer before receiving the response. '
            'The same slot on Rc8IfMcu is not supported, so the first controlled write must target the Linux/HID '
            'path only and must not invent pair_config/ext_params contents.'
        ),
        'tags': ['vcm36w', 'rc8', 'hid', 'pairing', 'write-path', 'verified'],
        'metadata': {
            'backend': 'NS_USBCOM::Rc8IfLinux',
            'vtable_offset': '0x5EC',
            'wrapper': '0x109467E0',
            'command': '0x0246',
            'payload_bytes': 1028,
            'timeout_ms': 1000,
            'secrets_stored': False,
        },
    },
    {
        'topic': 'yealink',
        'key': 'vcm36w_pairing_write_safety_state',
        'title': 'VCM36-W pairing write safety state before first write',
        'content': (
            'Current verified safety state: USB RC8 transport and the 0x0246/0x404-byte PairTaskConfigData '
            'write path are mapped, but arbitrary pairing data must not be sent. A controlled write is only '
            'appropriate once a valid pair_config/ext_params payload has been derived from verified Yealink '
            'semantics or captured from the real report flow. WLAN SSID/passphrase are stored separately in '
            'add-on options and must never be copied into Second Brain entries.'
        ),
        'tags': ['vcm36w', 'pairing', 'safety', 'verified'],
        'metadata': {'protocol_write_ready': False, 'secrets_stored': False},
    },
]


def main() -> None:
    if MARKER.exists():
        return

    results = []
    for entry in VERIFIED_ENTRIES:
        existing = brain_get(entry['topic'], entry['key'], include_history=False)
        if existing is None:
            results.append(brain_upsert(
                topic=entry['topic'],
                key=entry['key'],
                title=entry['title'],
                content=entry['content'],
                tags=entry['tags'],
                source='bootstrap_2.5.0',
                confidence='verified',
                metadata={**entry['metadata'], 'backfilled_from_verified_analysis': True},
                change_reason='Backfill of verified VCM36-W analysis after Second Brain write tools were unavailable.',
            ))

    stale = brain_get('yealink', 'vcm36w_next_steps', include_history=False)
    if stale and '0x0231' in str(stale.get('content', '')):
        results.append(brain_upsert(
            topic='yealink',
            key='vcm36w_next_steps',
            title='VCM36-W current next step after protocol corrections',
            content=(
                'Correction: direct GetInfo 0x0231 must not be sent because its grant bit is false. The pairing '
                'investigation has advanced beyond that stale step. Current path: use the verified WiFiMic MAC '
                'request/report architecture, obtain or construct valid pair_config/ext_params, then perform one '
                'controlled Linux/HID RC8 0x0246 write of the complete 0x404-byte PairTaskConfigData with no '
                'automatic retries. Do not store WLAN secrets in Second Brain.'
            ),
            tags=['vcm36w', 'next-step', 'pairing', 'correction'],
            source='bootstrap_2.5.0',
            confidence='verified',
            metadata={'supersedes_stale_0x0231_step': True, 'secrets_stored': False},
            change_reason='Earlier next-step note became invalid after grant-bit and pairing-path analysis.',
        ))

    MARKER.write_text(json.dumps({
        'completed_at': utcnow(),
        'results': results,
        'note': 'One-time 2.5.0 backfill; future changes must use second_brain_upsert with the same stable topic/key.',
    }, indent=2, ensure_ascii=False))
    MARKER.chmod(0o600)


if __name__ == '__main__':
    main()
