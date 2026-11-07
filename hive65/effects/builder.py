"""No-code effects made in the Studio's Effect Builder.

A design is a dict: {name, pattern, colors, speed, scale, direction, reaction}.
Each saved design is registered as a real effect (category "custom").
"""
import random

import numpy as np

from ..canvas import parse_color
from . import REGISTRY, Effect
from ._util import grid

PATTERNS = ("wave", "radial", "noise", "gradient", "sparkle", "stripes", "orbit", "rain")
REACTIONS = ("none", "bass", "beat", "typing", "volume")
DIRECTIONS = ("right", "left", "up", "down", "out", "in")

DEFAULT_DESIGN = {"name": "my_effect", "pattern": "wave", "colors": ["#ff0080", "#00e5ff", "#7c3aed"],
                  "speed": 1.0, "scale": 1.0, "direction": "right", "reaction": "none"}


def _gradient(colors, x):
    """Sample a looping multi-colour gradient at positions x (0..1, wraps)."""
    cols = np.array(colors)
    x = np.asarray(x) % 1.0 * len(cols)
    i = np.floor(x).astype(int)
    f = (x - i)[..., None]
    return cols[i % len(cols)] * (1 - f) + cols[(i + 1) % len(cols)] * f


class BuilderEffect(Effect):
    design = DEFAULT_DESIGN

    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        d = dict(DEFAULT_DESIGN, **self.design, **opts)
        self.d = d
        self.colors = [parse_color(c) for c in d["colors"]] or [np.array([1.0, 1.0, 1.0])]
        self.phase = 0.0
        self.kick = 0.0
        self.sparks = np.zeros((ctx.canvas.h, ctx.canvas.w))
        self.ripples = []

    def _energy(self, t, dt):
        r = self.d["reaction"]
        if r == "none":
            return 1.0, 1.0
        if r == "typing":
            for k in self.ctx.pressed_keys():
                self.ripples.append((k.x, k.y + 0.5, t))
                self.kick = 1.0
            self.kick = max(0.0, self.kick - dt * 2)
            return 0.35 + 0.65 * self.kick, 1 + self.kick * 2
        a = self.ctx.audio
        if r == "beat":
            if self.hit("beat"):
                self.kick = 1.0
            self.kick = max(0.0, self.kick - dt * 3)
            return 0.25 + 0.75 * self.kick, 1 + self.kick * 2
        if r == "bass":
            return 0.15 + 0.85 * a.bass, 1 + a.bass * 2
        return 0.15 + 0.85 * a.level, 1 + a.level * 2       # volume

    def render(self, canvas, t, dt):
        d = self.d
        level, boost = self._energy(t, dt)
        self.phase += dt * d["speed"] * boost
        p, sc = self.phase, max(0.1, d["scale"])
        x, y = grid(canvas)
        w, h = canvas.w, canvas.h
        dirn = d["direction"]
        if dirn in ("right", "left"):
            axis, sign = x / w, (1 if dirn == "left" else -1)
        elif dirn in ("up", "down"):
            axis, sign = y / h, (1 if dirn == "up" else -1)
        else:
            axis = np.hypot(x - w / 2, (y - h / 2) * 1.6) / w
            sign = -1 if dirn == "out" else 1
        pat = d["pattern"]
        if pat == "wave":
            pos = axis / sc + sign * p * 0.3
            rgb = _gradient(self.colors, pos)
            rgb = rgb * (0.55 + 0.45 * np.sin((axis * 6 / sc + sign * p * 2)))[..., None]
        elif pat == "radial":
            r = np.hypot(x - w / 2, (y - h / 2) * 1.6) / w
            rgb = _gradient(self.colors, r * 2 / sc + sign * p * 0.4)
        elif pat == "noise":
            n = (np.sin(x * 0.7 / sc + p) * np.cos(y * 1.1 / sc - p * 0.7)
                 + np.sin((x + y) * 0.4 / sc + p * 0.5)) / 2
            rgb = _gradient(self.colors, n * 0.5 + 0.5 + p * 0.05)
        elif pat == "gradient":
            rgb = _gradient(self.colors, axis / sc * 0.999 + sign * p * 0.05)
        elif pat == "stripes":
            band = np.floor((axis / sc * 6 + sign * p) % len(self.colors)).astype(int)
            rgb = np.array(self.colors)[band % len(self.colors)]
        elif pat == "orbit":
            rgb = np.zeros((h, w, 3))
            for i, col in enumerate(self.colors):
                a = p * 1.5 + i * 2 * np.pi / len(self.colors)
                cx, cy = w / 2 + np.cos(a) * w * 0.35 * sc, h / 2 + np.sin(a) * h * 0.35
                b = np.clip(1 - np.hypot(x - cx, (y - cy) * 1.3) / 2.2, 0, 1) ** 1.5
                rgb = np.maximum(rgb, col * b[..., None])
        elif pat == "rain":
            self.sparks *= 0.8
            if random.random() < 0.6 * boost:
                self.sparks[0, random.randrange(w)] = 1.0
            self.sparks[1:] = np.maximum(self.sparks[1:], self.sparks[:-1] * 0.95)
            rgb = _gradient(self.colors, x / w + p * 0.05) * self.sparks[..., None]
        else:   # sparkle
            self.sparks *= 0.85
            for _ in range(int(2 * boost)):
                self.sparks[random.randrange(h), random.randrange(w)] = 1.0
            rgb = _gradient(self.colors, x / w + p * 0.05) * self.sparks[..., None]
        out = rgb * level
        if self.ripples:   # typing reaction: rings of the first colour
            self.ripples = [r for r in self.ripples if t - r[2] < 0.8]
            for cx, cy, born in self.ripples:
                dist = np.hypot(x - cx, (y - cy) * 1.2)
                ring = np.clip(1 - np.abs(dist - (t - born) * 14), 0, 1) * (1 - (t - born) / 0.8)
                out = np.maximum(out, self.colors[0] * ring[..., None])
        canvas.pixels[:] = np.clip(out, 0, 1)


def make_class(design):
    name = design["name"]
    cls = type(f"Builder_{name}", (BuilderEffect,), {"design": dict(design), "category": "custom",
                                                    "params": {}})
    cls.effect_name = name
    cls.description = f"your effect: {design['pattern']} · {design['reaction']} reaction"
    return cls


def register_all(designs):
    """(Re)register every saved design; drop removed ones."""
    for n in [n for n, c in REGISTRY.items() if getattr(c, "category", "") == "custom"]:
        del REGISTRY[n]
    for d in designs:
        if d.get("name"):
            REGISTRY[d["name"]] = make_class(d)
