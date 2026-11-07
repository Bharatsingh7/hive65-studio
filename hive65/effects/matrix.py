"""Shape and motion effects that read well on the staggered 16x5 grid."""
import random

import numpy as np

from ..canvas import hsv, parse_color
from . import Effect, effect, param


@effect("life", "Conway's Game of Life on the key grid", "ambient")
class Life(Effect):
    params = {"step": param("float", 0.35, 0.05, 2, label="Seconds per generation")}

    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        self.seed()
        self.step_at = 0.0

    def seed(self):
        c = self.ctx.canvas
        self.cells = np.random.rand(c.h, c.w) < 0.35
        self.hue = random.random()
        self.history = []

    def render(self, canvas, t, dt):
        if t >= self.step_at:
            n = sum(np.roll(np.roll(self.cells, dy, 0), dx, 1)
                    for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx)
            self.cells = (n == 3) | (self.cells & (n == 2))
            key = self.cells.tobytes()
            if not self.cells.any() or key in self.history:
                self.seed()
            self.history = (self.history + [key])[-8:]
            self.step_at = t + self.opt("step")
            self.hue += 0.02
        canvas.fade(0.6)
        canvas.pixels[self.cells] = hsv(self.hue)


@effect("matrix_rain", "green digital rain", "ambient")
class MatrixRain(Effect):
    params = {"color": param("color", "#00ff40", label="Colour")}

    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        self.heads = [random.uniform(-6, 0) for _ in range(ctx.canvas.w)]
        self.speeds = [random.uniform(3, 6) for _ in range(ctx.canvas.w)]

    def render(self, canvas, t, dt):
        canvas.fade(0.75)
        color = parse_color(self.opt("color"))
        for c in range(canvas.w):
            self.heads[c] += dt * self.speeds[c]
            r = int(self.heads[c])
            if 0 <= r < canvas.h:
                canvas.pixels[r, c] = color   # the fade leaves the trail behind
            if self.heads[c] > canvas.h + random.uniform(0, 6):
                self.heads[c] = random.uniform(-4, 0)
                self.speeds[c] = random.uniform(3, 6)
