"""Notification animations drawn over whatever effect is running."""
import numpy as np

from .canvas import hsv, parse_color
from .engine import Overlay


def _grid(ov):
    h, w = ov.canvas.h, ov.canvas.w
    y, x = np.mgrid[0:h, 0:w]
    return x + 0.5, y + 0.5


class LevelOverlay(Overlay):
    """Volume / brightness: the board fills left to right to the new level."""

    duration = 1.8

    def __init__(self, ctx, kind, level, muted=False):
        super().__init__(ctx)
        self.key = kind
        self.kind, self.level, self.muted = kind, max(0.0, min(1.0, level)), muted

    def render(self, t, dt):
        c = self.canvas
        env = self.fade(t)
        x, y = _grid(self)
        if self.muted:
            stripes = ((x + y + t * 6) % 3 < 1.2).astype(float)
            c.pixels[:] = np.array([1.0, 0.0, 0.05]) * (0.35 + 0.65 * stripes)[..., None]
            self.alpha[:] = env
            return
        fill = self.level * c.w
        # grow quickly to the level so the change is felt, not just shown
        fill *= min(1.0, t / 0.25)
        lit = np.clip(fill - (x - 0.5), 0, 1)
        if self.kind == "brightness":
            col = np.stack([np.ones_like(x), 0.55 + 0.45 * x / c.w, 0.15 + 0.85 * (x / c.w) ** 2], -1)
        else:
            col = np.stack([hsv(0.33 - 0.33 * (xx / c.w)) for xx in x[0]])[None].repeat(c.h, 0)
        edge = np.exp(-((x - fill) ** 2) / 0.4)[..., None]   # bright leading edge
        c.pixels[:] = col * lit[..., None] + edge * 0.6
        dark = np.array([0.02, 0.02, 0.03])
        c.pixels[:] = np.where(lit[..., None] > 0, c.pixels, dark)
        self.alpha[:] = env * 0.92


class PingOverlay(Overlay):
    """App notification: a ring bursts from the centre in the app's colour, twice."""

    duration = 1.6

    def __init__(self, ctx, color="#00b0ff"):
        super().__init__(ctx)
        self.color = parse_color(color) if isinstance(color, str) else np.asarray(color, float)

    def render(self, t, dt):
        c = self.canvas
        x, y = _grid(self)
        d = np.hypot(x - c.w / 2, (y - c.h / 2) * 1.6)
        glow = np.zeros_like(d)
        for start in (0.0, 0.45):
            age = t - start
            if age > 0:
                glow = np.maximum(glow, np.clip(1.6 - np.abs(d - age * 14), 0, 1) * max(0, 1 - age / 1.2))
        flash = max(0.0, 1 - t / 0.15) * 0.6
        c.pixels[:] = self.color * np.clip(glow + flash, 0, 1)[..., None]
        self.alpha[:] = np.clip(glow * 1.2 + flash, 0, 1) * self.fade(t)


class SweepOverlay(Overlay):
    """Media track change: bands of the album/palette colours sweep across."""

    duration = 1.4
    key = "media"

    def __init__(self, ctx, colors=None):
        super().__init__(ctx)
        self.colors = [np.asarray(c, float) for c in (colors or [hsv(i / 5) for i in range(5)])]

    def render(self, t, dt):
        c = self.canvas
        x, y = _grid(self)
        pos = t / self.duration * (c.w + 8) - 4
        band = (pos - x + y * 0.4)
        idx = np.clip((band * 0.8).astype(int), 0, len(self.colors) - 1)
        c.pixels[:] = np.array(self.colors)[idx]
        self.alpha[:] = np.clip(1 - np.abs(band - 2) / 3, 0, 1) * self.fade(t, 0.05, 0.3)


class BorderOverlay(Overlay):
    """Caps Lock and other toggles: a light chases around the board's edge."""

    duration = 1.0

    def __init__(self, ctx, color="#ffffff", key=None):
        super().__init__(ctx)
        self.color = parse_color(color) if isinstance(color, str) else np.asarray(color, float)
        self.key = key
        h, w = self.canvas.h, self.canvas.w
        self.path = ([(0, c) for c in range(w)] + [(r, w - 1) for r in range(1, h)] +
                     [(h - 1, c) for c in range(w - 2, -1, -1)] + [(r, 0) for r in range(h - 2, 0, -1)])

    def render(self, t, dt):
        n = len(self.path)
        head = t / self.duration * n * 1.5
        self.canvas.clear()
        self.alpha[:] = 0
        for i, (r, c) in enumerate(self.path):
            a = max(0.0, 1 - ((head - i) % n) / 8) if head >= i else 0.0
            self.canvas.pixels[r, c] = self.color
            self.alpha[r, c] = a * self.fade(t)


class PulseOverlay(Overlay):
    """Battery low / warnings: the whole board pulses a colour a few times."""

    duration = 2.0

    def __init__(self, ctx, color="#ff4000", pulses=3, key=None):
        super().__init__(ctx)
        self.color = parse_color(color) if isinstance(color, str) else np.asarray(color, float)
        self.pulses, self.key = pulses, key

    def render(self, t, dt):
        p = 0.5 - 0.5 * np.cos(2 * np.pi * self.pulses * t / self.duration)
        self.canvas.clear(self.color)
        self.alpha[:] = p * self.fade(t)


class ConfettiOverlay(Overlay):
    """Celebration (timer done etc.): random keys pop in random colours."""

    duration = 2.5

    def render(self, t, dt):
        c = self.canvas
        if not hasattr(self, "life"):
            self.life = np.zeros((c.h, c.w))
            self.hue = np.random.rand(c.h, c.w)
        self.life *= 0.85
        pop = np.random.rand(c.h, c.w) < 0.12
        self.life[pop] = 1
        self.hue[pop] = np.random.rand(int(pop.sum()))
        for r in range(c.h):
            for col in range(c.w):
                c.pixels[r, col] = hsv(self.hue[r, col])
        self.alpha[:] = self.life * self.fade(t)


def make(ctx, kind, value=None, **meta):
    """Build an overlay from an event (also used by `hive65 notify`)."""
    if kind in ("volume", "brightness"):
        return LevelOverlay(ctx, kind, float(value if value is not None else 0.5),
                            bool(meta.get("muted")))
    if kind == "app":
        return PingOverlay(ctx, meta.get("color", "#00b0ff"))
    if kind == "media":
        return SweepOverlay(ctx, meta.get("colors"))
    if kind == "caps":
        return BorderOverlay(ctx, "#ffffff" if value else "#2050ff", key="caps")
    if kind == "battery":
        return PulseOverlay(ctx, "#ff3000", key="battery")
    if kind == "mic":
        return PulseOverlay(ctx, "#ff0030" if value else "#00ff60", pulses=2, key="mic")
    if kind == "done":
        return ConfettiOverlay(ctx)
    if kind == "flash":
        return PulseOverlay(ctx, meta.get("color", "#ffffff"), pulses=1)
    raise ValueError(f"unknown notification kind '{kind}'")
