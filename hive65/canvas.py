"""A 16x5 RGB canvas that maps onto the keyboard's LEDs."""
import colorsys

import numpy as np

from .layout import NUM_LEDS, Layout


def hsv(h, s=1.0, v=1.0):
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, s, v)
    return np.array([r, g, b])


def parse_color(text):
    """'#ff8800', 'ff8800', 'red', or 'r,g,b' -> float RGB array in 0..1."""
    named = {"red": "ff0000", "green": "00ff00", "blue": "0000ff", "white": "ffffff",
             "black": "000000", "yellow": "ffff00", "cyan": "00ffff",
             "magenta": "ff00ff", "orange": "ff6000", "purple": "8000ff", "pink": "ff40a0"}
    text = named.get(text.lower(), text).lstrip("#")
    if "," in text:
        rgb = [int(v) for v in text.split(",")]
    else:
        rgb = [int(text[i:i + 2], 16) for i in (0, 2, 4)]
    return np.array(rgb, dtype=float) / 255.0


class Canvas:
    """pixels[row, col] = (r, g, b) floats in 0..1."""

    def __init__(self, layout=None):
        self.layout = layout or Layout()
        self.w, self.h = self.layout.width, self.layout.height
        self.pixels = np.zeros((self.h, self.w, 3))
        grid = self.layout.grid()
        # For each key, the cells it covers; its colour is their mean.
        self._key_cells = {}
        for (c, r), led in grid.items():
            self._key_cells.setdefault(led, []).append((r, c))
        self._leds = np.array(sorted(self._key_cells))
        self._rows = [np.array([rc[0] for rc in self._key_cells[l]]) for l in self._leds]
        self._cols = [np.array([rc[1] for rc in self._key_cells[l]]) for l in self._leds]

    def clear(self, color=(0, 0, 0)):
        self.pixels[:] = color

    def fade(self, factor):
        self.pixels *= factor

    def set(self, col, row, color):
        if 0 <= col < self.w and 0 <= row < self.h:
            self.pixels[row, col] = color

    def add(self, col, row, color):
        if 0 <= col < self.w and 0 <= row < self.h:
            self.pixels[row, col] = np.minimum(1.0, self.pixels[row, col] + color)

    def set_key(self, name, color):
        k = self.layout.key(name)
        for r, c in self._key_cells.get(k.led, []):
            self.pixels[r, c] = color

    def key_colors(self):
        """{led index: (r, g, b) floats} — one colour per physical key."""
        px = np.clip(self.pixels, 0, 1)
        return {led: px[rows, cols].max(axis=0) if len(rows) > 1 else px[rows[0], cols[0]]
                for led, rows, cols in zip(self._leds, self._rows, self._cols)}

    def to_frame(self, brightness=1.0, tuning=None):
        """Encode as the 378-byte payload of command 0x08 (LED index * 3 = R,G,B)."""
        tuning = tuning or LEDTuning()
        frame = np.zeros((NUM_LEDS, 3), dtype=np.uint8)
        colors = self.key_colors()
        leds = np.fromiter(colors, dtype=int)
        rgb = tuning.apply(np.array(list(colors.values())), brightness)
        frame[leds] = rgb
        return frame.tobytes()


class LEDTuning:
    """Output stage that makes colours read clearly on real keycaps.

    gamma      < 2.2 keeps mid-tones visible (keyboard PWM is already non-linear)
    saturation > 1 pushes colours away from washed-out white
    floor      minimum level for any lit key, so dim pixels don't vanish
    white      per-channel balance (these LEDs run blue-heavy)
    pop        snap near-black to black so lit keys stand out
    """

    def __init__(self, gamma=1.3, saturation=1.25, floor=0.08, white=(1.0, 0.92, 0.8), pop=True):
        self.gamma, self.saturation, self.floor = gamma, saturation, floor
        self.white, self.pop = np.array(white, dtype=float), pop

    @classmethod
    def from_settings(cls, d):
        return cls(**{k: d[k] for k in ("gamma", "saturation", "floor", "white", "pop") if k in d})

    def apply(self, rgb, brightness=1.0):
        rgb = np.clip(rgb, 0, 1)
        peak = rgb.max(axis=1, keepdims=True)
        if self.saturation != 1:
            grey = rgb.mean(axis=1, keepdims=True)
            rgb = np.clip(grey + (rgb - grey) * self.saturation, 0, 1)
            # keep the original peak so saturation doesn't change brightness
            new_peak = rgb.max(axis=1, keepdims=True)
            rgb = np.where(new_peak > 0, rgb * (peak / np.maximum(new_peak, 1e-6)), rgb)
        if self.pop:
            rgb[peak[:, 0] < 0.04] = 0
            peak = rgb.max(axis=1, keepdims=True)
        rgb = rgb ** self.gamma
        if self.floor:
            p = rgb.max(axis=1, keepdims=True)
            lit = p > 1e-4
            scale = np.where(lit, np.maximum(p, self.floor) / np.maximum(p, 1e-6), 1)
            rgb = rgb * scale
        rgb = rgb * self.white * brightness
        return np.clip(rgb * 255 + 0.5, 0, 255).astype(np.uint8)
