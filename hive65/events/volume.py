"""Master volume / mute changes. Windows: Core Audio (pycaw). Linux: wpctl."""
import re
import subprocess

from . import LINUX, WINDOWS, Source


class WindowsVolume(Source):
    name = "volume"
    interval = 0.1

    def setup(self):
        import comtypes
        comtypes.CoInitialize()
        from pycaw.pycaw import AudioUtilities
        self.ep = AudioUtilities.GetSpeakers().EndpointVolume
        self.last = self._read()

    def _read(self):
        return round(self.ep.GetMasterVolumeLevelScalar(), 3), bool(self.ep.GetMute())

    def poll(self):
        cur = self._read()
        if cur != self.last:
            self.last = cur
            self.emit("volume", cur[0], muted=cur[1])


class LinuxVolume(Source):
    """PipeWire/WirePlumber: `wpctl get-volume @DEFAULT_AUDIO_SINK@` -> 'Volume: 0.45 [MUTED]'."""

    name = "volume"
    interval = 0.2

    def _read(self):
        out = subprocess.run(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"],
                             capture_output=True, text=True, timeout=2).stdout
        m = re.search(r"([\d.]+)", out)
        return (round(float(m.group(1)), 3) if m else 0.0), "MUTED" in out

    def setup(self):
        self.last = self._read()

    def poll(self):
        cur = self._read()
        if cur != self.last:
            self.last = cur
            self.emit("volume", min(1.0, cur[0]), muted=cur[1])


def create(emit):
    if WINDOWS:
        return WindowsVolume(emit)
    if LINUX:
        return LinuxVolume(emit)
    return None
