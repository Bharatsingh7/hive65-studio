"""More music-reactive effects. Each leans on a different part of the analysis:
bands, kick/snare/hat hits, tempo phase, or bass/mid/treble energy."""
import random

import numpy as np

from ..canvas import hsv
from . import Effect, effect, param
from ._util import blob, grid, hsv_array, noise2, ring


@effect("center_bars", "mirrored spectrum bars growing out from the middle row", "music")
class CenterBars(Effect):
    def render(self, canvas, t, dt):
        bands = self.ctx.audio.bands
        h, w = canvas.h, canvas.w
        x, y = grid(canvas)
        mirrored = np.concatenate([bands[: w // 2][::-1], bands[: w - w // 2]])
        height = mirrored * (h / 2 + 0.3)
        dist = np.abs(y - h / 2)
        lit = np.clip(height[None, :] - dist + 0.5, 0, 1)
        canvas.pixels[:] = hsv_array(0.75 - dist / h * 0.6 + t * 0.02, 1, lit)


@effect("gravcenter", "VU from the centre with peaks that fall back under gravity", "music")
class GravCenter(Effect):
    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        self.peak, self.vel = 0.0, 0.0

    def render(self, canvas, t, dt):
        a = self.ctx.audio
        level = a.level * 1.2
        if level > self.peak:
            self.peak, self.vel = level, 0.0
        else:
            self.vel += dt * 1.6
            self.peak = max(0.0, self.peak - self.vel * dt)
        x, y = grid(canvas)
        d = np.abs(x - canvas.w / 2) / (canvas.w / 2)
        lit = np.clip((level - d) * 6, 0, 1)
        peak = np.clip(1 - np.abs(d - self.peak) * 10, 0, 1)
        n = noise2(x, y, t * 2) * 0.12
        canvas.pixels[:] = hsv_array(0.55 - d * 0.5 + n, 1, lit) + peak[..., None]


@effect("spectrogram", "scrolling waterfall: the music's frequencies flow upward", "music")
class Spectrogram(Effect):
    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        self.hist = np.zeros((ctx.canvas.h, ctx.canvas.w))
        self.acc = 0.0

    def render(self, canvas, t, dt):
        self.acc += dt
        if self.acc > 0.06:
            self.acc = 0
            self.hist[:-1] = self.hist[1:]
            self.hist[-1] = self.ctx.audio.bands
        v = self.hist ** 1.5
        canvas.pixels[:] = hsv_array(0.7 - v * 0.7, 1, v)


@effect("drum_rows", "kick lights the bottom rows, snare the middle, hi-hats the top", "music")
class DrumRows(Effect):
    def render(self, canvas, t, dt):
        a = self.ctx.audio
        canvas.fade(0.6)
        h = canvas.h
        for rows, level, col in (((h - 2, h - 1), a.kick, np.array([1.0, 0.05, 0.2])),
                                 ((h - 3,), a.snare, np.array([1.0, 0.8, 0.1])),
                                 ((0, 1), a.hat, np.array([0.2, 0.7, 1.0]))):
            for r in rows:
                if 0 <= r < h:
                    canvas.pixels[r] = np.maximum(canvas.pixels[r], col * level)


@effect("swirl", "glowing orbs orbit the centre and leap outward on beats", "music")
class Swirl(Effect):
    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        self.radius = 2.0

    def render(self, canvas, t, dt):
        a = self.ctx.audio
        if self.hit("kick"):
            self.radius = 6.5
        self.radius += (2.0 + a.level * 2 - self.radius) * min(1, dt * 4)
        x, y = grid(canvas)
        canvas.fade(0.55)
        for i in range(4):
            ang = t * (1.2 + a.mid) + i * np.pi / 2
            cx = canvas.w / 2 + np.cos(ang) * self.radius
            cy = canvas.h / 2 + np.sin(ang) * self.radius * 0.45
            canvas.pixels[:] = np.maximum(canvas.pixels, hsv(i / 4 + t * 0.05)[None, None]
                                          * blob(x, y, cx, cy, 1.8, 1.4)[..., None])


@effect("strobe_chase", "columns chase across the board locked to the song's tempo", "music")
class StrobeChase(Effect):
    def render(self, canvas, t, dt):
        a = self.ctx.audio
        x, _ = grid(canvas)
        beats = a.hits["beat"] + a.phase
        pos = (beats % 2) / 2 * (canvas.w + 4) - 2
        lit = np.clip(1 - np.abs(x - pos) / 1.5, 0, 1) ** 2
        hue = (a.hits["beat"] // 2) * 0.13
        canvas.fade(0.7)
        canvas.pixels[:] = np.maximum(canvas.pixels, hsv(hue)[None, None] * lit[..., None] *
                                      (0.4 + 0.6 * a.level))


@effect("fireworks", "a rocket launches on every kick and bursts into sparks", "music")
class Fireworks(Effect):
    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        self.rockets, self.sparks = [], []

    def render(self, canvas, t, dt):
        if self.hit("kick"):
            self.rockets.append([random.uniform(2, canvas.w - 2), canvas.h, -random.uniform(7, 10), random.random()])
        canvas.fade(0.65)
        for r in self.rockets:
            r[2] += 9 * dt
            r[1] += r[2] * dt
            canvas.add(int(r[0]), int(r[1]), np.array([1.0, 0.9, 0.6]))
        for r in [r for r in self.rockets if r[2] >= 0 or r[1] < 0.8]:
            for _ in range(16):
                a = random.uniform(0, 2 * np.pi)
                s = random.uniform(2, 7)
                self.sparks.append([r[0], r[1], np.cos(a) * s, np.sin(a) * s * 0.6, 1.0, r[3]])
        self.rockets = [r for r in self.rockets if r[2] < 0 and r[1] >= 0.8]
        for s in self.sparks:
            s[3] += 5 * dt
            s[0] += s[2] * dt
            s[1] += s[3] * dt
            s[4] -= dt * 1.3
            canvas.add(int(s[0]), int(s[1]), hsv(s[5] + random.uniform(-0.05, 0.05)) * max(0, s[4]))
        self.sparks = [s for s in self.sparks if s[4] > 0]


@effect("music_lava", "metaballs that swell with loudness and split on drops", "music")
class MusicLava(Effect):
    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        self.b = [[random.uniform(0, 16), random.uniform(0, 5), random.uniform(-1, 1), random.uniform(-0.5, 0.5)]
                  for _ in range(4)]

    def render(self, canvas, t, dt):
        a = self.ctx.audio
        if self.hit("kick"):
            for b in self.b:
                b[2] += random.uniform(-3, 3)
                b[3] += random.uniform(-1.5, 1.5)
        x, y = grid(canvas)
        field = np.zeros_like(x)
        for b in self.b:
            b[0] = (b[0] + b[2] * dt) % canvas.w
            b[1] += b[3] * dt
            if not 0 <= b[1] <= canvas.h:
                b[3] = -b[3]
            b[2] *= 0.98
            field += (1.2 + a.bass * 2) / (np.hypot(x - b[0], (y - b[1]) * 1.3) + 0.5)
        v = np.clip(field - 1.6, 0, 1)
        canvas.pixels[:] = hsv_array(0.95 - v * 0.15 + a.treble * 0.2, 1, v)


@effect("palette_pulse", "the wallpaper's colours flash on every beat", "music")
class PalettePulse(Effect):
    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        self.i, self.e = 0, 0.0

    def render(self, canvas, t, dt):
        if self.hit("beat"):
            self.i += 1
            self.e = 1.0
        self.e = max(self.e - dt * 2.5, self.ctx.audio.level * 0.25)
        x, _ = grid(canvas)
        for c in range(canvas.w):
            canvas.pixels[:, c] = self.palette_color(self.i * 0.25 + c / canvas.w * 0.3) * self.e


@effect("horizon_eq", "five horizontal equalisers, one per row, low to high", "music")
class HorizonEQ(Effect):
    def render(self, canvas, t, dt):
        bands = self.ctx.audio.bands
        h, w = canvas.h, canvas.w
        groups = np.array_split(bands, h)
        x, _ = grid(canvas)
        for r in range(h):
            level = float(np.max(groups[h - 1 - r])) if len(groups[h - 1 - r]) else 0
            lit = np.clip(level * w - (x[r] - 0.5), 0, 1)
            canvas.pixels[r] = hsv_array(r / h * 0.8 + x[r] * 0.01, 1, lit)


@effect("disco", "random keys strobe in party colours with every hit", "music")
class Disco(Effect):
    def render(self, canvas, t, dt):
        a = self.ctx.audio
        canvas.fade(0.75)
        hits = (self.hit("kick") * 10 + self.hit("snare") * 6 + self.hit("hat") * 3
                + int(a.level * 3))
        for _ in range(hits):
            canvas.set(random.randrange(canvas.w), random.randrange(canvas.h),
                       hsv(random.choice([0.0, 0.08, 0.16, 0.5, 0.75, 0.88])))


@effect("mood", "the whole board breathes with the bass; its colour follows the treble", "music")
class Mood(Effect):
    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        self.hue = 0.0

    def render(self, canvas, t, dt):
        a = self.ctx.audio
        self.hue += (a.treble * 0.8 - self.hue) * dt * 0.8
        x, y = grid(canvas)
        wave = 0.75 + 0.25 * np.sin(x * 0.4 - t * 2)
        canvas.pixels[:] = hsv_array(0.62 - self.hue, 1, np.clip(0.15 + a.bass * 0.9, 0, 1) * wave)


@effect("pulse_rings", "bass, mids and highs each fire rings from their own spot", "music")
class PulseRings(Effect):
    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        self.rings = []

    def render(self, canvas, t, dt):
        origins = {"kick": (8, 4.5, 0.0), "snare": (3, 2.0, 0.15), "hat": (13, 1.0, 0.55)}
        for name, (cx, cy, hue) in origins.items():
            if self.hit(name):
                self.rings.append((cx, cy, t, hue))
        self.rings = [r for r in self.rings if t - r[2] < 1.0][-12:]
        x, y = grid(canvas)
        canvas.fade(0.5)
        for cx, cy, born, hue in self.rings:
            age = t - born
            canvas.pixels[:] = np.maximum(canvas.pixels, hsv(hue)[None, None]
                                          * (ring(x, y, cx, cy, age * 12, 1.0) * (1 - age))[..., None])


@effect("fountain", "particles shoot up from the bottom as high as the music is loud", "music")
class Fountain(Effect):
    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        self.p = []

    def render(self, canvas, t, dt):
        a = self.ctx.audio
        for c in range(canvas.w):
            if random.random() < self.ctx.audio.bands[c] * 0.5:
                self.p.append([c + 0.5, canvas.h, -(3 + a.bands[c] * 9), c / canvas.w])
        canvas.fade(0.6)
        for p in self.p:
            p[2] += 12 * dt
            p[1] += p[2] * dt
            canvas.add(int(p[0]), int(p[1]), hsv(p[3]))
        self.p = [p for p in self.p if p[1] < canvas.h + 0.5]


@effect("drop_lightning", "big drops crack the board with white lightning", "music")
class DropLightning(Effect):
    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        self.flash, self.bolt = 0.0, []

    def render(self, canvas, t, dt):
        a = self.ctx.audio
        canvas.pixels[:] = hsv_array(np.full((canvas.h, canvas.w), 0.7), 1, 0.06 + a.bass * 0.25)
        if self.hit("kick") and a.kick > 0.8:
            self.flash = 1.0
            c = random.randrange(canvas.w)
            self.bolt = []
            for r in range(canvas.h):
                c = min(canvas.w - 1, max(0, c + random.randint(-1, 1)))
                self.bolt.append((c, r))
        if self.flash > 0:
            canvas.pixels[:] += np.array([0.5, 0.5, 0.7]) * self.flash ** 3
            for c, r in self.bolt:
                canvas.set(c, r, np.array([1.0, 1.0, 1.0]))
            self.flash -= dt * 3


@effect("sine_wave", "an oscilloscope wave whose height follows the bass", "music")
class SineWave(Effect):
    def render(self, canvas, t, dt):
        a = self.ctx.audio
        x, y = grid(canvas)
        amp = 0.3 + a.bass * 2.2
        freq = 0.4 + a.treble * 0.8
        wy = canvas.h / 2 + np.sin(x * freq - t * 6) * amp
        line = np.clip(1 - np.abs(y - wy) * 1.2, 0, 1)
        canvas.fade(0.5)
        canvas.pixels[:] = np.maximum(canvas.pixels, hsv_array(0.5 + x * 0.02 + a.mid * 0.3, 1, line))


@effect("beat_snake", "a snake that steps on every beat and grows with the energy", "music")
class BeatSnake(Effect):
    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        self.body = [(0, 2)]
        self.dir = (1, 0)

    def render(self, canvas, t, dt):
        a = self.ctx.audio
        if self.hit("beat") or self.hit("snare"):
            hx, hy = self.body[0]
            if random.random() < 0.3:
                self.dir = random.choice([(1, 0), (-1, 0), (0, 1), (0, -1)])
            nx, ny = (hx + self.dir[0]) % canvas.w, (hy + self.dir[1]) % canvas.h
            self.body.insert(0, (nx, ny))
            self.body = self.body[: 3 + int(a.level * 18)]
        canvas.fade(0.8)
        for i, (c, r) in enumerate(self.body):
            canvas.set(c, r, hsv(t * 0.1 + i * 0.04, 1, 1 - i / (len(self.body) + 2)))


@effect("tunnel", "rings rush toward you at the song's tempo", "music")
class Tunnel(Effect):
    def render(self, canvas, t, dt):
        a = self.ctx.audio
        x, y = grid(canvas)
        d = np.hypot(x - canvas.w / 2, (y - canvas.h / 2) * 1.8)
        beat = a.hits["beat"] + a.phase
        v = (np.sin(d * 1.3 - beat * 2 * np.pi) * 0.5 + 0.5) ** 3
        canvas.pixels[:] = hsv_array(d * 0.04 + beat * 0.05, 1, v * (0.3 + 0.7 * a.level))


@effect("confetti_beat", "confetti bursts across the board on snares and claps", "music")
class ConfettiBeat(Effect):
    def render(self, canvas, t, dt):
        canvas.fade(0.8)
        n = 12 if self.hit("snare") else 0
        n += 4 if self.hit("kick") else 0
        for _ in range(n):
            canvas.set(random.randrange(canvas.w), random.randrange(canvas.h), hsv(random.random(), 0.8))


@effect("bass_meter", "the bass fills the board from the bottom like liquid", "music")
class BassMeter(Effect):
    def render(self, canvas, t, dt):
        a = self.ctx.audio
        x, y = grid(canvas)
        surface = canvas.h - a.bass * canvas.h * 1.1 + np.sin(x * 0.8 + t * 5) * 0.4 * a.mid
        lit = np.clip(y - surface + 0.5, 0, 1)
        canvas.pixels[:] = hsv_array(0.85 + (canvas.h - y) * 0.05 - a.kick * 0.2, 1, lit)
