"""More typing-reactive effects."""
import random
import time

import numpy as np

from ..canvas import hsv
from . import Effect, effect, param
from ._util import blob, grid, hsv_array, ring


@effect("typing_fire", "every key press sets that key on fire; flames rise and fade")
class TypingFire(Effect):
    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        self.heat = np.zeros((ctx.canvas.h + 1, ctx.canvas.w))

    def render(self, canvas, t, dt):
        for k in self.ctx.pressed_keys():
            c0 = int(k.x - k.w / 2 + 0.5)
            for c in range(max(0, c0), min(canvas.w, int(k.x + k.w / 2 + 0.5))):
                self.heat[k.row, c] = 1.4
        h = self.heat
        rise = h[1:] * 0.55 + np.roll(h[1:], 1, 1) * 0.12 + np.roll(h[1:], -1, 1) * 0.12
        h[:-1] = np.maximum(h[:-1] * 0.82, rise * np.random.uniform(0.8, 1.0, rise.shape))
        h *= 0.93
        v = np.clip(h[:-1], 0, 1)
        canvas.pixels[..., 0] = np.clip(v * 1.5, 0, 1)
        canvas.pixels[..., 1] = np.clip(v * 1.5 - 0.5, 0, 1) * 0.75
        canvas.pixels[..., 2] = np.clip(v * 2 - 1.5, 0, 1) * 0.6


@effect("lightning", "a bolt of lightning jumps from your last key to the next")
class Lightning(Effect):
    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        self.prev, self.bolts = None, []

    def render(self, canvas, t, dt):
        for k in self.ctx.pressed_keys():
            if self.prev is not None:
                (x0, y0), (x1, y1) = self.prev, (k.x, k.y)
                steps = max(2, int(np.hypot(x1 - x0, y1 - y0) * 2))
                pts = [(x0 + (x1 - x0) * i / steps + random.uniform(-0.4, 0.4),
                        y0 + (y1 - y0) * i / steps + random.uniform(-0.5, 0.5)) for i in range(steps + 1)]
                self.bolts.append([pts, 1.0])
            self.prev = (k.x, k.y)
        canvas.fade(0.5)
        for b in self.bolts:
            for px, py in b[0]:
                canvas.add(int(px), int(py), np.array([0.6, 0.7, 1.0]) * b[1] + (b[1] > 0.7) * 0.4)
            b[1] -= dt * 3
        self.bolts = [b for b in self.bolts if b[1] > 0]


@effect("splash", "keys drop into water: ripples spread and interfere")
class Splash(Effect):
    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        h, w = ctx.canvas.h, ctx.canvas.w
        self.cur = np.zeros((h, w))
        self.prev = np.zeros((h, w))

    def render(self, canvas, t, dt):
        for k in self.ctx.pressed_keys():
            c, r = min(canvas.w - 1, int(k.x)), k.row
            self.cur[r, c] += 2.5
        # classic 2D water ripple
        nxt = (np.roll(self.cur, 1, 0) + np.roll(self.cur, -1, 0) +
               np.roll(self.cur, 1, 1) + np.roll(self.cur, -1, 1)) / 2 - self.prev
        nxt *= 0.9
        self.prev, self.cur = self.cur, nxt
        v = np.clip(np.abs(self.cur), 0, 1)
        canvas.pixels[:] = hsv_array(0.55 + self.cur * 0.08, 0.8, v) + np.array([0, 0.01, 0.03])


@effect("wpm_meter", "typing speed bar: faster typing fills the board and heats the colour")
class WPMMeter(Effect):
    params = {"max_wpm": param("float", 120.0, 40, 250, label="WPM for a full board")}

    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        self.times = []
        self.shown = 0.0

    def render(self, canvas, t, dt):
        now = time.time()
        self.times += [now] * len(self.ctx.pressed_keys())
        self.times = [x for x in self.times if now - x < 6]
        wpm = len(self.times) / 5 * 10       # 5 chars per word, 6 s window
        frac = min(1.0, wpm / self.opt("max_wpm"))
        self.shown += (frac - self.shown) * min(1, dt * 4)
        x, y = grid(canvas)
        lit = np.clip(self.shown * canvas.w - (x - 0.5), 0, 1)
        hue = 0.6 - 0.6 * self.shown          # blue (slow) -> red (blazing)
        canvas.pixels[:] = hsv_array(hue - x * 0.01, 1, lit * (0.6 + 0.4 * (y < 4)))


@effect("combo", "fast streaks build a combo: colours escalate and burst on a break")
class Combo(Effect):
    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        self.combo, self.last, self.burst = 0, 0.0, 0.0
        self.glow = {}

    def render(self, canvas, t, dt):
        presses = self.ctx.pressed_keys()
        if presses:
            self.combo = self.combo + len(presses) if t - self.last < 0.35 else 1
            self.last = t
        elif t - self.last > 0.8 and self.combo >= 15:
            self.burst, self.combo = 1.0, 0
        level = min(1.0, self.combo / 40)
        for k in presses:
            self.glow[k.name] = 1.0
        canvas.clear(hsv(0.6 - level * 0.6) * level * 0.35)
        for name, g in list(self.glow.items()):
            canvas.set_key(name, hsv(0.6 - level * 0.6) * g + 0.3 * level)
            self.glow[name] = g - dt * 2
            if self.glow[name] <= 0:
                del self.glow[name]
        if self.burst > 0:
            x, y = grid(canvas)
            canvas.pixels[:] = np.maximum(canvas.pixels, hsv_array(x / canvas.w + t, 1, 1) * self.burst)
            self.burst -= dt * 1.5


@effect("ghost_keys", "your recent typing glows and slowly fades, like after-images")
class GhostKeys(Effect):
    params = {"fade": param("float", 4.0, 0.5, 15, label="Seconds to fade")}

    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        self.keys = {}

    def render(self, canvas, t, dt):
        for k in self.ctx.pressed_keys():
            self.keys[k.name] = (1.0, (t * 0.1) % 1)
        canvas.clear()
        for name, (g, hue) in list(self.keys.items()):
            canvas.set_key(name, hsv(hue + (1 - g) * 0.3) * g ** 1.5)
            g -= dt / self.opt("fade")
            if g <= 0:
                del self.keys[name]
            else:
                self.keys[name] = (g, hue)


@effect("sparks", "each key press explodes into sparks that fly and fall")
class Sparks(Effect):
    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        self.p = []

    def render(self, canvas, t, dt):
        for k in self.ctx.pressed_keys():
            hue = random.random()
            for _ in range(10):
                a = random.uniform(0, 2 * np.pi)
                s = random.uniform(3, 9)
                self.p.append([k.x, k.y, np.cos(a) * s, np.sin(a) * s - 3, 1.0, hue])
        canvas.fade(0.6)
        for p in self.p:
            p[3] += 14 * dt
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[4] -= dt * 1.4
            canvas.add(int(p[0]), int(p[1]), hsv(p[5], 0.7) * max(0, p[4]))
        self.p = [p for p in self.p if p[4] > 0 and 0 <= p[0] < canvas.w and p[1] < canvas.h + 1]


@effect("crosshair", "the pressed key's row and column light up like a targeting cross")
class Crosshair(Effect):
    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        self.hits = []

    def render(self, canvas, t, dt):
        for k in self.ctx.pressed_keys():
            self.hits.append([k.x, k.row, 1.0, random.random()])
        canvas.fade(0.7)
        x, y = grid(canvas)
        for h in self.hits:
            line = ((np.abs(x - h[0]) < 0.6) | (y.astype(int) == h[1])).astype(float)
            canvas.pixels[:] = np.maximum(canvas.pixels, hsv(h[3])[None, None] * (line * h[2])[..., None])
            h[2] -= dt * 2.5
        self.hits = [h for h in self.hits if h[2] > 0]


@effect("paint", "every key press splashes paint that blends and lingers")
class Paint(Effect):
    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        self.canvas_state = np.zeros((ctx.canvas.h, ctx.canvas.w, 3))

    def render(self, canvas, t, dt):
        x, y = grid(canvas)
        for k in self.ctx.pressed_keys():
            col = hsv(random.random())
            b = blob(x, y, k.x, k.y + 0.5, 2.2, 1.0)[..., None]
            self.canvas_state = self.canvas_state * (1 - b) + col * b
        self.canvas_state *= 1 - dt * 0.05
        canvas.pixels[:] = self.canvas_state


@effect("shockwave", "a bright ring blasts out from every key you hit")
class Shockwave(Effect):
    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        self.w = []

    def render(self, canvas, t, dt):
        for k in self.ctx.pressed_keys():
            self.w.append([k.x, k.y + 0.5, t, random.random()])
        self.w = [w for w in self.w if t - w[2] < 0.9]
        x, y = grid(canvas)
        canvas.clear()
        for cx, cy, born, hue in self.w:
            age = t - born
            canvas.pixels[:] = np.maximum(canvas.pixels, hsv(hue)[None, None] *
                                          (ring(x, y, cx, cy, age * 16, 1.2) * (1 - age / 0.9))[..., None])
