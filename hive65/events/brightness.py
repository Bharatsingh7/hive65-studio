"""Screen brightness changes.

Windows: screen_brightness_control (laptop panel via WMI, external monitors via
DDC/CI when supported). Linux: /sys/class/backlight (laptop panels).
"""
from pathlib import Path

from . import LINUX, WINDOWS, Source


class WindowsBrightness(Source):
    name = "brightness"
    interval = 0.4

    def setup(self):
        import comtypes
        comtypes.CoInitialize()
        import screen_brightness_control as sbc
        self.sbc = sbc
        self.last = self._read()

    def _read(self):
        # The built-in panel answers fastest and is what Fn keys change.
        try:
            return self.sbc.get_brightness(display=0, method="wmi")[0]
        except Exception:
            return self.sbc.get_brightness(display=0)[0]

    def poll(self):
        cur = self._read()
        if cur is not None and cur != self.last:
            self.last = cur
            self.emit("brightness", cur / 100)


class LinuxBrightness(Source):
    name = "brightness"
    interval = 0.2

    def setup(self):
        devices = sorted(Path("/sys/class/backlight").glob("*"))
        if not devices:
            raise RuntimeError("no /sys/class/backlight device")
        self.dev = devices[0]
        self.max = int((self.dev / "max_brightness").read_text())
        self.last = self._read()

    def _read(self):
        return int((self.dev / "brightness").read_text())

    def poll(self):
        cur = self._read()
        if cur != self.last:
            self.last = cur
            self.emit("brightness", cur / self.max)


def create(emit):
    if WINDOWS:
        return WindowsBrightness(emit)
    if LINUX:
        return LinuxBrightness(emit)
    return None
