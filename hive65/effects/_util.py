"""Vectorised helpers shared by effects."""
import threading

import numpy as np


class StaticPoller:
    """Stand-in used for gallery previews: fixed sample data, no thread."""

    def __init__(self, value):
        self.value, self.error = value, None

    def stop(self):
        pass


class Poller(threading.Thread):
    """Calls fn() every `interval` seconds off the render thread."""

    def __init__(self, fn, interval, default=None):
        super().__init__(daemon=True)
        self.fn, self.interval = fn, interval
        self.value, self.error = default, None
        self._stop_ev = threading.Event()
        self.start()

    def run(self):
        while not self._stop_ev.is_set():
            try:
                self.value = self.fn()
                self.error = None
            except Exception as e:
                self.error = str(e) or type(e).__name__
            self._stop_ev.wait(self.interval)

    def stop(self):
        self._stop_ev.set()


def grid(canvas):
    """Cell-centre coordinates (x, y) as h x w arrays, in key units."""
    y, x = np.mgrid[0:canvas.h, 0:canvas.w]
    return x + 0.5, y + 0.5


def hsv_array(h, s=1.0, v=1.0):
    """Vectorised HSV -> RGB. h, s, v broadcastable arrays; returns (..., 3)."""
    h, s, v = np.broadcast_arrays(np.asarray(h, dtype=float) % 1.0,
                                  np.asarray(s, dtype=float), np.asarray(v, dtype=float))
    i = np.floor(h * 6).astype(int) % 6
    f = h * 6 - np.floor(h * 6)
    p, q, t = v * (1 - s), v * (1 - s * f), v * (1 - s * (1 - f))
    r = np.choose(i, [v, q, p, p, t, v])
    g = np.choose(i, [t, v, v, q, p, p])
    b = np.choose(i, [p, p, t, v, v, q])
    return np.stack([r, g, b], axis=-1)


def blob(x, y, cx, cy, radius, sharp=2.0):
    """Soft round falloff 0..1 centred on (cx, cy)."""
    d = np.hypot(x - cx, (y - cy) * 1.15) / max(radius, 1e-3)
    return np.clip(1 - d, 0, 1) ** sharp


def ring(x, y, cx, cy, radius, width=0.9):
    d = np.hypot(x - cx, (y - cy) * 1.15)
    return np.clip(1 - np.abs(d - radius) / width, 0, 1)


def noise2(x, y, t, seed=0.0):
    """Cheap smooth pseudo-noise from layered sines (no extra deps)."""
    return (np.sin(x * 0.9 + t * 1.1 + seed) * np.cos(y * 1.3 - t * 0.7 + seed * 2)
            + np.sin((x + y) * 0.55 + t * 0.6 + seed * 3)
            + np.sin(np.hypot(x - 7 + seed, y - 2) * 0.8 - t)) / 3
