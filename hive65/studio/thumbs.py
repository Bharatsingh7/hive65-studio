"""Offline renders of effects for gallery thumbnails (simulated music and typing)."""
import random

import numpy as np

from ..canvas import Canvas
from ..engine import Context


class FakeAudio:
    def __init__(self, n=16):
        self.n = n
        self.hits = {"beat": 0, "kick": 0, "snare": 0, "hat": 0}
        self.bpm, self.phase = 120.0, 0.0
        self.tick(0)

    def tick(self, t):
        x = np.linspace(0, 1, self.n)
        self.bands = np.clip(0.75 * np.exp(-x * 2.2) + 0.25 * np.abs(np.sin(x * 9 + t * 5)), 0, 1)
        beat = (t * 2) % 1
        self.level = 0.55 + 0.35 * np.exp(-beat * 5)
        self.bass = self.kick = float(np.exp(-beat * 5))
        self.mid = self.snare = float(np.exp(-((t * 2 + 0.5) % 1) * 6))
        self.treble = self.hat = float(np.exp(-((t * 4) % 1) * 8))
        self.phase = beat
        if beat < 0.05:
            for k in ("beat", "kick"):
                self.hits[k] += 1
        if ((t * 2 + 0.5) % 1) < 0.05:
            self.hits["snare"] += 1
        if ((t * 4) % 1) < 0.08:
            self.hits["hat"] += 1

    def take_beat(self):
        return False


class FakeKeys:
    def __init__(self, layout):
        self.keys = [k for k in layout.keys if k.row < 4]

    def drain(self):
        return [random.choice(self.keys).vk] if random.random() < 0.25 else []


def render_thumbnail(cls, palette=None, seconds=2.2, fps=20):
    """Return {led: rgb} after running the effect for `seconds` of simulated time."""
    if cls.category == "screen" and cls.effect_name == "movie":
        return _movie_placeholder()
    canvas = Canvas()
    ctx = Context(canvas)
    ctx._audio = FakeAudio(canvas.w)
    ctx._keys = FakeKeys(canvas.layout)
    ctx.palette = palette or []
    ctx.demo = True      # sample data; no sensors, network or microphone
    effect = cls(ctx)
    t, dt = 0.0, 1.0 / fps
    random.seed(7)
    np.random.seed(7)
    for _ in range(int(seconds * fps)):
        ctx._audio.tick(t)
        ctx.begin_frame()
        effect.render(canvas, t, dt)
        t += dt
    effect.close()
    return canvas.key_colors()


def _movie_placeholder():
    canvas = Canvas()
    y, x = np.mgrid[0:canvas.h, 0:canvas.w]
    canvas.pixels[..., 0] = 0.9 - x / canvas.w * 0.6
    canvas.pixels[..., 1] = 0.25 + y / canvas.h * 0.3
    canvas.pixels[..., 2] = x / canvas.w
    return canvas.key_colors()


class LivePreview:
    """Steps an effect frame by frame on simulated music/typing (hover previews, builder)."""

    def __init__(self, cls, palette=None, options=None):
        self.canvas = Canvas()
        self.static = cls.category == "screen" and cls.effect_name == "movie"
        ctx = self.ctx = Context(self.canvas)
        ctx._audio = FakeAudio(self.canvas.w)
        ctx._keys = FakeKeys(self.canvas.layout)
        ctx.palette = palette or []
        ctx.demo = True
        self.effect = None if self.static else cls(ctx, **(options or {}))
        self.t = 0.0

    def step(self, dt=1 / 15):
        if self.static:
            return _movie_placeholder()
        self.ctx._audio.tick(self.t)
        self.ctx.begin_frame()
        self.effect.render(self.canvas, self.t, dt)
        self.t += dt
        return self.canvas.key_colors()

    def close(self):
        if self.effect is not None:
            self.effect.close()
            self.effect = None


_CACHE = {}


def cached_thumbnail(name, palette=None):
    """{led: rgb} for a registered effect, rendered once per run."""
    from ..effects import load_all
    if name not in _CACHE:
        _CACHE[name] = render_thumbnail(load_all()[name], palette)
    return _CACHE[name]
