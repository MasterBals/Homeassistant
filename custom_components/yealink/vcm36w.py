"""Read-only USB coordinator for Yealink VCM36-W."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .models import Vcm36wData

_USB_SYSFS = Path("/sys/bus/usb/devices")
_VID = "6993"
_PIDS = {"b06a", "b068"}


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(errors="replace").strip()
    except (OSError, UnicodeError):
        return None


class Vcm36wCoordinator(DataUpdateCoordinator[Vcm36wData]):
    """Track a VCM36-W attached to the Home Assistant host over USB."""

    def __init__(
        self,
        hass: HomeAssistant,
        logger,
        *,
        serial_number: str | None,
        discovery_path: str | None,
    ) -> None:
        super().__init__(
            hass,
            logger,
            name="Yealink VCM36-W",
            update_interval=timedelta(seconds=10),
        )
        self._serial_number = serial_number or None
        self._discovery_path = discovery_path or None
        self.data = Vcm36wData(serial_number=self._serial_number)

    @staticmethod
    def _interface_flags(device_dir: Path) -> tuple[bool, bool]:
        """Return whether HID and USB Audio interfaces exist."""
        has_hid = False
        has_audio = False
        for interface in device_dir.parent.glob(f"{device_dir.name}:*"):
            interface_class = (_read_text(interface / "bInterfaceClass") or "").lower()
            if interface_class == "03":
                has_hid = True
            elif interface_class == "01":
                has_audio = True
        return has_hid, has_audio

    def _scan(self) -> Vcm36wData:
        if not _USB_SYSFS.exists():
            return replace(self.data, connected=False, usb_path=None)

        for device_dir in _USB_SYSFS.iterdir():
            vid = (_read_text(device_dir / "idVendor") or "").lower()
            pid = (_read_text(device_dir / "idProduct") or "").lower()
            if vid != _VID.lower() or pid not in _PIDS:
                continue

            serial = _read_text(device_dir / "serial")
            if self._serial_number and serial and serial != self._serial_number:
                continue

            busnum = _read_text(device_dir / "busnum")
            devnum = _read_text(device_dir / "devnum")
            usb_path = self._discovery_path
            if busnum and devnum:
                usb_path = f"/dev/bus/usb/{int(busnum):03d}/{int(devnum):03d}"

            has_hid, has_audio = self._interface_flags(device_dir)
            return Vcm36wData(
                connected=True,
                usb_path=usb_path,
                serial_number=serial or self._serial_number,
                manufacturer=_read_text(device_dir / "manufacturer") or "Yealink",
                product=_read_text(device_dir / "product") or "VCM36-W",
                has_hid_interface=has_hid,
                has_audio_interface=has_audio,
            )

        return Vcm36wData(
            connected=False,
            usb_path=None,
            serial_number=self._serial_number,
            manufacturer="Yealink",
            product="VCM36-W",
            has_hid_interface=None,
            has_audio_interface=None,
        )

    async def _async_update_data(self) -> Vcm36wData:
        return await self.hass.async_add_executor_job(self._scan)
