"""Information displays built from bars and colours (no text)."""
import numpy as np

from ..canvas import hsv, parse_color
from . import Effect, effect, param

ROW_NUM = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-", "="]
ROW_Q = ["Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P", "[", "]"]
ROW_A = ["CapsLock", "A", "S", "D", "F", "G", "H", "J", "K", "L", ";", "'", "Enter"]
ROW_Z = ["LShift", "Z", "X", "C", "V", "B", "N", "M", ",", ".", "/", "RShift"]


def fill_row(canvas, names, fraction, color, dim=0.0):
    """Light the first `fraction` of a row of keys; the partial key is dimmer."""
    lit = fraction * len(names)
    for i, n in enumerate(names):
        level = min(1.0, max(0.0, lit - i))
        canvas.set_key(n, np.asarray(color) * max(level, dim))


@effect("sysmon", "CPU (number row), RAM (A row) and GPU (Z row) usage bars", "display")
class SysMon(Effect):
    params = {}

    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        import psutil
        self.psutil = psutil
        self.next, self.vals = 0.0, (0.0, 0.0, None)
        self.gpu = self._gpu_reader()

    @staticmethod
    def _gpu_reader():
        try:
            import pynvml
            pynvml.nvmlInit()
            h = pynvml.nvmlDeviceGetHandleByIndex(0)
            return lambda: pynvml.nvmlDeviceGetUtilizationRates(h).gpu / 100
        except Exception:
            return None

    def render(self, canvas, t, dt):
        if t >= self.next:
            gpu = self.gpu() if self.gpu else None
            self.vals = (self.psutil.cpu_percent() / 100,
                         self.psutil.virtual_memory().percent / 100, gpu)
            self.next = t + 0.5
        canvas.clear()
        for row, value in ((ROW_NUM, self.vals[0]), (ROW_A, self.vals[1]), (ROW_Z, self.vals[2])):
            if value is not None:
                fill_row(canvas, row, value, hsv(0.33 - 0.33 * value))  # green -> red


@effect("countdown", "timer: a bar drains across the board, then it flashes", "display")
class Countdown(Effect):
    params = {"minutes": param("float", 25.0, 0.5, 180, label="Minutes"),
              "color": param("color", "#ff3050", label="Colour")}

    def render(self, canvas, t, dt):
        import time
        if not hasattr(self, "started"):
            self.started = time.time()   # wall clock: unaffected by the speed setting
        total = self.opt("minutes") * 60
        left = max(0.0, total - (time.time() - self.started))
        canvas.clear()
        if left <= 0:
            canvas.clear(hsv(t * 0.5) * (0.5 + 0.5 * np.sin(t * 12)))
            return
        color = parse_color(self.opt("color"))
        for row in (ROW_NUM, ROW_Q, ROW_A, ROW_Z):
            fill_row(canvas, row, left / total, color)


@effect("calibrate", "test pattern for tuning colours and brightness", "display")
class Calibrate(Effect):
    params = {}

    def render(self, canvas, t, dt):
        canvas.clear()
        fill_row(canvas, ROW_NUM[:3], 1, (1, 0, 0))
        fill_row(canvas, ROW_NUM[3:6], 1, (0, 1, 0))
        fill_row(canvas, ROW_NUM[6:9], 1, (0, 0, 1))
        fill_row(canvas, ROW_NUM[9:], 1, (1, 1, 1))
        for i, n in enumerate(ROW_Q):            # grey ramp
            canvas.set_key(n, np.array([1.0, 1.0, 1.0]) * (i + 1) / len(ROW_Q))
        for i, n in enumerate(ROW_A):            # hue ramp
            canvas.set_key(n, hsv(i / len(ROW_A)))
        for i, n in enumerate(ROW_Z):            # dim hue ramp (25 %)
            canvas.set_key(n, hsv(i / len(ROW_Z)) * 0.25)
