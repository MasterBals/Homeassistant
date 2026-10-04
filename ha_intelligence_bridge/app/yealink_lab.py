from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import re
import shutil
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

ROOT = Path('/data/yealink_lab')
STATE = ROOT / 'state.json'
HOSTAPD = ROOT / 'hostapd.conf'
DNSMASQ = ROOT / 'dnsmasq.conf'
HOSTAPD_PID = ROOT / 'hostapd.pid'
DNSMASQ_PID = ROOT / 'dnsmasq.pid'
HOSTAPD_LOG = ROOT / 'hostapd.log'
CAPTURES = ROOT / 'captures'
YEALINK_VID = '1b51'
KNOWN_PIDS = {'b06a': 'VCM36-W runtime', 'b068': 'VCM36-W upgrade'}
IFACE_RE = re.compile(r'^[A-Za-z0-9_.:-]{1,32}$')


def _run(args: list[str], check: bool = True, timeout: int = 20) -> subprocess.CompletedProcess[str]:
    p = subprocess.run(args, text=True, capture_output=True, timeout=timeout, check=False)
    if check and p.returncode:
        raise RuntimeError((p.stderr or p.stdout or f'command failed: {args}')[-2000:])
    return p


def _bool(options: dict[str, Any], key: str, default: bool = False) -> bool:
    value = options.get(key, default)
    return value if isinstance(value, bool) else str(value).lower() in {'1', 'true', 'yes', 'on'}


def _iface(options: dict[str, Any], override: str = '') -> str:
    name = (override or str(options.get('yealink_wifi_interface', 'wlan0'))).strip()
    if not IFACE_RE.fullmatch(name) or not Path('/sys/class/net', name).exists():
        raise ValueError(f'Invalid or missing network interface: {name}')
    return name


def _load_state() -> dict[str, Any]:
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return {}


def _save_state(data: dict[str, Any]) -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix('.new')
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
    os.chmod(tmp, 0o600)
    tmp.replace(STATE)


def _usb_devices() -> list[dict[str, Any]]:
    if not shutil.which('lsusb'):
        return []
    out = []
    rx = re.compile(r'^Bus\s+(\d+)\s+Device\s+(\d+):\s+ID\s+([0-9A-Fa-f]{4}):([0-9A-Fa-f]{4})\s*(.*)$')
    for line in _run(['lsusb'], check=False).stdout.splitlines():
        m = rx.match(line.strip())
        if not m:
            continue
        bus, dev, vid, pid, label = m.groups()
        if vid.lower() != YEALINK_VID:
            continue
        out.append({'bus': bus, 'device': dev, 'vid': vid.lower(), 'pid': pid.lower(),
                    'known_product': KNOWN_PIDS.get(pid.lower()), 'label': label.strip(),
                    'device_path': f'/dev/bus/usb/{bus}/{dev}'})
    return out


def _wireless() -> dict[str, Any]:
    tools = {n: bool(shutil.which(n)) for n in ('ip', 'iw', 'hostapd', 'dnsmasq', 'lsusb', 'tcpdump')}
    iw_dev = _run(['iw', 'dev'], check=False).stdout if tools['iw'] else ''
    iw_list = _run(['iw', 'list'], check=False).stdout if tools['iw'] else ''
    return {'tools': tools, 'iw_dev': iw_dev[-6000:], 'ap_mode_supported': '* AP' in iw_list}


def _settings(options: dict[str, Any], interface: str = '', ssid: str = '', channel: int = 0,
              require_secret: bool = True) -> dict[str, Any]:
    iface = _iface(options, interface)
    ssid_value = (ssid or str(options.get('yealink_ap_ssid', 'Yealink-Lab'))).strip()
    if not ssid_value or len(ssid_value.encode()) > 32 or '\n' in ssid_value or '\r' in ssid_value:
        raise ValueError('SSID must contain 1-32 bytes and no line breaks')
    secret = str(options.get('yealink_ap_passphrase', '')).strip()
    if secret and not 8 <= len(secret) <= 63:
        raise ValueError('yealink_ap_passphrase must contain 8-63 characters')
    if require_secret and not secret:
        raise ValueError('Configure yealink_ap_passphrase (8-63 characters) before starting the AP')
    country = str(options.get('yealink_ap_country', 'CH')).upper().strip()
    if not re.fullmatch(r'[A-Z]{2}', country):
        raise ValueError('yealink_ap_country must be a two-letter ISO code')
    ch = int(channel or options.get('yealink_ap_channel', 6))
    if ch < 1 or ch > 165:
        raise ValueError('Wi-Fi channel must be 1-165')
    addr = ipaddress.ip_interface(str(options.get('yealink_ap_address', '192.168.187.1/24')))
    if addr.version != 4 or not addr.ip.is_private or addr.network.prefixlen > 29:
        raise ValueError('yealink_ap_address must be a private IPv4 subnet large enough for DHCP')
    start = ipaddress.ip_address(str(options.get('yealink_ap_dhcp_start', '192.168.187.20')))
    end = ipaddress.ip_address(str(options.get('yealink_ap_dhcp_end', '192.168.187.80')))
    if start not in addr.network or end not in addr.network or int(start) > int(end):
        raise ValueError('DHCP range must be ordered and inside the AP subnet')
    return {'interface': iface, 'ssid': ssid_value, 'secret': secret, 'country': country,
            'channel': ch, 'address': str(addr), 'network': str(addr.network),
            'dhcp_start': str(start), 'dhcp_end': str(end), 'netmask': str(addr.network.netmask),
            'gateway': str(addr.ip)}


def _global_addresses(iface: str) -> list[str]:
    try:
        rows = json.loads(_run(['ip', '-j', 'addr', 'show', 'dev', iface], check=False).stdout or '[]')
    except Exception:
        return []
    return [f"{a['local']}/{a.get('prefixlen')}" for r in rows for a in r.get('addr_info', [])
            if a.get('scope') == 'global' and a.get('local')]


def _overlaps(network: str) -> list[str]:
    wanted = ipaddress.ip_network(network)
    try:
        routes = json.loads(_run(['ip', '-j', 'route', 'show'], check=False).stdout or '[]')
    except Exception:
        return []
    result = []
    for route in routes:
        dst = route.get('dst')
        if not dst or dst == 'default':
            continue
        try:
            net = ipaddress.ip_network(dst, strict=False)
        except ValueError:
            continue
        if net.overlaps(wanted):
            result.append(str(net))
    return result


def _pid_ours(path: Path, needle: str) -> int:
    try:
        pid = int(path.read_text().strip())
        cmd = Path(f'/proc/{pid}/cmdline').read_bytes().replace(b'\x00', b' ').decode(errors='replace')
        return pid if needle in cmd and str(ROOT) in cmd else 0
    except Exception:
        return 0


def _stop_process(path: Path, needle: str) -> None:
    pid = _pid_ours(path, needle)
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    path.unlink(missing_ok=True)


def ap_stop(options: dict[str, Any]) -> dict[str, Any]:
    state = _load_state()
    _stop_process(DNSMASQ_PID, 'dnsmasq')
    _stop_process(HOSTAPD_PID, 'hostapd')
    iface, addr = state.get('interface'), state.get('address')
    if iface and IFACE_RE.fullmatch(str(iface)) and Path('/sys/class/net', str(iface)).exists():
        if addr:
            _run(['ip', 'addr', 'del', str(addr), 'dev', str(iface)], check=False)
        if state.get('owns_interface'):
            _run(['ip', 'link', 'set', 'dev', str(iface), 'down'], check=False)
    state.update(status='stopped', stopped_at=int(time.time()))
    _save_state(state)
    return {'ok': True, 'state': state}


def ap_start(options: dict[str, Any], interface: str = '', ssid: str = '', channel: int = 0) -> dict[str, Any]:
    if not _bool(options, 'yealink_lab_enabled', True):
        raise RuntimeError('Yealink lab is disabled')
    if not _bool(options, 'yealink_ap_write_enabled', False):
        raise RuntimeError('AP writes are locked; enable yealink_ap_write_enabled first')
    w = _wireless()
    missing = [x for x in ('ip', 'iw', 'hostapd', 'dnsmasq') if not w['tools'][x]]
    if missing:
        raise RuntimeError(f'Missing AP tools: {missing}')
    if not w['ap_mode_supported']:
        raise RuntimeError('The Wi-Fi driver does not advertise nl80211 AP mode')
    s = _settings(options, interface, ssid, channel)
    if _load_state().get('status') == 'running':
        raise RuntimeError('Yealink lab AP is already running')
    if _global_addresses(s['interface']):
        raise RuntimeError(f"Refusing to take over active interface {s['interface']}")
    overlaps = _overlaps(s['network'])
    if overlaps:
        raise RuntimeError(f"AP subnet {s['network']} overlaps existing routes: {overlaps}")

    ROOT.mkdir(parents=True, exist_ok=True)
    hostapd = '\n'.join([
        f"interface={s['interface']}", 'driver=nl80211', f"ssid={s['ssid']}",
        f"country_code={s['country']}", 'ieee80211d=1', f"hw_mode={'g' if s['channel'] <= 14 else 'a'}",
        f"channel={s['channel']}", 'wmm_enabled=1', 'auth_algs=1', 'wpa=2',
        'wpa_key_mgmt=WPA-PSK', 'rsn_pairwise=CCMP', f"wpa_passphrase={s['secret']}", ''])
    dnsmasq = '\n'.join([
        f"interface={s['interface']}", 'bind-interfaces', 'port=0', 'dhcp-authoritative',
        f"dhcp-range={s['dhcp_start']},{s['dhcp_end']},{s['netmask']},12h",
        f"dhcp-option=3,{s['gateway']}", f"dhcp-option=6,{s['gateway']}", ''])
    HOSTAPD.write_text(hostapd); DNSMASQ.write_text(dnsmasq); HOSTAPD_LOG.write_text('')
    os.chmod(HOSTAPD, 0o600); os.chmod(DNSMASQ, 0o600)
    state = {'status': 'starting', 'interface': s['interface'], 'ssid': s['ssid'], 'country': s['country'],
             'channel': s['channel'], 'address': s['address'], 'network': s['network'],
             'security': 'WPA2-PSK/CCMP', 'owns_interface': True, 'internet_forwarding': False,
             'started_at': int(time.time())}
    _save_state(state)
    try:
        _run(['ip', 'link', 'set', 'dev', s['interface'], 'down'])
        _run(['ip', 'addr', 'add', s['address'], 'dev', s['interface']])
        _run(['ip', 'link', 'set', 'dev', s['interface'], 'up'])
        _run(['hostapd', '-B', '-P', str(HOSTAPD_PID), '-f', str(HOSTAPD_LOG), str(HOSTAPD)])
        _run(['dnsmasq', f'--conf-file={DNSMASQ}', f'--pid-file={DNSMASQ_PID}'])
        time.sleep(1)
        if not _pid_ours(HOSTAPD_PID, 'hostapd') or not _pid_ours(DNSMASQ_PID, 'dnsmasq'):
            raise RuntimeError('hostapd or dnsmasq did not remain running')
    except Exception:
        ap_stop(options)
        raise
    state.update(status='running', hostapd_pid=_pid_ours(HOSTAPD_PID, 'hostapd'),
                 dnsmasq_pid=_pid_ours(DNSMASQ_PID, 'dnsmasq'))
    _save_state(state)
    return {'ok': True, 'state': state, 'passphrase_redacted': True}


def capture(options: dict[str, Any], seconds: int = 20, interface: str = '') -> dict[str, Any]:
    if not shutil.which('tcpdump'):
        raise RuntimeError('tcpdump is not installed')
    iface = _iface(options, interface)
    duration = min(max(int(seconds), 5), 120)
    CAPTURES.mkdir(parents=True, exist_ok=True)
    path = CAPTURES / f"yealink_{iface}_{time.strftime('%Y%m%d_%H%M%S')}.pcap"
    p = subprocess.Popen(['tcpdump', '-i', iface, '-U', '-s', '0', '-w', str(path)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    try:
        time.sleep(duration)
    finally:
        p.send_signal(signal.SIGINT)
    _, err = p.communicate(timeout=10)
    return {'ok': path.exists(), 'interface': iface, 'seconds': duration, 'path': str(path),
            'size_bytes': path.stat().st_size if path.exists() else 0, 'tcpdump_tail': (err or '')[-1200:]}


def register_yealink_tools(mcp: Any, options: dict[str, Any]) -> None:
    @mcp.tool()
    async def yealink_lab_status() -> dict[str, Any]:
        """Read-only readiness for VCM36-W USB and the isolated Yealink AP lab."""
        w = await asyncio.to_thread(_wireless)
        try:
            iface = _iface(options)
            addresses = await asyncio.to_thread(_global_addresses, iface)
        except Exception as exc:
            iface, addresses = str(options.get('yealink_wifi_interface', 'wlan0')), []
            w['interface_error'] = str(exc)
        return {'version': '1.0', 'enabled': _bool(options, 'yealink_lab_enabled', True),
                'ap_write_enabled': _bool(options, 'yealink_ap_write_enabled', False),
                'protocol_write_enabled': _bool(options, 'yealink_protocol_write_enabled', False),
                'pairing_write_tools_implemented': False, 'configured_interface': iface,
                'configured_interface_addresses': addresses, 'raw_usb_mapped': Path('/dev/bus/usb').exists(),
                'yealink_usb_devices': await asyncio.to_thread(_usb_devices), 'wireless': w,
                'state': _load_state(), 'internet_forwarding': False}

    @mcp.tool()
    async def yealink_usb_inventory() -> dict[str, Any]:
        """Read-only inventory of Yealink USB devices visible to the add-on."""
        return {'expected_vid': YEALINK_VID, 'known_products': KNOWN_PIDS,
                'devices': await asyncio.to_thread(_usb_devices)}

    @mcp.tool()
    async def yealink_ap_preview(interface: str = '', ssid: str = '', channel: int = 0) -> dict[str, Any]:
        """Validate AP parameters without changing the Wi-Fi interface."""
        s = await asyncio.to_thread(_settings, options, interface, ssid, channel, False)
        return {'interface': s['interface'], 'ssid': s['ssid'], 'country': s['country'],
                'channel': s['channel'], 'address': s['address'], 'network': s['network'],
                'dhcp_range': [s['dhcp_start'], s['dhcp_end']], 'security': 'WPA2-PSK/CCMP',
                'passphrase_configured': bool(s['secret']), 'internet_forwarding': False,
                'note': 'Transport/AP emulation only; Yealink pairing metadata and bind identity are not yet reproduced.'}

    @mcp.tool()
    async def yealink_ap_start(interface: str = '', ssid: str = '', channel: int = 0) -> dict[str, Any]:
        """Start the isolated AP. Requires yealink_ap_write_enabled=true; sends no RC8/pairing writes."""
        return await asyncio.to_thread(ap_start, options, interface, ssid, channel)

    @mcp.tool()
    async def yealink_ap_stop() -> dict[str, Any]:
        """Stop only the AP processes/address owned by the Yealink lab."""
        return await asyncio.to_thread(ap_stop, options)

    @mcp.tool()
    async def yealink_packet_capture(seconds: int = 20, interface: str = '') -> dict[str, Any]:
        """Passive packet capture on the lab interface; no packets are injected."""
        return await asyncio.to_thread(capture, options, seconds, interface)
