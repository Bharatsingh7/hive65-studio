"""More animations, tuned for a 16x5 keyboard: bold colours, dark backgrounds."""
import random

import numpy as np

from ..canvas import hsv, parse_color
from . import Effect, effect, param
from ._util import blob, grid, hsv_array, noise2, ring


@effect("aurora", "northern-lights curtains rippling across the keys")
class Aurora(Effect):
    params = {"speed": param("float", 0.6, 0.1, 3, label="Speed")}

    def render(self, canvas, t, dt):
        x, y = grid(canvas)
        s = t * self.opt("speed")
        curtain = np.sin(x * 0.5 + s + np.sin(x * 0.23 - s * 0.7) * 2.2) * 0.5 + 0.5
        height = np.clip(1.2 - np.abs(y - 1.2 - curtain * 2.2) / 1.6, 0, 1)
        hue = 0.33 + 0.25 * np.sin(x * 0.2 + s * 0.4) + 0.12 * (y / canvas.h)
        canvas.pixels[:] = hsv_array(hue, 0.9, height ** 1.5)


@effect("ocean", "rolling waves with white foam crests")
class Ocean(Effect):
    params = {"speed": param("float", 1.0, 0.2, 3, label="Speed")}

    def render(self, canvas, t, dt):
        x, y = grid(canvas)
        s = t * self.opt("speed")
        surface = 1.6 + np.sin(x * 0.55 - s * 1.8) * 0.9 + np.sin(x * 1.3 + s * 1.1) * 0.35
        depth = y - surface
        water = np.clip(depth + 0.8, 0, 1)
        foam = np.clip(1 - np.abs(depth) * 2.2, 0, 1) ** 2
        col = hsv_array(0.55 + 0.06 * np.clip(depth, 0, 3) / 3, 1, 0.25 + 0.75 * water)
        canvas.pixels[:] = col * (water > 0)[..., None] + foam[..., None] * 0.9


@effect("starfield", "twinkling stars that slowly bloom and fade")
class Starfield(Effect):
    params = {"density": param("float", 0.06, 0.01, 0.3, label="Stars per frame")}

    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        h, w = ctx.canvas.h, ctx.canvas.w
        self.phase = np.random.rand(h, w) * 6.28
        self.speed = np.random.uniform(0.5, 2.2, (h, w))
        self.hue = np.random.choice([0.58, 0.62, 0.12, 0.0, 0.8], (h, w))

    def render(self, canvas, t, dt):
        tw = np.clip(np.sin(self.phase + t * self.speed), 0, 1) ** 6
        canvas.pixels[:] = hsv_array(self.hue, 0.35, tw) + 0.02


@effect("lava_lamp", "slow molten blobs merging and splitting")
class LavaLamp(Effect):
    params = {"color": param("color", "#ff3000", label="Lava colour")}

    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        self.blobs = [(random.uniform(0, 16), random.uniform(0.2, 0.7), random.uniform(0, 6))
                      for _ in range(5)]

    def render(self, canvas, t, dt):
        x, y = grid(canvas)
        field = np.zeros_like(x)
        for bx, sp, ph in self.blobs:
            cx = bx + np.sin(t * 0.3 + ph) * 2
            cy = 2.5 + np.sin(t * sp + ph) * 2.3
            field += 1.8 / (np.hypot(x - cx, (y - cy) * 1.3) + 0.6)
        lava = np.clip(field - 1.2, 0, 1)
        base = parse_color(self.opt("color"))
        hot = np.array([1.0, 0.85, 0.2])
        canvas.pixels[:] = base * lava[..., None] + hot * (lava ** 4)[..., None] * 0.6
        canvas.pixels[:] += np.array([0.08, 0.0, 0.12])   # lamp glow behind


@effect("comets", "comets streak across with fading tails")
class Comets(Effect):
    params = {"count": param("int", 3, 1, 8, label="Comets")}

    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        self.c = [self._new() for _ in range(self.opt("count"))]

    def _new(self):
        return [random.uniform(-10, 0), random.randrange(5), random.uniform(6, 14), random.random()]

    def render(self, canvas, t, dt):
        canvas.fade(0.72)
        for c in self.c:
            c[0] += c[2] * dt
            canvas.set(int(c[0]), c[1], hsv(c[3], 0.6))
            if c[0] > canvas.w + 4:
                c[:] = self._new()


@effect("storm", "dark rain with sudden lightning flashes")
class Storm(Effect):
    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        self.drops, self.flash, self.bolt = [], 0.0, None

    def render(self, canvas, t, dt):
        canvas.fade(0.5)
        canvas.pixels[:] += np.array([0.0, 0.01, 0.04])
        if random.random() < 0.5:
            self.drops.append([random.randrange(canvas.w), 0.0])
        for d in self.drops:
            d[1] += dt * 14
            canvas.add(d[0], int(d[1]), np.array([0.2, 0.35, 0.9]))
        self.drops = [d for d in self.drops if d[1] < canvas.h]
        if random.random() < 0.012:
            self.flash, col = 1.0, random.randrange(canvas.w)
            self.bolt = [(min(canvas.w - 1, max(0, col + random.randint(-1, 1))), r) for r in range(canvas.h)]
        if self.flash > 0:
            canvas.pixels[:] = np.maximum(canvas.pixels, np.array([0.6, 0.6, 0.8]) * self.flash ** 2)
            for c, r in self.bolt or []:
                canvas.set(c, r, np.array([1.0, 1.0, 1.0]) * min(1, self.flash * 2))
            self.flash -= dt * 4


@effect("snowfall", "gentle snow drifting down and settling")
class Snowfall(Effect):
    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        self.flakes = []
        self.ground = np.zeros(ctx.canvas.w)

    def render(self, canvas, t, dt):
        canvas.clear(np.array([0.0, 0.02, 0.06]))
        if random.random() < 0.25:
            self.flakes.append([random.uniform(0, canvas.w), 0.0, random.uniform(1.2, 2.5)])
        for f in self.flakes:
            f[1] += dt * f[2]
            f[0] += np.sin(t * 2 + f[2] * 5) * dt * 0.8
            canvas.set(int(f[0]) % canvas.w, int(f[1]), np.array([0.9, 0.95, 1.0]))
        landed = [f for f in self.flakes if f[1] >= canvas.h - 1]
        for f in landed:
            self.ground[int(f[0]) % canvas.w] = 1.0
        self.flakes = [f for f in self.flakes if f[1] < canvas.h - 1]
        self.ground *= 0.995
        for c in range(canvas.w):
            canvas.add(c, canvas.h - 1, np.array([0.7, 0.8, 1.0]) * self.ground[c])


@effect("fireflies", "warm fireflies wandering in the dark")
class Fireflies(Effect):
    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        self.f = [[random.uniform(0, 16), random.uniform(0, 5), random.uniform(0, 6), random.uniform(0.6, 1.5)]
                  for _ in range(7)]

    def render(self, canvas, t, dt):
        x, y = grid(canvas)
        canvas.clear(np.array([0.0, 0.015, 0.0]))
        for f in self.f:
            f[0] = (f[0] + np.sin(t * f[3] + f[2]) * dt * 1.5) % canvas.w
            f[1] = np.clip(f[1] + np.cos(t * f[3] * 0.8 + f[2]) * dt, 0, canvas.h)
            glow = max(0.0, np.sin(t * f[3] * 2 + f[2])) ** 3
            canvas.pixels += blob(x, y, f[0], f[1], 1.4)[..., None] * np.array([1.0, 0.85, 0.15]) * glow


@effect("kaleidoscope", "mirrored, rotating colour patterns")
class Kaleidoscope(Effect):
    def render(self, canvas, t, dt):
        x, y = grid(canvas)
        mx = np.abs(x - canvas.w / 2)
        my = np.abs(y - canvas.h / 2) * 1.6
        a = np.arctan2(my, mx) * 3 + t * 0.8
        r = np.hypot(mx, my)
        v = np.sin(a) * np.cos(r * 0.9 - t * 1.5)
        canvas.pixels[:] = hsv_array(v * 0.3 + t * 0.07 + r * 0.04, 1, np.clip(np.abs(v) * 1.4, 0, 1))


@effect("vortex", "a spinning spiral pulled into the centre")
class Vortex(Effect):
    params = {"arms": param("int", 3, 1, 6, label="Spiral arms")}

    def render(self, canvas, t, dt):
        x, y = grid(canvas)
        dx, dy = x - canvas.w / 2, (y - canvas.h / 2) * 1.6
        ang = np.arctan2(dy, dx)
        r = np.hypot(dx, dy)
        v = np.sin(ang * self.opt("arms") + r * 0.9 - t * 3)
        canvas.pixels[:] = hsv_array(r * 0.05 - t * 0.1, 1, np.clip(v, 0, 1) ** 1.5)


@effect("scanner", "Knight-Rider style sweeping eye")
class Scanner(Effect):
    params = {"color": param("color", "#ff0000", label="Colour"),
              "speed": param("float", 1.0, 0.3, 3, label="Speed")}

    def render(self, canvas, t, dt):
        x, _ = grid(canvas)
        pos = (np.sin(t * 2.2 * self.opt("speed")) * 0.5 + 0.5) * (canvas.w - 1) + 0.5
        canvas.fade(0.8)
        canvas.pixels[:] = np.maximum(canvas.pixels, parse_color(self.opt("color")) *
                                      np.clip(1 - np.abs(x - pos) / 1.2, 0, 1)[..., None])


@effect("dna", "a double helix twisting along the keyboard")
class DNA(Effect):
    def render(self, canvas, t, dt):
        x, y = grid(canvas)
        canvas.clear()
        for phase, hue in ((0, 0.55), (np.pi, 0.9)):
            sy = canvas.h / 2 + np.sin(x * 0.6 - t * 2.5 + phase) * 1.9
            depth = np.cos(x * 0.6 - t * 2.5 + phase) * 0.5 + 0.5
            line = np.clip(1 - np.abs(y - sy) * 1.3, 0, 1) * (0.35 + 0.65 * depth)
            canvas.pixels[:] = np.maximum(canvas.pixels, hsv(hue) * line[..., None])
        rungs = (np.floor(x) % 2 == 0) & (np.abs(np.sin(x * 0.6 - t * 2.5)) < 0.35)
        canvas.pixels[rungs] = np.maximum(canvas.pixels[rungs], 0.25)


@effect("bouncing_balls", "coloured balls bouncing with gravity")
class BouncingBalls(Effect):
    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        self.b = [[random.uniform(0, 15), random.uniform(0, 2), random.uniform(-4, 4), 0.0, random.random()]
                  for _ in range(4)]

    def render(self, canvas, t, dt):
        x, y = grid(canvas)
        canvas.fade(0.55)
        for b in self.b:
            b[3] += 18 * dt
            b[0] += b[2] * dt
            b[1] += b[3] * dt
            if b[1] > canvas.h - 0.5:
                b[1], b[3] = canvas.h - 0.5, -abs(b[3]) * 0.92
                if abs(b[3]) < 4:
                    b[3] = -random.uniform(9, 12)
            if not 0.5 <= b[0] <= canvas.w - 0.5:
                b[2] = -b[2]
                b[0] = np.clip(b[0], 0.5, canvas.w - 0.5)
            canvas.pixels[:] = np.maximum(canvas.pixels, hsv(b[4]) * blob(x, y, b[0], b[1], 1.0, 1.2)[..., None])


@effect("tetris", "blocks fall, stack up and clear in a flash")
class Tetris(Effect):
    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        self.board = np.full((ctx.canvas.h, ctx.canvas.w), -1.0)
        self.piece, self.next_drop, self.clear_flash = None, 0.0, 0.0

    def render(self, canvas, t, dt):
        h, w = self.board.shape
        if self.piece is None:
            width = random.choice([1, 2, 3])
            self.piece = [random.randint(0, w - width), -1, width, random.random()]
        if t >= self.next_drop:
            self.next_drop = t + 0.18
            c0, r, width, hue = self.piece
            nr = r + 1
            if nr >= h or (self.board[nr, c0:c0 + width] >= 0).any():
                if r < 0:
                    self.board[:] = -1
                else:
                    self.board[r, c0:c0 + width] = hue
                self.piece = None
                full = [row for row in range(h) if (self.board[row] >= 0).sum() >= w - 1]
                if full:
                    self.clear_flash = 1.0
                    for row in full:
                        self.board[1:row + 1] = self.board[:row].copy()
                        self.board[0] = -1
            else:
                self.piece[1] = nr
        canvas.clear()
        filled = self.board >= 0
        canvas.pixels[filled] = hsv_array(self.board[filled], 1, 0.8)
        if self.piece and self.piece[1] >= 0:
            c0, r, width, hue = self.piece
            canvas.pixels[r, c0:c0 + width] = hsv(hue)
        if self.clear_flash > 0:
            canvas.pixels[:] = np.maximum(canvas.pixels, self.clear_flash)
            self.clear_flash -= dt * 4


@effect("pong", "two paddles play pong against each other")
class Pong(Effect):
    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        self.ball = [8.0, 2.5, 7.0, 3.0]
        self.p = [2.5, 2.5]

    def render(self, canvas, t, dt):
        h, w = canvas.h, canvas.w
        b = self.ball
        b[0] += b[2] * dt
        b[1] += b[3] * dt
        if not 0 <= b[1] <= h - 0.01:
            b[3] = -b[3]
            b[1] = np.clip(b[1], 0, h - 0.01)
        for side, px in ((0, 1), (1, w - 2)):
            target = b[1] if (b[2] < 0) == (side == 0) else h / 2
            self.p[side] += np.clip(target - self.p[side], -dt * 6, dt * 6)
        if b[0] < 1.5 or b[0] > w - 1.5:
            paddle = self.p[0] if b[0] < 1.5 else self.p[1]
            if abs(paddle - b[1]) < 1.6:
                b[2] = -b[2] * 1.03
                b[0] = np.clip(b[0], 1.5, w - 1.5)
            elif not 0 <= b[0] <= w:
                self.ball = [w / 2, h / 2, random.choice([-7, 7]), random.uniform(-3, 3)]
        canvas.fade(0.45)
        for side, px in ((0, 0), (1, w - 1)):
            for r in range(h):
                if abs(r + 0.5 - self.p[side]) < 1.2:
                    canvas.set(px, r, np.array([0.2, 0.6, 1.0]) if side == 0 else np.array([1.0, 0.3, 0.2]))
        canvas.set(int(b[0]), int(b[1]), np.array([1.0, 1.0, 1.0]))


@effect("snake", "a snake hunts glowing food around the board")
class Snake(Effect):
    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        self.reset()

    def reset(self):
        self.body = [(2, 2), (1, 2), (0, 2)]
        self.food = (10, 2)
        self.next = 0.0

    def render(self, canvas, t, dt):
        h, w = canvas.h, canvas.w
        if t >= self.next:
            self.next = t + 0.14
            hx, hy = self.body[0]
            fx, fy = self.food
            options = [(hx + dx, hy + dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))]
            options = [p for p in options if 0 <= p[0] < w and 0 <= p[1] < h and p not in self.body[:-1]]
            if not options:
                self.reset()
                return
            nxt = min(options, key=lambda p: abs(p[0] - fx) + abs(p[1] - fy) + random.random() * 0.3)
            self.body.insert(0, nxt)
            if nxt == self.food:
                free = [(c, r) for c in range(w) for r in range(h) if (c, r) not in self.body]
                self.food = random.choice(free) if free else (0, 0)
                if len(self.body) > 22:
                    self.body = self.body[:4]
            else:
                self.body.pop()
        canvas.clear()
        for i, (c, r) in enumerate(self.body):
            canvas.set(c, r, hsv(0.3 + i * 0.02, 1, 1 - i / (len(self.body) + 4)))
        canvas.set(*self.food, np.array([1.0, 0.1, 0.3]) * (0.6 + 0.4 * np.sin(t * 10)))


@effect("heartbeat", "a lub-dub heartbeat pulsing out from the centre")
class Heartbeat(Effect):
    params = {"bpm": param("float", 72.0, 40, 180, label="Beats per minute"),
              "color": param("color", "#ff0030", label="Colour")}

    def render(self, canvas, t, dt):
        x, y = grid(canvas)
        period = 60 / self.opt("bpm")
        p = (t % period) / period
        pulse = np.exp(-((p - 0.05) / 0.04) ** 2) + 0.7 * np.exp(-((p - 0.22) / 0.04) ** 2)
        d = np.hypot(x - canvas.w / 2, (y - canvas.h / 2) * 1.6)
        wave = np.exp(-((d - p * 18) / 1.5) ** 2) * (1 - p)
        level = np.clip(pulse * np.clip(1 - d / 9, 0.15, 1) + wave * 0.6, 0, 1)
        canvas.pixels[:] = parse_color(self.opt("color")) * level[..., None]


@effect("galaxy", "a slowly rotating galaxy with a bright core")
class Galaxy(Effect):
    def render(self, canvas, t, dt):
        x, y = grid(canvas)
        dx, dy = x - canvas.w / 2, (y - canvas.h / 2) * 2.0
        r = np.hypot(dx, dy)
        a = np.arctan2(dy, dx)
        arms = np.cos(2 * a - np.log1p(r) * 3 + t * 0.6) * 0.5 + 0.5
        core = np.clip(1 - r / 3, 0, 1) ** 2
        v = np.clip(arms ** 3 * np.clip(1 - r / 10, 0, 1) + core, 0, 1)
        canvas.pixels[:] = hsv_array(0.72 - r * 0.03 + core * 0.15, 0.8 - core * 0.6, v)


@effect("hypno", "hypnotic concentric rings flowing outward")
class Hypno(Effect):
    def render(self, canvas, t, dt):
        x, y = grid(canvas)
        d = np.hypot(x - canvas.w / 2, (y - canvas.h / 2) * 1.6)
        v = (np.sin(d * 1.6 - t * 5) > 0).astype(float)
        canvas.pixels[:] = hsv_array(d * 0.04 + t * 0.1, 1, v)


@effect("candle", "flickering candlelight glow")
class Candle(Effect):
    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        self.level = 0.7

    def render(self, canvas, t, dt):
        x, y = grid(canvas)
        self.level += (random.uniform(0.45, 1.0) - self.level) * 0.25
        n = noise2(x, y, t * 3) * 0.25
        heat = np.clip(self.level * (1 - (np.abs(x - canvas.w / 2) / canvas.w)) + n, 0, 1)
        canvas.pixels[:] = np.stack([heat, heat ** 1.8 * 0.6, heat ** 4 * 0.15], -1)


@effect("plasma_ring", "rings of plasma with a palette that follows the wallpaper")
class PlasmaRing(Effect):
    def render(self, canvas, t, dt):
        x, y = grid(canvas)
        v = np.sin(np.hypot(x - 8 + np.sin(t) * 4, (y - 2.5) * 1.5) * 1.2 - t * 2)
        lvl = np.clip(v * 0.5 + 0.5, 0, 1) ** 2
        for r in range(canvas.h):
            for c in range(canvas.w):
                canvas.pixels[r, c] = self.palette_color(lvl[r, c] * 0.5 + t * 0.03) * lvl[r, c]


@effect("neon_grid", "synthwave neon grid rushing toward you")
class NeonGrid(Effect):
    def render(self, canvas, t, dt):
        x, y = grid(canvas)
        horizon = 0.5
        depth = np.clip(y - horizon, 0.01, None)
        lines_h = (np.abs(((1 / depth) * 2 + t * 2.5) % 1 - 0.5) < 0.18).astype(float)
        lines_v = (np.abs(((x - canvas.w / 2) / depth * 0.6) % 1 - 0.5) < 0.15).astype(float)
        grid_v = np.clip(lines_h + lines_v, 0, 1) * (y > horizon)
        sun = np.clip(1 - np.abs(x - canvas.w / 2) / 3, 0, 1) * (y < 1)
        canvas.pixels[:] = (np.array([1.0, 0.1, 0.8]) * grid_v[..., None]
                            + np.array([1.0, 0.5, 0.0]) * sun[..., None])
