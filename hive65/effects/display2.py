"""Useful display effects: system monitors, timers, wellbeing and ambient info.

All of them work on Linux and Windows (psutil, sockets, /sys, Open-Meteo);
where a sensor doesn't exist on a machine the effect shows a slow grey
"unavailable" pulse instead of failing. Information is shown with bars,
positions and colours only — no text.
"""
import datetime as dt_mod
import glob
import json
import math
import random
import socket
import sys
import time
import urllib.request

import numpy as np

from ..canvas import hsv, parse_color
from . import Effect, effect, param
from ._util import blob, grid, hsv_array
from .display import ROW_A, ROW_NUM, ROW_Q, ROW_Z, fill_row

ROWS4 = [ROW_NUM, ROW_Q, ROW_A, ROW_Z]
LINUX = sys.platform.startswith("linux")


def unavailable(canvas, t):
    """Slow grey breathing: the data source isn't available on this machine."""
    canvas.clear(np.array([0.35, 0.35, 0.45]) * (0.15 + 0.15 * math.sin(t * 2)))


def heat(v):
    """0 -> green, 0.5 -> yellow, 1 -> red."""
    return hsv(0.33 - 0.33 * min(1.0, max(0.0, v)))


def column_bars(canvas, values, color_fn):
    """Vertical bars, one per canvas column, growing up from the bottom row."""
    h = canvas.h
    for c in range(canvas.w):
        v = values[c]
        lit = v * h
        for r in range(h):
            level = min(1.0, max(0.0, lit - (h - 1 - r)))
            canvas.pixels[r, c] = color_fn(c, v) * level


# --------------------------------------------------------------------- system
@effect("cpu_cores", "every CPU core as its own bar, green to red with load")
class CPUCores(Effect):
    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        import psutil
        psutil.cpu_percent(percpu=True)
        self.p = self.poll(lambda: psutil.cpu_percent(percpu=True), 0.5, [],
                           demo=[15, 80, 35, 60, 95, 20, 45, 70, 10, 55, 85, 30])
        self.shown = np.zeros(ctx.canvas.w)

    def render(self, canvas, t, dt):
        cores = self.p.value or []
        canvas.clear()
        if not cores:
            return
        # spread cores over the 16 columns (average when there are more cores)
        target = np.array([np.mean(np.array_split(np.array(cores), canvas.w)[c]) / 100
                           if len(cores) >= canvas.w else cores[int(c * len(cores) / canvas.w)] / 100
                           for c in range(canvas.w)])
        self.shown += (target - self.shown) * min(1.0, dt * 6)
        column_bars(canvas, self.shown, lambda c, v: heat(v))


@effect("cpu_temp", "board colour and pulse speed follow the CPU temperature")
class CPUTemp(Effect):
    params = {"cool": param("float", 35.0, 10, 60, label="Cool (°C)"),
              "hot": param("float", 90.0, 60, 110, label="Hot (°C)")}

    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        self.p = self.poll(self._read, 2.0, demo=72.0)
        self.phase = 0.0

    @staticmethod
    def _read():
        import psutil
        temps = getattr(psutil, "sensors_temperatures", lambda: {})()
        for key in ("coretemp", "k10temp", "zenpower", "cpu_thermal", "acpitz"):
            if temps.get(key):
                return max(s.current for s in temps[key])
        for entries in temps.values():
            if entries:
                return max(s.current for s in entries)
        return None

    def render(self, canvas, t, dt):
        temp = self.p.value
        if temp is None:
            unavailable(canvas, t)   # e.g. Windows without a sensor driver
            return
        v = (temp - self.opt("cool")) / max(1.0, self.opt("hot") - self.opt("cool"))
        v = min(1.0, max(0.0, v))
        self.phase += dt * (0.5 + v * 4)
        x, y = grid(canvas)
        level = 0.55 + 0.45 * np.sin(self.phase * 2 * np.pi - x * 0.3)
        canvas.pixels[:] = hsv_array(0.62 - 0.62 * v, 1, level)
        fill_row(canvas, ROW_NUM, v, np.array([1.0, 1.0, 1.0]))


@effect("ram_fill", "memory use as a liquid level; swap shows as a magenta top layer")
class RAMFill(Effect):
    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        import psutil
        self.p = self.poll(lambda: (psutil.virtual_memory().percent / 100,
                                    psutil.swap_memory().percent / 100), 1.0, (0.0, 0.0),
                           demo=(0.62, 0.3))

    def render(self, canvas, t, dt):
        ram, swap = self.p.value
        x, y = grid(canvas)
        surface = canvas.h * (1 - ram) + np.sin(x * 0.7 + t * 3) * 0.25
        lit = np.clip(y - surface + 0.5, 0, 1)
        canvas.pixels[:] = hsv_array(0.5 - ram * 0.5 + (canvas.h - y) * 0.02, 1, lit)
        if swap > 0.01:
            fill_row(canvas, ROW_NUM, swap, np.array([1.0, 0.0, 0.8]))


@effect("net_traffic", "scrolling graph: download rises in blue, upload hangs down in orange")
class NetTraffic(Effect):
    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        import psutil
        self.psutil = psutil
        self.last = psutil.net_io_counters()
        self.last_t = time.time()
        self.hist = np.zeros((2, ctx.canvas.w))
        self.peak = 1e5
        self.acc = 0.0

    def render(self, canvas, t, dt):
        self.acc += dt
        if self.acc >= 0.5:
            self.acc = 0.0
            now, cur = time.time(), self.psutil.net_io_counters()
            span = max(0.05, now - self.last_t)
            down = (cur.bytes_recv - self.last.bytes_recv) / span
            up = (cur.bytes_sent - self.last.bytes_sent) / span
            self.last, self.last_t = cur, now
            self.peak = max(self.peak * 0.97, down, up, 5e4)
            scale = lambda v: min(1.0, math.log1p(v) / math.log1p(self.peak))
            self.hist = np.roll(self.hist, -1, axis=1)
            self.hist[:, -1] = (scale(down), scale(up))
        canvas.clear()
        h = canvas.h
        for c in range(canvas.w):
            d, u = self.hist[:, c]
            for r in range(h):
                from_bottom = h - 1 - r
                down_lvl = min(1.0, max(0.0, d * h - from_bottom))
                up_lvl = min(1.0, max(0.0, u * (h - 1) - r)) * 0.9
                canvas.pixels[r, c] = (np.array([0.1, 0.5, 1.0]) * down_lvl +
                                       np.array([1.0, 0.45, 0.0]) * up_lvl)


@effect("disk_activity", "disk reads flash green on the left, writes red on the right")
class DiskActivity(Effect):
    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        import psutil
        self.psutil = psutil
        self.last = psutil.disk_io_counters()
        self.acc = 0.0
        self.peak = 1e6

    def render(self, canvas, t, dt):
        canvas.fade(0.85)
        self.acc += dt
        if self.acc < 0.2:
            return
        self.acc = 0.0
        cur = self.psutil.disk_io_counters()
        if cur is None or self.last is None:
            unavailable(canvas, t)
            return
        r = cur.read_bytes - self.last.read_bytes
        w = cur.write_bytes - self.last.write_bytes
        if getattr(self.ctx, "demo", False):
            r, w = 4e6, 2e6
        self.last = cur
        self.peak = max(self.peak * 0.98, r, w, 2e5)
        half = canvas.w // 2
        for amount, cols, color in ((r, range(0, half), np.array([0.1, 1.0, 0.3])),
                                    (w, range(half, canvas.w), np.array([1.0, 0.15, 0.1]))):
            n = int(min(1.0, math.log1p(amount) / math.log1p(self.peak)) * len(cols) * canvas.h * 0.6)
            for _ in range(n):
                canvas.set(random.choice(list(cols)), random.randrange(canvas.h), color)


@effect("battery", "battery level bar; a shimmer runs along it while charging")
class Battery(Effect):
    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        import psutil
        from types import SimpleNamespace
        self.p = self.poll(psutil.sensors_battery, 5.0,
                           demo=SimpleNamespace(percent=68, power_plugged=True))

    def render(self, canvas, t, dt):
        b = self.p.value
        canvas.clear()
        if b is None:   # desktop: no battery -> steady "on mains" glow
            canvas.clear(np.array([0.1, 0.3, 1.0]) * (0.3 + 0.1 * math.sin(t)))
            return
        frac = b.percent / 100
        color = hsv(0.33 * frac) if frac > 0.2 else np.array([1.0, 0.1, 0.0]) * (0.5 + 0.5 * math.sin(t * 6))
        for row in ROWS4:
            fill_row(canvas, row, frac, color)
        if b.power_plugged:
            x, _ = grid(canvas)
            pos = (t * 6) % (canvas.w * frac + 3)
            shimmer = np.clip(1 - np.abs(x - pos) / 1.5, 0, 1)[..., None]
            lit = canvas.pixels.max(axis=2, keepdims=True) > 0
            canvas.pixels[:] = np.where(lit, np.minimum(1, canvas.pixels + shimmer * 0.6), canvas.pixels)


@effect("gpu_meter", "GPU load (top rows) and video memory (bottom rows): NVIDIA or AMD")
class GPUMeter(Effect):
    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        self.p = self.poll(self._reader() if not getattr(ctx, "demo", False) else None, 0.5, demo=(0.7, 0.45))

    @staticmethod
    def _reader():
        try:
            import pynvml
            pynvml.nvmlInit()
            h = pynvml.nvmlDeviceGetHandleByIndex(0)

            def nv():
                m = pynvml.nvmlDeviceGetMemoryInfo(h)
                return pynvml.nvmlDeviceGetUtilizationRates(h).gpu / 100, m.used / m.total
            return nv
        except Exception:
            pass
        cards = glob.glob("/sys/class/drm/card*/device/gpu_busy_percent")
        if cards:   # AMD on Linux
            dev = cards[0].rsplit("/", 1)[0]

            def amd():
                busy = int(open(f"{dev}/gpu_busy_percent").read()) / 100
                used = int(open(f"{dev}/mem_info_vram_used").read())
                total = int(open(f"{dev}/mem_info_vram_total").read())
                return busy, used / total
            return amd
        return lambda: None

    def render(self, canvas, t, dt):
        v = self.p.value
        if v is None:
            unavailable(canvas, t)
            return
        util, mem = v
        canvas.clear()
        for row in (ROW_NUM, ROW_Q):
            fill_row(canvas, row, util, heat(util))
        for row in (ROW_A, ROW_Z):
            fill_row(canvas, row, mem, hsv(0.75 - mem * 0.2))


@effect("ping_meter", "internet latency: green is fast, red is slow; blinks red when offline")
class PingMeter(Effect):
    params = {"host": param("text", "1.1.1.1", label="Host"),
              "good": param("float", 30.0, 5, 200, label="Good (ms)"),
              "bad": param("float", 200.0, 50, 1000, label="Bad (ms)")}

    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        host = self.opt("host")
        self.p = self.poll(lambda: self._ping(host), 1.0, demo=45.0)
        self.pulses = []
        self.last_val = None

    @staticmethod
    def _ping(host):
        t0 = time.perf_counter()
        with socket.create_connection((host, 443), timeout=2):
            pass
        return (time.perf_counter() - t0) * 1000

    def render(self, canvas, t, dt):
        ms = self.p.value if not self.p.error else None
        x, y = grid(canvas)
        canvas.fade(0.8)
        if ms is None:
            if self.p.error:
                canvas.clear(np.array([1.0, 0.0, 0.0]) * (1 if int(t * 2) % 2 else 0.1))
            return
        if ms != self.last_val:
            self.last_val = ms
            self.pulses.append(t)
        v = (ms - self.opt("good")) / max(1.0, self.opt("bad") - self.opt("good"))
        color = heat(v)
        self.pulses = [p for p in self.pulses if t - p < 1.5]
        for p in self.pulses:
            pos = (t - p) * 14
            glow = np.clip(1 - np.abs(x - pos) / 1.2, 0, 1)[..., None]
            canvas.pixels[:] = np.maximum(canvas.pixels, color * glow)
        fill_row(canvas, ROW_Z, min(1.0, max(0.05, v)), color * 0.6)


@effect("mic_meter", "your microphone level, so you can see if you're heard on calls")
class MicMeter(Effect):
    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        import threading
        self.level, self.peak, self.error = 0.0, 0.0, None
        self._stop = threading.Event()
        self.demo = getattr(ctx, "demo", False)
        if not self.demo:   # never open the microphone for a gallery preview
            threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            import soundcard as sc
            mic = sc.default_microphone()
            with mic.recorder(samplerate=48000, blocksize=1024) as rec:
                while not self._stop.is_set():
                    data = rec.record(numframes=1024)
                    rms = float(np.sqrt(np.mean(data ** 2)))
                    db = 20 * math.log10(max(rms, 1e-6))
                    self.level = max(0.0, min(1.0, (db + 60) / 50))
        except Exception as e:
            self.error = str(e)

    def close(self):
        self._stop.set()

    def render(self, canvas, t, dt):
        if self.error:
            canvas.clear(np.array([1.0, 0.0, 0.1]) * (0.3 + 0.2 * math.sin(t * 3)))
            return
        if self.demo:
            self.level = 0.55 + 0.35 * math.sin(t * 7)
        self.peak = max(self.level, self.peak - dt * 0.6)
        canvas.clear()
        for row in ROWS4:
            fill_row(canvas, row, self.level, heat(self.level * 0.9))
        i = min(len(ROW_Z) - 1, int(self.peak * len(ROW_Z)))
        canvas.set_key(ROW_Q[min(i, len(ROW_Q) - 1)], np.array([1.0, 1.0, 1.0]))


# --------------------------------------------------------------------- time & focus
def _wall_start(self):
    if not hasattr(self, "_t0"):
        self._t0 = time.time()
    return time.time() - self._t0


def _drain(canvas, frac, color):
    for row in ROWS4:
        fill_row(canvas, row, frac, color)


@effect("pomodoro", "work/break focus timer: a bar drains, colours change between phases")
class Pomodoro(Effect):
    params = {"work": param("float", 25.0, 1, 90, label="Work (min)"),
              "rest": param("float", 5.0, 1, 30, label="Break (min)"),
              "long_rest": param("float", 15.0, 5, 45, label="Long break (min)"),
              "rounds": param("int", 4, 2, 8, label="Rounds before long break")}

    def render(self, canvas, t, dt):
        el = _wall_start(self)
        w, r, lr, n = (self.opt("work") * 60, self.opt("rest") * 60,
                       self.opt("long_rest") * 60, self.opt("rounds"))
        cycle = (w + r) * (n - 1) + w + lr
        pos = el % cycle
        phases = []
        for i in range(n):
            phases.append(("work", w))
            phases.append(("rest", lr if i == n - 1 else r))
        for kind, length in phases:
            if pos < length:
                break
            pos -= length
        left = 1 - pos / length
        color = np.array([1.0, 0.25, 0.1]) if kind == "work" else np.array([0.1, 1.0, 0.45])
        canvas.clear(color * 0.06)
        _drain(canvas, left, color)
        if length - pos < 10:   # last 10 s: blink to warn the phase is ending
            if int(t * 4) % 2:
                canvas.pixels[:] = np.maximum(canvas.pixels, color * 0.5)
        # rounds done so far, as dots on the bottom row
        done = int(el % cycle // (w + r))
        for i in range(n):
            canvas.set(1 + i * 2, canvas.h - 1, np.array([1.0, 1.0, 1.0]) * (1 if i < done else 0.12))


@effect("hourglass", "sand pours from the top rows to the bottom over the set time")
class Hourglass(Effect):
    params = {"minutes": param("float", 10.0, 0.5, 120, label="Minutes"),
              "color": param("color", "#ffc040", label="Sand colour")}

    def render(self, canvas, t, dt):
        total = self.opt("minutes") * 60
        frac = min(1.0, _wall_start(self) / total)
        sand = parse_color(self.opt("color"))
        canvas.clear()
        cells = canvas.w * 2
        top_left = int(round(cells * (1 - frac)))
        bottom = int(round(cells * frac))
        for i in range(cells):   # top half empties from the middle out
            r, c = divmod(i, canvas.w)
            if i < top_left:
                canvas.pixels[r, c] = sand * 0.8
        for i in range(bottom):  # bottom half fills from the bottom row up
            r, c = divmod(i, canvas.w)
            canvas.pixels[canvas.h - 1 - r, c] = sand
        if frac < 1:
            stream_row = 2 + int(t * 8) % 2
            canvas.set(canvas.w // 2, stream_row, sand)
        else:
            canvas.pixels[:] *= 0.5 + 0.5 * (int(t * 3) % 2)


@effect("stopwatch", "elapsed time: seconds sweep the A row, minutes fill Q, hours fill numbers")
class Stopwatch(Effect):
    def render(self, canvas, t, dt):
        el = _wall_start(self)
        canvas.clear()
        fill_row(canvas, ROW_NUM, (el / 3600) % 12 / 12, np.array([1.0, 0.3, 0.8]))
        fill_row(canvas, ROW_Q, (el / 60) % 60 / 60, np.array([0.2, 0.7, 1.0]))
        i = int((el % 60) / 60 * len(ROW_A))
        canvas.set_key(ROW_A[i], np.array([1.0, 1.0, 1.0]))


@effect("day_progress", "the sun crosses the board through the day; sky colour follows the time")
class DayProgress(Effect):
    params = {"sunrise": param("float", 6.0, 3, 10, label="Sunrise (hour)"),
              "sunset": param("float", 18.5, 15, 22, label="Sunset (hour)")}

    def render(self, canvas, t, dt):
        now = dt_mod.datetime.now()
        hour = now.hour + now.minute / 60 + now.second / 3600
        rise, setp = self.opt("sunrise"), self.opt("sunset")
        x, y = grid(canvas)
        if rise <= hour <= setp:
            f = (hour - rise) / (setp - rise)
            edge = min(f, 1 - f)                 # 0 at dawn/dusk, 0.5 at noon
            sky = np.array([1.0, 0.45, 0.15]) * (1 - min(1, edge * 6)) + np.array([0.2, 0.55, 1.0]) * min(1, edge * 6)
            canvas.pixels[:] = sky * (0.25 + 0.35 * (y / canvas.h))[..., None]
            sx = f * (canvas.w - 1) + 0.5
            sy = canvas.h - 0.5 - math.sin(f * math.pi) * (canvas.h - 1)
            canvas.pixels[:] = np.maximum(canvas.pixels, np.array([1.0, 0.85, 0.2]) *
                                          blob(x, y, sx, sy, 1.8, 1.0)[..., None])
        else:
            canvas.clear(np.array([0.02, 0.03, 0.12]))
            rng = np.random.default_rng(int(now.timestamp()) // 3)
            for _ in range(6):
                canvas.set(int(rng.integers(canvas.w)), int(rng.integers(canvas.h)), np.array([0.6, 0.6, 0.8]))


@effect("progress", "how much of the day, week, month or year is done")
class Progress(Effect):
    params = {"span": param("choice", "day", choices=["day", "week", "month", "year"], label="Span")}

    def render(self, canvas, t, dt):
        now = dt_mod.datetime.now()
        span = self.opt("span")
        start_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if span == "day":
            start, end = start_day, start_day + dt_mod.timedelta(days=1)
        elif span == "week":
            start = start_day - dt_mod.timedelta(days=now.weekday())
            end = start + dt_mod.timedelta(days=7)
        elif span == "month":
            start = start_day.replace(day=1)
            end = (start + dt_mod.timedelta(days=32)).replace(day=1)
        else:
            start = start_day.replace(month=1, day=1)
            end = start.replace(year=start.year + 1)
        frac = (now - start) / (end - start)
        keys = [k for row in ROWS4 for k in row]   # reading order, like a page filling up
        lit = frac * len(keys)
        canvas.clear()
        for i, k in enumerate(keys):
            level = min(1.0, max(0.0, lit - i))
            canvas.set_key(k, hsv(0.55 + 0.4 * i / len(keys)) * max(level, 0.05))


@effect("metronome", "a pendulum ticks at your tempo; the first beat of each bar flashes")
class Metronome(Effect):
    params = {"bpm": param("float", 100.0, 30, 240, label="BPM"),
              "beats": param("int", 4, 1, 12, label="Beats per bar")}

    def render(self, canvas, t, dt):
        el = _wall_start(self)
        beat_len = 60 / self.opt("bpm")
        beat = int(el / beat_len)
        phase = (el % beat_len) / beat_len
        accent = beat % self.opt("beats") == 0
        x, y = grid(canvas)
        swing = math.sin((beat + phase) * math.pi)
        pos = canvas.w / 2 + swing * (canvas.w / 2 - 1)
        flash = max(0.0, 1 - phase * 5)
        color = np.array([1.0, 0.3, 0.1]) if accent else np.array([0.2, 0.7, 1.0])
        canvas.clear(color * flash * (0.5 if accent else 0.25))
        canvas.pixels[:] = np.maximum(canvas.pixels, np.array([1.0, 1.0, 1.0]) *
                                      np.clip(1 - np.abs(x - pos) / 0.9, 0, 1)[..., None])


@effect("breathing_guide", "box breathing: fill up to inhale, hold, empty to exhale, hold")
class BreathingGuide(Effect):
    params = {"inhale": param("float", 4.0, 2, 10, label="Inhale (s)"),
              "hold": param("float", 4.0, 0, 10, label="Hold (s)"),
              "exhale": param("float", 4.0, 2, 12, label="Exhale (s)"),
              "rest": param("float", 4.0, 0, 10, label="Hold empty (s)")}

    def render(self, canvas, t, dt):
        el = _wall_start(self)
        a, b, c, d = (self.opt("inhale"), self.opt("hold"), self.opt("exhale"), self.opt("rest"))
        pos = el % (a + b + c + d)
        if pos < a:
            level, color = pos / a, np.array([0.1, 0.8, 1.0])
        elif pos < a + b:
            level, color = 1.0, np.array([0.5, 0.4, 1.0])
        elif pos < a + b + c:
            level, color = 1 - (pos - a - b) / c, np.array([0.1, 1.0, 0.6])
        else:
            level, color = 0.0, np.array([0.5, 0.4, 1.0])
        level = 0.5 - 0.5 * math.cos(level * math.pi)   # ease in/out
        x, y = grid(canvas)
        surface = canvas.h * (1 - level)
        lit = np.clip(y - surface + 0.5, 0, 1)
        canvas.pixels[:] = color * (0.08 + 0.92 * lit)[..., None]


@effect("reminder", "gentle waves every N minutes: rest your eyes, drink water or stretch")
class Reminder(Effect):
    params = {"preset": param("choice", "eyes", choices=["eyes", "water", "stretch", "custom"],
                              label="Reminder"),
              "every": param("float", 20.0, 1, 180, label="Every (min, custom)"),
              "length": param("float", 20.0, 5, 120, label="Show for (s, custom)"),
              "color": param("color", "#40ff80", label="Colour (custom)")}
    PRESETS = {"eyes": (20, 20, "#40ff80"), "water": (45, 15, "#2090ff"), "stretch": (60, 30, "#ff9020")}

    def render(self, canvas, t, dt):
        every, length, color = self.PRESETS.get(self.opt("preset"),
                                                (self.opt("every"), self.opt("length"), self.opt("color")))
        el = _wall_start(self)
        pos = el % (every * 60)
        if getattr(self.ctx, "demo", False):
            pos = every * 60 - length / 2      # preview: show the reminder wave
        col = parse_color(color)
        if pos < every * 60 - length:
            # between reminders: a faint progress line on the bottom row
            canvas.clear()
            fill_row(canvas, ROW_Z, pos / (every * 60 - length), col * 0.25)
            return
        x, y = grid(canvas)
        wave = 0.5 + 0.5 * np.sin(x * 0.5 - t * 3 + y * 0.6)
        canvas.pixels[:] = col * (0.3 + 0.7 * wave)[..., None]


@effect("sunrise_alarm", "a wake-up light: deep red slowly brightens to warm daylight")
class SunriseAlarm(Effect):
    params = {"minutes": param("float", 15.0, 1, 60, label="Sunrise length (min)")}

    def render(self, canvas, t, dt):
        f = min(1.0, _wall_start(self) / (self.opt("minutes") * 60))
        if getattr(self.ctx, "demo", False):
            f = 0.55
        x, y = grid(canvas)
        rise = np.clip(f * 1.6 - (y / canvas.h) * 0.6, 0, 1)   # light climbs from the bottom row
        r = 0.15 + 0.85 * rise
        g = np.clip(rise * 1.3 - 0.35, 0, 1) * 0.85
        b = np.clip(rise * 1.6 - 1.0, 0, 1) * 0.6
        canvas.pixels[:] = np.stack([r, g, b], -1) * (0.15 + 0.85 * f)


@effect("moon_phase", "tonight's moon: the lit part of the board matches its phase")
class MoonPhase(Effect):
    def render(self, canvas, t, dt):
        days = (time.time() / 86400 - 10957.5 - 6.8) % 29.530588   # since a known new moon
        phase = days / 29.530588                                    # 0 new, 0.5 full
        x, y = grid(canvas)
        cx, cy, r = canvas.w / 2, canvas.h / 2, 2.6
        dx, dy = (x - cx) / r, (y - cy) * 1.2 / r
        inside = dx ** 2 + dy ** 2 <= 1
        # terminator: the lit side's boundary moves across the disc
        k = math.cos(phase * 2 * math.pi)
        edge = k * np.sqrt(np.clip(1 - dy ** 2, 0, 1))
        lit = (dx > edge) if phase < 0.5 else (dx < -edge)
        canvas.clear(np.array([0.0, 0.0, 0.02]))
        canvas.pixels[inside & lit] = np.array([1.0, 0.95, 0.75])
        canvas.pixels[inside & ~lit] = np.array([0.05, 0.07, 0.15])


@effect("weather", "current weather animation + temperature bar (Open-Meteo, no account)")
class Weather(Effect):
    params = {"lat": param("float", 28.61, -90, 90, label="Latitude"),
              "lon": param("float", 77.21, -180, 180, label="Longitude")}

    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        lat, lon = self.opt("lat"), self.opt("lon")
        url = (f"https://api.open-meteo.com/v1/forecast?latitude={lat:.3f}&longitude={lon:.3f}"
               "&current=temperature_2m,weather_code,is_day")
        self.p = self.poll(lambda: json.load(urllib.request.urlopen(url, timeout=10))["current"], 900,
                           demo={"weather_code": 61, "temperature_2m": 26, "is_day": 1})
        self.drops = []

    def render(self, canvas, t, dt):
        cur = self.p.value
        if not cur:
            unavailable(canvas, t)
            return
        code, temp, day = cur["weather_code"], cur["temperature_2m"], cur.get("is_day", 1)
        x, y = grid(canvas)
        if code in (0, 1):                       # clear
            if day:
                canvas.pixels[:] = np.array([1.0, 0.75, 0.1]) * blob(x, y, 3, 1, 5, 1.2)[..., None]
                canvas.pixels[:] += np.array([0.05, 0.25, 0.7])
            else:
                canvas.clear(np.array([0.02, 0.02, 0.1]))
                for i in range(5):
                    canvas.set((i * 7 + int(t)) % canvas.w, i % canvas.h, np.array([0.7, 0.7, 0.9]))
        elif code in (2, 3, 45, 48):             # clouds / fog
            n = np.sin(x * 0.6 - t * 0.8) * np.cos(y * 0.9 + t * 0.3) * 0.5 + 0.5
            canvas.pixels[:] = np.array([0.5, 0.55, 0.65]) * (0.3 + 0.6 * n)[..., None]
        elif code >= 95:                         # thunderstorm
            canvas.clear(np.array([0.05, 0.05, 0.15]))
            if random.random() < 0.03:
                canvas.clear(np.array([0.9, 0.9, 1.0]))
        else:                                    # rain / drizzle / snow
            snow = code in (71, 73, 75, 77, 85, 86)
            canvas.fade(0.6)
            if random.random() < 0.5:
                self.drops.append([random.randrange(canvas.w), 0.0])
            for d in self.drops:
                d[1] += dt * (3 if snow else 12)
                canvas.set(d[0], int(d[1]), np.array([0.9, 0.9, 1.0]) if snow else np.array([0.2, 0.5, 1.0]))
            self.drops = [d for d in self.drops if d[1] < canvas.h]
        frac = min(1.0, max(0.0, (temp + 10) / 50))       # -10 °C .. 40 °C
        fill_row(canvas, ROW_NUM, frac, hsv(0.66 - 0.66 * frac))


@effect("status_light", "busy / available light for calls: a breathing border in your status colour")
class StatusLight(Effect):
    params = {"status": param("choice", "busy", choices=["available", "busy", "away", "focus"],
                              label="Status")}
    COLORS = {"available": "#00ff60", "busy": "#ff0020", "away": "#ffb000", "focus": "#a040ff"}

    def render(self, canvas, t, dt):
        col = parse_color(self.COLORS.get(self.opt("status"), "#ff0020"))
        level = 0.55 + 0.45 * math.sin(t * 1.5)
        canvas.clear(col * 0.05)
        canvas.pixels[0, :] = canvas.pixels[-1, :] = col * level
        canvas.pixels[:, 0] = canvas.pixels[:, -1] = col * level
