from __future__ import annotations

import hashlib
import json
import os
import selectors
import signal
import time
from pathlib import Path
from typing import Any

try:
    import usb.core
    import usb.util
except Exception as exc:  # pragma: no cover - runtime diagnostic
    usb = None
    USB_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"
else:
    USB_IMPORT_ERROR = None

VID_HEX = "6993"
VID_INT = 0x6993
PIDS = {
    0xB06A: "VCM36-W runtime",
    0xB068: "VCM36-W upgrade",
}
SYSFS = Path("/sys/bus/usb/devices")
OUT = Path("/homeassistant/yealink_vcm36w_usb_probe.json")
INTERVAL = 5
PASSIVE_CAPTURE_SECONDS = 4.0
PASSIVE_MAX_FRAMES = 64
RUNNING = True
RECENT_FRAMES: dict[str, dict[str, Any]] = {}


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(errors="replace").strip()
    except (OSError, UnicodeError):
        return None


def _read_bytes(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except OSError:
        return None


def _to_int(value: str | None, base: int = 10) -> int | None:
    if value is None:
        return None
    try:
        return int(value, base)
    except (TypeError, ValueError):
        return None


def _hid_report_descriptor(hidraw_name: str) -> bytes | None:
    root = Path("/sys/class/hidraw") / hidraw_name / "device"
    candidates = [root / "report_descriptor"]
    try:
        resolved = root.resolve()
        candidates.extend([resolved / "report_descriptor", resolved.parent / "report_descriptor"])
    except OSError:
        pass
    for candidate in candidates:
        data = _read_bytes(candidate)
        if data is not None:
            return data
    return None


def _report_ids(desc: bytes) -> list[int]:
    """Extract HID Report IDs from a report descriptor without interpreting usage data."""
    ids: list[int] = []
    i = 0
    while i < len(desc):
        prefix = desc[i]
        i += 1
        if prefix == 0xFE:
            if i + 1 >= len(desc):
                break
            size = desc[i]
            i += 2 + size
            continue
        size_code = prefix & 0x03
        size = 4 if size_code == 3 else size_code
        item_type = (prefix >> 2) & 0x03
        tag = (prefix >> 4) & 0x0F
        if i + size > len(desc):
            break
        payload = desc[i : i + size]
        i += size
        if item_type == 1 and tag == 8 and payload:
            rid = int.from_bytes(payload, "little")
            if rid not in ids:
                ids.append(rid)
    return ids


def _hidraw_for(device_dir: Path) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for interface in sorted(device_dir.parent.glob(f"{device_dir.name}:*")):
        if (_read_text(interface / "bInterfaceClass") or "").lower() != "03":
            continue
        interface_number = _to_int(_read_text(interface / "bInterfaceNumber"), 16)
        for path in sorted(interface.rglob("hidraw*")):
            if not path.name.startswith("hidraw") or not path.name[6:].isdigit():
                continue
            dev_path = str(Path("/dev") / path.name)
            if dev_path in seen:
                continue
            seen.add(dev_path)
            report_descriptor = _hid_report_descriptor(path.name)
            result.append(
                {
                    "hidraw": dev_path,
                    "interface_number": interface_number,
                    "report_descriptor_size": len(report_descriptor) if report_descriptor is not None else None,
                    "report_descriptor_hex": report_descriptor.hex() if report_descriptor is not None else None,
                    "report_ids": _report_ids(report_descriptor or b""),
                }
            )
    return result


def _interfaces(device_dir: Path) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for interface in sorted(device_dir.parent.glob(f"{device_dir.name}:*")):
        eps: list[dict[str, Any]] = []
        for ep in sorted(interface.glob("ep_*")):
            eps.append(
                {
                    "name": ep.name,
                    "address": _read_text(ep / "bEndpointAddress"),
                    "attributes": _read_text(ep / "bmAttributes"),
                    "max_packet_size": _read_text(ep / "wMaxPacketSize"),
                    "interval": _read_text(ep / "bInterval"),
                }
            )
        driver = None
        try:
            if (interface / "driver").exists():
                driver = (interface / "driver").resolve().name
        except OSError:
            pass
        result.append(
            {
                "sysfs": interface.name,
                "number": _read_text(interface / "bInterfaceNumber"),
                "class": _read_text(interface / "bInterfaceClass"),
                "subclass": _read_text(interface / "bInterfaceSubClass"),
                "protocol": _read_text(interface / "bInterfaceProtocol"),
                "driver": driver,
                "endpoints": eps,
            }
        )
    return result


def _get_report(dev: Any, interface_number: int, report_type: int, report_id: int) -> dict[str, Any]:
    """Issue the read-only HID GET_REPORT class request.

    report_type: 1 = input, 3 = feature. No SET_REPORT request is ever sent here.
    """
    try:
        data = dev.ctrl_transfer(
            0xA1,
            0x01,
            ((report_type & 0xFF) << 8) | (report_id & 0xFF),
            interface_number,
            512,
            timeout=400,
        )
        raw = bytes(data)
        return {"ok": True, "length": len(raw), "hex": raw.hex()}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:300]}"}


def _feature_reports(bus: int | None, address: int | None, hidraw: list[dict[str, Any]]) -> dict[str, Any]:
    if USB_IMPORT_ERROR:
        return {"available": False, "error": USB_IMPORT_ERROR, "interfaces": []}
    if bus is None or address is None:
        return {"available": False, "error": "USB bus/address unavailable", "interfaces": []}
    try:
        dev = usb.core.find(bus=bus, address=address)
    except Exception as exc:
        return {"available": False, "error": f"USB lookup failed: {type(exc).__name__}: {exc}", "interfaces": []}
    if dev is None:
        return {"available": False, "error": "PyUSB could not find the enumerated device", "interfaces": []}

    output: list[dict[str, Any]] = []
    for info in hidraw:
        iface = info.get("interface_number")
        if not isinstance(iface, int):
            continue
        ids = info.get("report_ids") or [0]
        rows: list[dict[str, Any]] = []
        for rid in ids:
            rows.append(
                {
                    "report_id": int(rid),
                    "feature": _get_report(dev, iface, 3, int(rid)),
                    "input": _get_report(dev, iface, 1, int(rid)),
                }
            )
        output.append({"interface_number": iface, "hidraw": info.get("hidraw"), "reports": rows})
    return {"available": True, "interfaces": output}


def _remember_frame(path: str, raw: bytes) -> None:
    digest = hashlib.sha256(raw).hexdigest()[:16]
    key = f"{path}:{digest}"
    now = int(time.time())
    existing = RECENT_FRAMES.get(key)
    if existing:
        existing["last_seen"] = now
        existing["count"] = int(existing.get("count", 1)) + 1
        return
    RECENT_FRAMES[key] = {
        "hidraw": path,
        "sha256_16": digest,
        "first_seen": now,
        "last_seen": now,
        "count": 1,
        "length": len(raw),
        "report_id": raw[0] if raw else None,
        "hex": raw.hex(),
    }
    while len(RECENT_FRAMES) > PASSIVE_MAX_FRAMES:
        oldest = min(RECENT_FRAMES, key=lambda item: int(RECENT_FRAMES[item].get("last_seen", 0)))
        RECENT_FRAMES.pop(oldest, None)


def _vendor_hidraw_paths(devices: list[dict[str, Any]]) -> list[str]:
    paths: list[str] = []
    for device in devices:
        for info in device.get("hid") or []:
            path = str(info.get("hidraw") or "")
            report_ids = [int(x) for x in (info.get("report_ids") or [])]
            if path and 0xC8 in report_ids and Path(path).exists() and path not in paths:
                paths.append(path)
    return paths


def _passive_hidraw_capture(devices: list[dict[str, Any]], seconds: float = PASSIVE_CAPTURE_SECONDS) -> dict[str, Any]:
    """Listen passively for input reports from the vendor hidraw channel.

    The file descriptors are opened O_RDONLY|O_NONBLOCK. This function never writes,
    never calls HIDIOCSFEATURE/SET_REPORT and never detaches the usbhid kernel driver.
    """
    paths = _vendor_hidraw_paths(devices)
    errors: list[dict[str, str]] = []
    if not paths:
        return {"capture_seconds": seconds, "paths": [], "frames_seen": 0, "errors": [], "recent_frames": list(RECENT_FRAMES.values())}

    selector = selectors.DefaultSelector()
    opened: list[int] = []
    read_count = 0
    try:
        for path in paths:
            try:
                flags = os.O_RDONLY | os.O_NONBLOCK
                if hasattr(os, "O_CLOEXEC"):
                    flags |= os.O_CLOEXEC
                fd = os.open(path, flags)
                opened.append(fd)
                selector.register(fd, selectors.EVENT_READ, data=path)
            except OSError as exc:
                errors.append({"hidraw": path, "error": f"{type(exc).__name__}: {exc}"})

        deadline = time.monotonic() + max(0.1, float(seconds))
        while RUNNING and time.monotonic() < deadline and selector.get_map():
            timeout = min(0.25, max(0.0, deadline - time.monotonic()))
            for key, _mask in selector.select(timeout):
                fd = int(key.fd)
                path = str(key.data)
                while True:
                    try:
                        raw = os.read(fd, 4096)
                    except BlockingIOError:
                        break
                    except OSError as exc:
                        errors.append({"hidraw": path, "error": f"{type(exc).__name__}: {exc}"})
                        try:
                            selector.unregister(fd)
                        except Exception:
                            pass
                        break
                    if not raw:
                        break
                    read_count += 1
                    _remember_frame(path, raw)
    finally:
        selector.close()
        for fd in opened:
            try:
                os.close(fd)
            except OSError:
                pass

    recent = sorted(RECENT_FRAMES.values(), key=lambda item: int(item.get("last_seen", 0)), reverse=True)
    return {
        "capture_seconds": seconds,
        "paths": paths,
        "frames_seen_this_cycle": read_count,
        "errors": errors[-20:],
        "recent_frames": recent,
        "write_operations_performed": False,
    }


def _find_devices() -> list[dict[str, Any]]:
    if not SYSFS.exists():
        return []
    result: list[dict[str, Any]] = []
    for device_dir in sorted(SYSFS.iterdir()):
        vid = (_read_text(device_dir / "idVendor") or "").lower()
        pid_text = (_read_text(device_dir / "idProduct") or "").lower()
        if vid != VID_HEX:
            continue
        try:
            pid = int(pid_text, 16)
        except ValueError:
            continue
        if pid not in PIDS:
            continue

        bus = _to_int(_read_text(device_dir / "busnum"), 10)
        address = _to_int(_read_text(device_dir / "devnum"), 10)
        hidraw = _hidraw_for(device_dir)
        record: dict[str, Any] = {
            "sysfs": device_dir.name,
            "vid": vid,
            "pid": f"{pid:04x}",
            "mode": PIDS[pid],
            "manufacturer": _read_text(device_dir / "manufacturer"),
            "product": _read_text(device_dir / "product"),
            "serial_number": _read_text(device_dir / "serial"),
            "bus_number": bus,
            "device_number": address,
            "usb_version": _read_text(device_dir / "version"),
            "device_class": _read_text(device_dir / "bDeviceClass"),
            "device_subclass": _read_text(device_dir / "bDeviceSubClass"),
            "device_protocol": _read_text(device_dir / "bDeviceProtocol"),
            "max_packet_size_0": _read_text(device_dir / "bMaxPacketSize0"),
            "interfaces": _interfaces(device_dir),
            "hid": hidraw,
        }
        record["read_only_reports"] = _feature_reports(bus, address, hidraw)
        result.append(record)
    return result


def probe() -> dict[str, Any]:
    devices = _find_devices()
    passive = _passive_hidraw_capture(devices)
    return {
        "schema": 2,
        "captured_at": int(time.time()),
        "mode": "read_only",
        "writes_performed": False,
        "expected_vid": VID_HEX,
        "expected_pids": {f"{pid:04x}": name for pid, name in PIDS.items()},
        "device_count": len(devices),
        "devices": devices,
        "passive_hidraw": passive,
        "notes": [
            "Only USB descriptors, HID GET_REPORT requests and passive O_RDONLY hidraw reads are used.",
            "No hidraw write, HID SET_REPORT, firmware write, driver detach or pairing command is issued by this probe.",
            "Vendor report ID 0xC8 is captured passively when the microphone emits an input report.",
        ],
    }


def _write(payload: dict[str, Any]) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".json.new")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
    os.chmod(tmp, 0o600)
    tmp.replace(OUT)


def _stop(_signum: int, _frame: Any) -> None:
    global RUNNING
    RUNNING = False


def main() -> None:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    while RUNNING:
        cycle_started = time.monotonic()
        try:
            _write(probe())
        except Exception as exc:
            try:
                _write(
                    {
                        "schema": 2,
                        "captured_at": int(time.time()),
                        "mode": "read_only",
                        "writes_performed": False,
                        "device_count": 0,
                        "devices": [],
                        "passive_hidraw": {"recent_frames": list(RECENT_FRAMES.values()), "error": f"{type(exc).__name__}: {exc}"},
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
            except Exception:
                pass
        elapsed = time.monotonic() - cycle_started
        remaining = max(0.0, INTERVAL - elapsed)
        for _ in range(int(remaining * 10)):
            if not RUNNING:
                break
            time.sleep(0.1)


if __name__ == "__main__":
    main()
