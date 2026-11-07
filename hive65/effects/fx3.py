"""Effect pack 3: fluid, glitch, hyperspace, terrain, city, fireplace and more."""
import random

import numpy as np

from ..canvas import hsv
from . import Effect, effect, param
from ._util import blob, grid, hsv_array, noise2


# ------------------------------------------------------------------ typing
@effect("fluid", "colourful smoke you stir by typing; it swirls and slowly settles", "typing")
class Fluid(Effect):
    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        h, w = ctx.canvas.h, ctx.canvas.w
        self.dye = np.zeros((h, w, 3))
        self.vx = np.zeros((h, w))
        self.vy = np.zeros((h, w))

    def render(self, canvas, t, dt):
        h, w = self.vx.shape
        x, y = grid(canvas)
        for k in self.ctx.pressed_keys():
            b = blob(x, y, k.x, k.y + 0.5, 2.0, 1.0)
            ang = random.uniform(0, 2 * np.pi)
            self.vx += b * np.cos(ang) * 6
            self.vy += b * np.sin(ang) * 3
            self.dye = np.maximum(self.dye, hsv(random.random())[None, None] * b[..., None])
        # ambient curl so it never fully stops
        self.vx += np.sin(y * 1.3 + t) * 0.2 * dt
        self.vy += np.cos(x * 0.7 - t) * 0.1 * dt
        # semi-Lagrangian advection
        sx = np.clip(x - 0.5 - self.vx * dt, 0, w - 1)
        sy = np.clip(y - 0.5 - self.vy * dt, 0, h - 1)
        x0, y0 = np.floor(sx).astype(int), np.floor(sy).astype(int)
        x1, y1 = np.minimum(x0 + 1, w - 1), np.minimum(y0 + 1, h - 1)
        fx, fy = (sx - x0)[..., None], (sy - y0)[..., None]
        d = self.dye
        self.dye = ((d[y0, x0] * (1 - fx) + d[y0, x1] * fx) * (1 - fy)
                    + (d[y1, x0] * (1 - fx) + d[y1, x1] * fx) * fy)
        # diffuse velocity a little and damp
        for v in (self.vx, self.vy):
            v[:] = (v * 0.6 + (np.roll(v, 1, 0) + np.roll(v, -1, 0) + np.roll(v, 1, 1) + np.roll(v, -1, 1)) * 0.1)
            v *= 0.97
        self.dye *= 0.992
        canvas.pixels[:] = np.clip(self.dye, 0, 1)


@effect("rain_window", "raindrops trickle down glass; typing throws splashes", "typing")
class RainWindow(Effect):
    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        self.drops = []      # [x, y, speed]
        self.splash = []     # [x, y, born]

    def render(self, canvas, t, dt):
        x, y = grid(canvas)
        canvas.clear(np.array([0.02, 0.04, 0.09]))
        city = (np.sin(x * 2.1) * 0.5 + 0.5) * (y > 2.5) * 0.12
        canvas.pixels[:] += np.stack([city, city * 0.6, city * 0.2], -1)   # blurry lights behind
        if random.random() < 0.15:
            self.drops.append([random.uniform(0, canvas.w), 0.0, random.uniform(0.5, 1.5)])
        for d in self.drops:
            d[1] += dt * d[2] * (1 + d[1] * 0.4)
            d[0] += np.sin(t * 3 + d[2]) * dt * 0.3
            canvas.pixels[:] = np.maximum(canvas.pixels, np.array([0.5, 0.75, 1.0]) *
                                          blob(x, y, d[0], d[1], 0.9, 1.5)[..., None])
        self.drops = [d for d in self.drops if d[1] < canvas.h + 1]
        for k in self.ctx.pressed_keys():
            self.splash.append([k.x, k.y + 0.5, t])
        self.splash = [s for s in self.splash if t - s[2] < 0.5]
        for sx, sy, born in self.splash:
            a = t - born
            r = np.clip(1 - np.abs(np.hypot(x - sx, (y - sy) * 1.3) - a * 8) / 0.8, 0, 1) * (1 - a / 0.5)
            canvas.pixels[:] = np.maximum(canvas.pixels, np.array([0.7, 0.9, 1.0]) * r[..., None])


@effect("cyber_trail", "each key press sends neon light racing along its row like a circuit", "typing")
class CyberTrail(Effect):
    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        self.runners = []   # [x, row, dir, hue, life]

    def render(self, canvas, t, dt):
        for k in self.ctx.pressed_keys():
            hue = random.choice([0.5, 0.83, 0.12])
            for d in (-1, 1):
                self.runners.append([k.x, k.row, d, hue, 1.0])
        canvas.fade(0.78)
        for r in self.runners:
            r[0] += r[2] * dt * 22
            if random.random() < 0.04:          # turn onto a neighbouring row like a trace
                r[1] = int(np.clip(r[1] + random.choice([-1, 1]), 0, canvas.h - 1))
            r[4] -= dt * 0.9
            canvas.add(int(r[0]), int(r[1]), hsv(r[3]) * max(0.0, r[4]) + 0.15)
        self.runners = [r for r in self.runners if r[4] > 0 and -1 <= r[0] <= canvas.w + 1][-40:]


# ------------------------------------------------------------------ music
@effect("glitch", "cyberpunk glitch: RGB-split slices that tear apart on every beat", "music")
class Glitch(Effect):
    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        self.burst = 0.0

    def render(self, canvas, t, dt):
        a = self.ctx.audio
        if self.hit("kick") or self.hit("snare"):
            self.burst = 1.0
        self.burst = max(0.0, self.burst - dt * 3)
        x, y = grid(canvas)
        base = hsv_array(0.85 + 0.15 * np.sin(x * 0.3 + t), 1, 0.25 + 0.4 * a.level)
        out = base.copy()
        shift = int(round(self.burst * 3))
        out[..., 0] = np.roll(base[..., 0], shift, axis=1)       # red slides right
        out[..., 2] = np.roll(base[..., 2], -shift, axis=1)      # blue slides left
        if self.burst > 0.2:
            for _ in range(int(self.burst * 4)):                 # torn horizontal slices
                r = random.randrange(canvas.h)
                out[r] = np.roll(out[r], random.randint(-4, 4), axis=0)
                out[r] = np.maximum(out[r], np.array([0.0, 1.0, 0.9]) * random.random() * self.burst)
        if random.random() < 0.02 + self.burst * 0.2:            # stray white noise pixels
            out[random.randrange(canvas.h), random.randrange(canvas.w)] = 1.0
        canvas.pixels[:] = np.clip(out, 0, 1)


@effect("warp_speed", "hyperspace: stars stream from the centre, faster with the bass", "music")
class WarpSpeed(Effect):
    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        self.stars = [self._new() for _ in range(26)]

    @staticmethod
    def _new():
        a = random.uniform(0, 2 * np.pi)
        return [a, random.uniform(0, 0.5), random.uniform(0.6, 1.4), random.choice([0.55, 0.6, 0.0, 0.8])]

    def render(self, canvas, t, dt):
        a = self.ctx.audio
        speed = 2 + a.bass * 16 + (8 if self.hit("kick") else 0)
        canvas.fade(0.55 + 0.3 * (1 - a.bass))
        cx, cy = canvas.w / 2, canvas.h / 2
        for s in self.stars:
            s[1] += dt * speed * s[2] * (0.3 + s[1])
            px, py = cx + np.cos(s[0]) * s[1] * 2.4, cy + np.sin(s[0]) * s[1] * 0.9
            if not (0 <= px < canvas.w and 0 <= py < canvas.h):
                s[:] = self._new()
                continue
            canvas.add(int(px), int(py), hsv(s[3], 0.4) * min(1.0, 0.3 + s[1] * 0.4))


@effect("audio_terrain", "a mountain landscape scrolls past, shaped by the music", "music")
class AudioTerrain(Effect):
    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        self.heights = np.zeros(ctx.canvas.w)
        self.acc = 0.0

    def render(self, canvas, t, dt):
        a = self.ctx.audio
        self.acc += dt
        if self.acc > 0.08:
            self.acc = 0.0
            self.heights = np.roll(self.heights, -1)
            self.heights[-1] = 0.6 * self.heights[-2] + 0.4 * (a.bass * 0.7 + a.mid * 0.5) * canvas.h
        x, y = grid(canvas)
        top = canvas.h - self.heights[None, :]
        ground = np.clip(y - top + 0.5, 0, 1)
        snow = np.clip(1 - np.abs(y - top) * 1.5, 0, 1) * (self.heights[None, :] > canvas.h * 0.6)
        sky = hsv_array(0.7 - y / canvas.h * 0.1, 0.8, 0.12 + 0.2 * a.treble)
        land = hsv_array(0.3 - (canvas.h - y) * 0.06, 0.9, 0.9)
        canvas.pixels[:] = sky * (1 - ground[..., None]) + land * ground[..., None] + snow[..., None] * 0.8


@effect("equalizer_city", "a night skyline whose windows flicker with the mids and highs", "music")
class EqualizerCity(Effect):
    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        rng = np.random.default_rng(3)
        self.tops = rng.integers(1, 4, ctx.canvas.w)
        self.windows = rng.random((ctx.canvas.h, ctx.canvas.w))

    def render(self, canvas, t, dt):
        a = self.ctx.audio
        x, y = grid(canvas)
        canvas.pixels[:] = hsv_array(0.68, 0.9, 0.06 + 0.2 * (1 - y / canvas.h) * a.bass)
        building = (y - 0.5) >= self.tops[None, :]
        band = np.interp(x / canvas.w, np.linspace(0, 1, len(a.bands)), a.bands)
        lit = building & (self.windows < band * 1.1)
        canvas.pixels[building] = np.array([0.05, 0.05, 0.08])
        warm = hsv_array(0.1 + self.windows * 0.05, 0.8, 0.9)
        canvas.pixels[lit] = warm[lit]
        if self.hit("hat"):
            self.windows = np.random.default_rng().random(self.windows.shape)


# ------------------------------------------------------------------ ambient
@effect("lava_flow", "a slow river of lava with a dark crust breaking apart", "ambient")
class LavaFlow(Effect):
    def render(self, canvas, t, dt):
        x, y = grid(canvas)
        n = noise2(x - t * 1.2, y, t * 0.4)
        crust = np.clip((n - 0.1) * 3, 0, 1)
        heat = np.clip(0.9 - crust + 0.15 * np.sin(x - t * 3), 0, 1)
        canvas.pixels[:] = np.stack([heat, heat ** 2 * 0.55, heat ** 5 * 0.2], -1) + crust[..., None] * 0.03


@effect("northern_storm", "aurora curtains torn by flashes of lightning", "ambient")
class NorthernStorm(Effect):
    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        self.flash = 0.0

    def render(self, canvas, t, dt):
        x, y = grid(canvas)
        curtain = np.sin(x * 0.5 + t * 0.8 + np.sin(x * 0.2 - t) * 2) * 0.5 + 0.5
        band = np.clip(1.2 - np.abs(y - 1.0 - curtain * 2.5) / 1.4, 0, 1) ** 1.6
        canvas.pixels[:] = hsv_array(0.38 + 0.3 * np.sin(x * 0.15 + t * 0.3), 0.9, band)
        if random.random() < 0.008:
            self.flash = 1.0
        if self.flash > 0:
            canvas.pixels[:] = np.maximum(canvas.pixels, np.array([0.7, 0.75, 1.0]) * self.flash ** 2)
            self.flash -= dt * 5


@effect("fireplace", "glowing logs, rising flames and drifting embers", "ambient")
class Fireplace(Effect):
    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        self.heat = np.zeros((ctx.canvas.h, ctx.canvas.w))
        self.embers = []

    def render(self, canvas, t, dt):
        h, w = self.heat.shape
        x, y = grid(canvas)
        logs = (y > h - 1) & (np.abs(x - w / 2) < w * 0.35)
        src = np.clip(1 - np.abs(x[-1] - w / 2) / (w * 0.4), 0, 1) * np.random.uniform(0.7, 1.1, w)
        self.heat[-1] = src
        rise = (self.heat[1:] * 0.6 + np.roll(self.heat[1:], 1, 1) * 0.15 + np.roll(self.heat[1:], -1, 1) * 0.15)
        self.heat[:-1] = rise * np.random.uniform(0.82, 0.97, rise.shape)
        v = np.clip(self.heat, 0, 1)
        canvas.pixels[:] = np.stack([np.clip(v * 1.4, 0, 1), np.clip(v * 1.4 - 0.45, 0, 1) * 0.7,
                                     np.clip(v * 2 - 1.6, 0, 1) * 0.3], -1)
        canvas.pixels[logs] = np.array([0.35, 0.08, 0.0]) + 0.25 * np.random.rand(int(logs.sum()), 1)
        if random.random() < 0.1:
            self.embers.append([random.uniform(w * 0.3, w * 0.7), h - 1.0, random.uniform(-0.5, 0.5)])
        for e in self.embers:
            e[1] -= dt * 2.5
            e[0] += e[2] * dt
            canvas.add(int(e[0]), int(e[1]), np.array([1.0, 0.6, 0.1]))
        self.embers = [e for e in self.embers if e[1] >= 0]


@effect("ocean_sunset", "a sun sinking into a shimmering sea, sky shifting from gold to violet", "ambient")
class OceanSunset(Effect):
    params = {"cycle": param("float", 40.0, 10, 300, label="Sunset length (s)")}

    def render(self, canvas, t, dt):
        x, y = grid(canvas)
        f = (t / self.opt("cycle")) % 1.0                 # 0: high sun, 1: dusk
        horizon = 2.6
        sky_hue = 0.11 - 0.2 * f                          # gold -> pink/violet
        sky = hsv_array(sky_hue + (horizon - y) * 0.03, 0.85, np.clip(0.9 - f * 0.6 - (horizon - y) * 0.1, 0.05, 1))
        sun_y = 0.5 + f * 2.6
        sun = blob(x, y, canvas.w / 2, sun_y, 2.2, 1.2) * (y < horizon)
        sea = y >= horizon
        shimmer = (np.sin(x * 2.3 - t * 3 + y * 4) * 0.5 + 0.5) * np.clip(1 - np.abs(x - canvas.w / 2) / 3, 0, 1)
        water = hsv_array(0.6 - f * 0.1, 0.9, 0.25 + 0.1 * np.sin(x * 0.8 + t))
        out = np.where(sea[..., None], water + np.array([1.0, 0.55, 0.1]) * (shimmer * (1 - f) * 0.7)[..., None], sky)
        out = np.maximum(out, np.array([1.0, 0.75, 0.25]) * sun[..., None])
        canvas.pixels[:] = np.clip(out, 0, 1)


@effect("nebula", "drifting clouds of colour in your wallpaper's palette", "ambient")
class Nebula(Effect):
    def render(self, canvas, t, dt):
        x, y = grid(canvas)
        a = noise2(x * 0.7, y, t * 0.35)
        b = noise2(x * 0.5 + 5, y * 1.3, t * 0.25, seed=2.0)
        density = np.clip((a + b) * 0.9 + 0.35, 0, 1)
        for r in range(canvas.h):
            for c in range(canvas.w):
                canvas.pixels[r, c] = self.palette_color(b[r, c] * 0.6 + 0.5 + t * 0.01) * density[r, c] ** 1.5
        stars = (np.random.rand(canvas.h, canvas.w) < 0.01)
        canvas.pixels[stars] = 1.0
