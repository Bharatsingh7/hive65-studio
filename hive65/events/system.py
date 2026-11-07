"""Caps Lock and battery-low events."""
from pathlib import Path

from . import LINUX, WINDOWS, Source


class SystemEvents(Source):
    name = "system"
    interval = 0.1

    def setup(self):
        import psutil
        self.psutil = psutil
        self.caps = self._caps()
        self.battery_warned = False
        self.tick = 0

    def _caps(self):
        if WINDOWS:
            import ctypes
            return bool(ctypes.windll.user32.GetKeyState(0x14) & 1)
        if LINUX:
            for led in Path("/sys/class/leds").glob("*capslock*"):
                return (led / "brightness").read_text().strip() != "0"
        return None

    def poll(self):
        caps = self._caps()
        if caps is not None and caps != self.caps:
            self.caps = caps
            self.emit("caps", caps)
        self.tick += 1
        if self.tick % 100 == 0:   # battery every ~10 s
            b = self.psutil.sensors_battery()
            if b and not b.power_plugged and b.percent <= 15 and not self.battery_warned:
                self.battery_warned = True
                self.emit("battery", b.percent / 100)
            elif b and (b.power_plugged or b.percent > 20):
                self.battery_warned = False


def create(emit):
    return SystemEvents(emit)
