"""Effects driven by what's on screen (movies, games) and by the wallpaper."""
import numpy as np

from ..canvas import hsv
from . import Effect, effect, param

_SAMPLER = None


def sampler(region):
    global _SAMPLER
    from ..ambient.screen import ScreenSampler
    if _SAMPLER is None or _SAMPLER.region != region or not _SAMPLER.is_alive():
        if _SAMPLER:
            _SAMPLER.stop()
        _SAMPLER = ScreenSampler(region=region)
    return _SAMPLER


def _boost(rgb, sat, floor=0.0):
    grey = rgb.mean(axis=-1, keepdims=True)
    out = np.clip(grey + (rgb - grey) * sat, 0, 1)
    peak = out.max(axis=-1, keepdims=True)
    # lift dark scenes so they still glow, keep hue
    target = np.maximum(peak, floor)
    return np.where(peak > 0.02, out * (target / np.maximum(peak, 1e-6)), 0)


@effect("movie", "ambilight: keys copy the colours of the video/game on screen", "screen")
class Movie(Effect):
    params = {"mode": param("choice", "fit", choices=["fit", "edges", "average"],
                            label="Mapping"),
              "region": param("choice", "screen", choices=["screen", "window"],
                              label="Capture"),
              "smoothing": param("float", 0.3, 0.0, 0.9, label="Smoothing"),
              "saturation": param("float", 1.5, 1.0, 3.0, label="Colour boost"),
              "lift": param("float", 0.15, 0.0, 0.5, label="Dark-scene lift")}

    def __init__(self, ctx, **opts):
        super().__init__(ctx, **opts)
        self.src = sampler(self.opt("region"))
        self.state = np.zeros((ctx.canvas.h, ctx.canvas.w, 3))

    def render(self, canvas, t, dt):
        img = self.src.latest
        if img is None:
            canvas.clear(hsv(t * 0.1) * 0.1 * (1 if self.src.error is None else 0))
            if self.src.error:   # make a capture failure visible: slow red breathe
                canvas.clear(np.array([1, 0, 0]) * (0.3 + 0.3 * np.sin(t * 3)))
            return
        from PIL import Image
        h, w = canvas.h, canvas.w
        mode = self.opt("mode")
        if mode == "average":
            target = np.broadcast_to(img.reshape(-1, 3).mean(axis=0), (h, w, 3))
        else:
            small = np.asarray(Image.fromarray((img * 255).astype(np.uint8)).resize((w, h), Image.BOX),
                               dtype=float) / 255
            if mode == "edges":
                edge = np.zeros_like(small)
                top = np.asarray(Image.fromarray((img[: img.shape[0] // 4] * 255).astype(np.uint8))
                                 .resize((w, 1), Image.BOX), dtype=float) / 255
                bot = np.asarray(Image.fromarray((img[-img.shape[0] // 4:] * 255).astype(np.uint8))
                                 .resize((w, 1), Image.BOX), dtype=float) / 255
                edge[0], edge[-1] = top[0], bot[0]
                edge[:, 0], edge[:, -1] = small[:, 0], small[:, -1]
                edge[1:-1, 1:-1] = small[1:-1, 1:-1] * 0.25
                small = edge
            target = small
        target = _boost(np.asarray(target), self.opt("saturation"), self.opt("lift"))
        k = self.opt("smoothing")
        self.state = self.state * k + target * (1 - k)
        canvas.pixels[:] = self.state


@effect("wallpaper_flow", "slow gradient through your wallpaper's colours", "screen")
class WallpaperFlow(Effect):
    params = {"speed": param("float", 0.04, 0.005, 0.3, label="Drift speed")}

    def render(self, canvas, t, dt):
        s = self.opt("speed")
        for c in range(canvas.w):
            col = self.palette_color(c / canvas.w * 0.6 + t * s, fallback_hue=(c / canvas.w + t * s))
            for r in range(canvas.h):
                canvas.pixels[r, c] = col * (0.75 + 0.25 * np.sin(t * 0.8 + c * 0.4 + r))


@effect("wallpaper_aurora", "wallpaper colours as drifting aurora curtains", "screen")
class WallpaperAurora(Effect):
    params = {"speed": param("float", 0.5, 0.1, 2, label="Speed")}

    def render(self, canvas, t, dt):
        s = self.opt("speed") * t
        y, x = np.mgrid[0:canvas.h, 0:canvas.w]
        wave = np.sin(x * 0.45 + s * 1.3 + np.sin(y * 0.8 + s)) * 0.5 + 0.5
        bright = np.clip(np.sin(x * 0.3 - s * 0.7 + y * 0.5) * 0.5 + 0.6, 0, 1)
        for r in range(canvas.h):
            for c in range(canvas.w):
                canvas.pixels[r, c] = self.palette_color(wave[r, c] * 0.8 + s * 0.05) * bright[r, c]
