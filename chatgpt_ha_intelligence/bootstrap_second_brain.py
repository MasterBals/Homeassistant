from __future__ import annotations

import json
from pathlib import Path

from state_store import brain_get, brain_upsert, utcnow

MARKER = Path('/data/second_brain_bootstrap_2.5.3.done')

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
            'plus a terminator. After SetPairTaskConfigData succeeds, the Yealink flow calls UsbDev_SetApEnable '
            'for the current device.'
        ),
        'tags': ['vcm36w', 'pairing', 'wifimic', 'pair_config', 'ext_params', 'verified'],
        'metadata': {
            'report_endpoint': '/devctl/system/pair/wifimic-config/report',
            'pair_task_size': 1028,
            'pair_config_offset': 4,
            'ext_params_offset': 516,
            'pair_config_max_bytes': 511,
            'ext_params_max_bytes': 511,
            'ap_enable_after_set': True,
            'secrets_stored': False,
        },
    },
    {
        'topic': 'yealink',
        'key': 'vcm36w_live_usb_rc8_transport',
        'title': 'VCM36-W live USB/HID RC8 transport verified',
        'content': (
            'Live verification on the connected VCM36-W: USB VID/PID 6993:B06A in runtime mode, serial '
            '803143F030002094, interface 0, proprietary HID report 0xC8, interrupt OUT endpoint 0x06 and IN '
            'endpoint 0x85. The reusable libusb transport can temporarily detach usbhid, claim interface 0, '
            'perform RC8 exchanges and restore the kernel driver. Capability, Hello and diagnostic read paths '
            'have already worked over this transport. RC8 fragments use a four-byte HID fragment header followed '
            'by a 16-byte RC8 header encoded as <HHHHII>.'
        ),
        'tags': ['vcm36w', 'usb', 'hid', 'rc8', 'live-verified'],
        'metadata': {
            'vid': '0x6993',
            'pid': '0xB06A',
            'serial': '803143F030002094',
            'interface': 0,
            'report_id': '0xC8',
            'ep_out': '0x06',
            'ep_in': '0x85',
            'report_size': 1024,
            'single_fragment_payload_max': 1020,
            'rc8_header_bytes': 16,
            'secrets_stored': False,
        },
    },
    {
        'topic': 'yealink',
        'key': 'vcm36w_pair_write_transport',
        'title': 'VCM36-W verified RC8 PairTaskConfigData write path and fragmentation requirement',
        'content': (
            'Verified static analysis: the Linux/HID backend NS_USBCOM::Rc8IfLinux uses vtable slot +0x5EC '
            'for the PairTaskConfigData write. The wrapper at 0x109467E0 sends the complete 0x404-byte payload '
            'through MsgSet using command 0x0246. The same slot on Rc8IfMcu is not the supported pairing path. '
            'A critical implementation detail is now verified from the live Python transport: one 0xC8 HID '
            'report carries at most 1020 bytes after its four-byte fragment header. An RC8 request containing '
            'the 16-byte RC8 header plus the 0x404-byte PairTaskConfigData totals 1044 bytes, so the real MsgSet '
            'path must fragment the request across multiple HID reports. The current generic exchange() helper '
            'only builds a single fragment and therefore must not be used for the pairing write until matching '
            'multi-fragment MsgSet framing is implemented and verified.'
        ),
        'tags': ['vcm36w', 'rc8', 'hid', 'pairing', 'write-path', 'fragmentation', 'verified'],
        'metadata': {
            'backend': 'NS_USBCOM::Rc8IfLinux',
            'vtable_offset': '0x5EC',
            'wrapper': '0x109467E0',
            'command': '0x0246',
            'pair_payload_bytes': 1028,
            'rc8_request_bytes_before_hid_fragment_header': 1044,
            'single_fragment_payload_max': 1020,
            'requires_multifragment_msgset': True,
            'generic_exchange_safe_for_pairing': False,
            'secrets_stored': False,
        },
    },
    {
        'topic': 'yealink',
        'key': 'vcm36w_pairing_preflight_state',
        'title': 'VCM36-W pairing preflight has no sendable pair_config/ext_params yet',
        'content': (
            'Live preflight result: the verified report-layout artifact contains pair_config and ext_params only '
            'as analysed field descriptions, not as the real non-empty strings/bytes required by the device. '
            'The static-check artifact also contains no directly usable values. The preflight therefore produced '
            'no .vcm36w_pair_payload.bin and reported usable=false. No pairing write has been performed. Valid '
            'pair_config and ext_params must be obtained from the real Yealink report flow or reconstructed from '
            'fully verified Yealink semantics; they must not be invented from SSID/password assumptions.'
        ),
        'tags': ['vcm36w', 'pairing', 'preflight', 'pair_config', 'ext_params', 'live-verified'],
        'metadata': {
            'preflight_usable': False,
            'payload_written': False,
            'pairing_write_performed': False,
            'reason': 'no directly usable non-empty pair_config/ext_params values in verified artifacts',
            'secrets_stored': False,
        },
    },
    {
        'topic': 'yealink',
        'key': 'vcm36w_pairing_write_safety_state',
        'title': 'VCM36-W pairing write safety state before first controlled write',
        'content': (
            'Current verified safety state: USB RC8 transport and the Linux/HID 0x0246 PairTaskConfigData write '
            'path are mapped, but the first controlled write is not ready yet. Two prerequisites remain: obtain '
            'authentic pair_config/ext_params data and implement/verify MsgSet-compatible multi-fragment HID '
            'transmission for the 1044-byte RC8 request. Once both are satisfied, perform exactly one controlled '
            '0x0246 write with no automatic retry, then verify the acknowledgement, AP transition and wireless '
            'pairing state. WLAN SSID/passphrase remain add-on options and must never be copied into Second Brain.'
        ),
        'tags': ['vcm36w', 'pairing', 'safety', 'next-step', 'verified'],
        'metadata': {
            'protocol_write_ready': False,
            'pair_config_ready': False,
            'multifragment_write_ready': False,
            'automatic_retry_allowed': False,
            'secrets_stored': False,
        },
    },
    {
        'topic': 'yealink',
        'key': 'vcm36w_next_steps',
        'title': 'VCM36-W next steps toward first controlled pairing write',
        'content': (
            'Current next step after protocol corrections: do not use direct GetInfo 0x0231 because its grant '
            'bit is false. Continue on the verified WiFiMic MAC request/report architecture. Capture or derive '
            'the authentic pair_config and ext_params returned by /devctl/system/pair/wifimic-config/report, '
            'implement the exact MsgSet multi-fragment framing needed for RC8 0x0246 with the 0x404-byte '
            'PairTaskConfigData, validate that framing with non-destructive traffic if possible, then execute '
            'one controlled Linux/HID write and inspect ACK/AP/wireless state. Never persist WLAN credentials '
            'or pairing secrets in Second Brain.'
        ),
        'tags': ['vcm36w', 'next-step', 'pairing', 'rc8', 'verified'],
        'metadata': {
            'supersedes_stale_0x0231_step': True,
            'pairing_write_performed': False,
            'secrets_stored': False,
        },
    },
]


def main() -> None:
    if MARKER.exists():
        return

    results = []
    for entry in VERIFIED_ENTRIES:
        results.append(brain_upsert(
            topic=entry['topic'],
            key=entry['key'],
            title=entry['title'],
            content=entry['content'],
            tags=entry['tags'],
            source='bootstrap_2.5.3',
            confidence='verified',
            metadata={**entry['metadata'], 'backfilled_from_verified_analysis': True},
            change_reason='Synchronize latest verified VCM36-W pairing analysis into the MCP Second Brain.',
        ))

    MARKER.write_text(json.dumps({
        'completed_at': utcnow(),
        'results': results,
        'note': 'One-time 2.5.3 verified Yealink pairing knowledge sync; future changes should use second_brain_upsert with stable topic/key.',
    }, indent=2, ensure_ascii=False))
    MARKER.chmod(0o600)


if __name__ == '__main__':
    main()
