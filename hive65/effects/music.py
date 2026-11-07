"""Music-reactive effects driven by whatever audio is playing on the PC."""
import random

import numpy as np

from ..canvas import hsv
from . import Effect, effect


@effect("spectrum", "spectrum analyser: one column per frequency band")
class Spectrum(Effect):
    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        self.peaks = np.zeros(ctx.canvas.w)

    def render(self, canvas, t, dt):
        bands = self.ctx.audio.bands
        canvas.clear()
        self.peaks = np.maximum(self.peaks - dt * 1.5, bands)
        for c in range(canvas.w):
            height = bands[c] * canvas.h
            for r in range(canvas.h):
                level = height - (canvas.h - 1 - r)  # bottom row first
                if level > 0:
                    canvas.pixels[r, c] = hsv(c / canvas.w * 0.8 + t * 0.03) * min(1.0, level)
            peak_row = canvas.h - 1 - min(canvas.h - 1, int(self.peaks[c] * canvas.h))
            canvas.add(c, peak_row, np.array([0.6, 0.6, 0.6]))


@effect("vu", "stereo-style VU meter growing from the centre")
class VU(Effect):
    def render(self, canvas, t, dt):
        level = self.ctx.audio.level
        canvas.fade(0.6)
        half = canvas.w / 2
        reach = level * half * 1.3
        for c in range(canvas.w):
            d = abs(c + 0.5 - half)
            if d < reach:
                color = hsv(0.33 - 0.33 * d / half)  # green centre -> red edges
                for r in range(canvas.h):
                    canvas.pixels[r, c] = color


@effect("beat_pulse", "whole board flashes a new colour on every beat")
class BeatPulse(Effect):
    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        self.hue, self.energy = 0.0, 0.0

    def render(self, canvas, t, dt):
        if self.hit("beat"):
            self.hue = (self.hue + 0.17) % 1
            self.energy = 1.0
        self.energy = max(self.energy - dt * 3, self.ctx.audio.level * 0.3)
        canvas.clear(hsv(self.hue) * self.energy)


@effect("bass_ripple", "rings burst out of the space bar on every beat")
class BassRipple(Effect):
    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        self.rings = []  # (birth time, hue)
        space = ctx.layout.key("space")
        self.cx, self.cy = space.x, space.y

    def render(self, canvas, t, dt):
        if self.hit("beat"):
            self.rings.append((t, random.random()))
        self.rings = [(b, h) for b, h in self.rings if t - b < 2.0]
        canvas.fade(0.5)
        for r in range(canvas.h):
            for c in range(canvas.w):
                d = np.hypot(c + 0.5 - self.cx, (r + 0.5 - self.cy) * 1.3)
                for born, hue in self.rings:
                    radius = (t - born) * 10
                    glow = max(0.0, 1 - abs(d - radius)) * (1 - (t - born) / 2)
                    if glow > 0:
                        canvas.add(c, r, hsv(hue) * glow)


@effect("audio_wave", "scrolling waveform of the music's loudness")
class AudioWave(Effect):
    def render(self, canvas, t, dt):
        canvas.pixels[:, :-1] = canvas.pixels[:, 1:]
        canvas.pixels[:, -1] = 0
        a = self.ctx.audio
        level = a.level * canvas.h
        mid = (canvas.h - 1) / 2
        for r in range(canvas.h):
            if abs(r - mid) <= level / 2:
                canvas.pixels[r, -1] = hsv(0.6 - a.bass * 0.6)


@effect("rain_drops", "colourful drops fall faster and thicker with louder music")
class RainDrops(Effect):
    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        self.drops = []  # [col, row, hue]

    def render(self, canvas, t, dt):
        a = self.ctx.audio
        canvas.fade(0.7)
        if random.random() < a.level * 1.5 or self.hit("beat"):
            self.drops.append([random.randrange(canvas.w), 0.0, random.random()])
        for d in self.drops:
            d[1] += dt * (4 + a.bass * 12)
            canvas.add(d[0], int(d[1]), hsv(d[2]))
        self.drops = [d for d in self.drops if d[1] < canvas.h]
