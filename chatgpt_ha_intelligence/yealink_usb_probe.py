from __future__ import annotations

import json
import os
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
RUNNING = True


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


def _hidraw_for(device_dir: Path) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for interface in sorted(device_dir.parent.glob(f"{device_dir.name}:*")):
        if (_read_text(interface / "bInterfaceClass") or "").lower() != "03":
            continue
        interface_number = _to_int(_read_text(interface / "bInterfaceNumber"), 16)
        for path in sorted(interface.rglob("hidraw*")):
            if not path.name.startswith("hidraw"):
                continue
            dev_path = Path("/dev") / path.name
            report_descriptor = _hid_report_descriptor(path.name)
            result.append(
                {
                    "hidraw": str(dev_path),
                    "interface_number": interface_number,
                    "report_descriptor_size": len(report_descriptor) if report_descriptor is not None else None,
                    "report_descriptor_hex": report_descriptor.hex() if report_descriptor is not None else None,
                    "report_ids": _report_ids(report_descriptor or b""),
                }
            )
    return result


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
    return {
        "schema": 1,
        "captured_at": int(time.time()),
        "mode": "read_only",
        "writes_performed": False,
        "expected_vid": VID_HEX,
        "expected_pids": {f"{pid:04x}": name for pid, name in PIDS.items()},
        "device_count": len(devices),
        "devices": devices,
        "notes": [
            "Only USB descriptors and HID GET_REPORT requests are used.",
            "No HID SET_REPORT, firmware write or pairing command is issued by this probe.",
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
        try:
            _write(probe())
        except Exception as exc:
            try:
                _write(
                    {
                        "schema": 1,
                        "captured_at": int(time.time()),
                        "mode": "read_only",
                        "writes_performed": False,
                        "device_count": 0,
                        "devices": [],
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
            except Exception:
                pass
        for _ in range(INTERVAL * 10):
            if not RUNNING:
                break
            time.sleep(0.1)


if __name__ == "__main__":
    main()
