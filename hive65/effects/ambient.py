import numpy as np

from ..canvas import hsv, parse_color
from . import Effect, effect


@effect("solid", "one colour on every key (--color)")
class Solid(Effect):
    def render(self, canvas, t, dt):
        canvas.clear(parse_color(self.opt("color", "white")))


@effect("rainbow", "smooth rainbow wave (--speed, --angle)")
class Rainbow(Effect):
    def render(self, canvas, t, dt):
        speed, angle = self.opt("speed", 0.25), np.radians(self.opt("angle", 0.0))
        for r in range(canvas.h):
            for c in range(canvas.w):
                pos = (c * np.cos(angle) + r * np.sin(angle)) / canvas.w
                canvas.pixels[r, c] = hsv(pos - t * speed)


@effect("plasma", "flowing colour plasma")
class Plasma(Effect):
    def render(self, canvas, t, dt):
        y, x = np.mgrid[0:canvas.h, 0:canvas.w]
        v = (np.sin(x / 2.0 + t) + np.sin((y + t) / 1.5) + np.sin((x + y + t * 2) / 3.0)
             + np.sin(np.hypot(x - 8, y - 2) / 2.0 - t)) / 4
        for r in range(canvas.h):
            for c in range(canvas.w):
                canvas.pixels[r, c] = hsv(v[r, c] * 0.5 + t * 0.05)


@effect("fire", "flickering fire rising from the bottom row")
class Fire(Effect):
    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        self.heat = np.zeros((ctx.canvas.h + 1, ctx.canvas.w))

    def render(self, canvas, t, dt):
        h = self.heat
        h[-1] = np.random.uniform(0.5, 1.0, canvas.w)
        h[:-1] = (h[1:] * 0.6 + np.roll(h[1:], 1, axis=1) * 0.2
                  + np.roll(h[1:], -1, axis=1) * 0.2) * np.random.uniform(0.75, 0.95, h[:-1].shape)
        v = h[:-1]
        canvas.pixels[..., 0] = np.clip(v * 1.6, 0, 1)
        canvas.pixels[..., 1] = np.clip(v * 1.6 - 0.6, 0, 1) * 0.7
        canvas.pixels[..., 2] = np.clip(v * 2 - 1.6, 0, 1) * 0.5


@effect("breathe", "slow breathing in one colour (--color, --period)")
class Breathe(Effect):
    def render(self, canvas, t, dt):
        level = (1 - np.cos(2 * np.pi * t / self.opt("period", 4.0))) / 2
        canvas.clear(parse_color(self.opt("color", "cyan")) * level)
