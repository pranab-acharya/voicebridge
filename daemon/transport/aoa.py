"""
AOAv2 (Android Open Accessory v2) USB transport.

The laptop presents itself as a USB accessory; the Android app opens
it and streams audio. Requires libusb and pyusb.

Install libusb on Linux:  sudo apt install libusb-1.0-0
"""
import time
from typing import Optional
from .base import Transport

# AOA USB vendor control requests
_AOA_GET_PROTOCOL    = 51
_AOA_SEND_STRING     = 52
_AOA_START_ACCESSORY = 53

# String indices for AOA identification
_STR_MANUFACTURER = 0
_STR_MODEL        = 1
_STR_DESCRIPTION  = 2
_STR_VERSION      = 3
_STR_URI          = 4
_STR_SERIAL       = 5

# USB IDs once the device is in accessory mode
_ACCESSORY_VID  = 0x18D1
_ACCESSORY_PIDS = {0x2D00, 0x2D01}  # accessory, accessory+ADB


class AoaTransport(Transport):
    def __init__(self,
                 manufacturer: str = "VoiceBridge",
                 model:        str = "LaptopDaemon",
                 description:  str = "VoiceBridge Daemon",
                 version:      str = "1.0",
                 usb_timeout:  int = 5000) -> None:
        self.strings    = [manufacturer, model, description, version, "", ""]
        self.usb_timeout = usb_timeout
        self._dev    = None
        self._ep_in  = None
        self._ep_out = None
        self._connected = False

    def connect(self) -> bool:
        try:
            import usb.core
            import usb.util
        except ImportError:
            raise RuntimeError("pyusb not installed: pip install pyusb")

        dev = self._find_accessory_device(usb)
        if dev is None:
            dev = self._switch_to_accessory_mode(usb)
        if dev is None:
            return False

        try:
            if dev.is_kernel_driver_active(0):
                dev.detach_kernel_driver(0)
            dev.set_configuration()
        except Exception:
            pass

        cfg  = dev.get_active_configuration()
        intf = cfg[(0, 0)]
        ep_in = usb.util.find_descriptor(
            intf, custom_match=lambda e:
            usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN)
        ep_out = usb.util.find_descriptor(
            intf, custom_match=lambda e:
            usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT)

        if not ep_in or not ep_out:
            return False

        self._dev       = dev
        self._ep_in     = ep_in
        self._ep_out    = ep_out
        self._connected = True
        return True

    def _find_accessory_device(self, usb):
        for pid in _ACCESSORY_PIDS:
            dev = usb.core.find(idVendor=_ACCESSORY_VID, idProduct=pid)
            if dev:
                return dev
        return None

    def _switch_to_accessory_mode(self, usb):
        for dev in usb.core.find(find_all=True):
            try:
                proto = dev.ctrl_transfer(0xC0, _AOA_GET_PROTOCOL, 0, 0, 2)
                version = (proto[1] << 8) | proto[0]
                if version < 1:
                    continue
                for idx, s in enumerate(self.strings):
                    b = s.encode("utf-8") + b"\x00"
                    dev.ctrl_transfer(0x40, _AOA_SEND_STRING, 0, idx, b)
                dev.ctrl_transfer(0x40, _AOA_START_ACCESSORY, 0, 0, None)
                time.sleep(2)
                return self._find_accessory_device(usb)
            except Exception:
                continue
        return None

    def read(self, size: int) -> Optional[bytes]:
        if not self._ep_in:
            return None
        try:
            import usb.core
            data = self._ep_in.read(size, self.usb_timeout)
            return bytes(data)
        except Exception as exc:
            if "timeout" in str(exc).lower():
                return b""
            self._connected = False
            return None

    def write(self, data: bytes) -> bool:
        if not self._ep_out:
            return False
        try:
            self._ep_out.write(data, self.usb_timeout)
            return True
        except Exception:
            self._connected = False
            return False

    def disconnect(self) -> None:
        self._connected = False
        if self._dev:
            try:
                import usb.util
                usb.util.dispose_resources(self._dev)
            except Exception:
                pass
            self._dev = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def name(self) -> str:
        return "AOAv2 USB"
