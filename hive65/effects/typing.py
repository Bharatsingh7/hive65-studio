"""Effects that react to what you type."""
import random

import numpy as np

from ..canvas import hsv
from . import Effect, effect


@effect("ripple", "every key press sends out a coloured ring")
class Ripple(Effect):
    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        self.rings = []  # (x, y, birth, hue)

    def render(self, canvas, t, dt):
        for k in self.ctx.pressed_keys():
            self.rings.append((k.x, k.y, t, random.random()))
        self.rings = [r for r in self.rings if t - r[2] < 1.2][-12:]
        canvas.fade(0.55)
        y, x = np.mgrid[0:canvas.h, 0:canvas.w]
        for kx, ky, born, hue in self.rings:
            age = t - born
            d = np.hypot(x + 0.5 - kx, (y + 0.5 - ky) * 1.2)
            glow = np.clip(1 - np.abs(d - age * 9), 0, 1) * (1 - age / 1.2)
            canvas.pixels += glow[..., None] * hsv(hue)
        np.clip(canvas.pixels, 0, 1, out=canvas.pixels)


@effect("heatmap", "keys glow hotter the more you use them")
class Heatmap(Effect):
    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        self.heat = {}

    def render(self, canvas, t, dt):
        for k in self.ctx.pressed_keys():
            self.heat[k.name] = min(1.0, self.heat.get(k.name, 0) + 0.15)
        canvas.clear((0, 0, 0.04))
        for name, h in list(self.heat.items()):
            canvas.set_key(name, hsv(0.66 - 0.66 * h, 1, 0.25 + 0.75 * h))
            self.heat[name] = h * (1 - dt * self.opt("cool", 0.05))


@effect("reactive", "pressed keys light up white and fade to a base colour")
class Reactive(Effect):
    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        self.glow = {}

    def render(self, canvas, t, dt):
        for k in self.ctx.pressed_keys():
            self.glow[k.name] = 1.0
        canvas.clear(hsv(t * 0.02, 1, 0.15))
        for name, g in list(self.glow.items()):
            canvas.set_key(name, np.array([1.0, 1.0, 1.0]) * g + hsv(t * 0.02, 1, 0.15) * (1 - g))
            self.glow[name] = g - dt * 1.5
            if self.glow[name] <= 0:
                del self.glow[name]
