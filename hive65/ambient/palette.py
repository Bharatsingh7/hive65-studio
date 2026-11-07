"""Dominant vivid colours of an image, for keyboard palettes."""
import colorsys

import numpy as np


def extract(image, count=6):
    """Return up to `count` RGB arrays (0..1), most vivid and common first.

    Greys and near-black are dropped (they look dead on LEDs); colours are
    pushed to full value so they glow.
    """
    img = image.convert("RGB")
    img.thumbnail((160, 160))
    q = img.quantize(colors=24, method=0)   # median cut
    pal = q.getpalette()[:24 * 3]
    counts = sorted(q.getcolors(), reverse=True)
    scored = []
    for n, idx in counts:
        r, g, b = (v / 255 for v in pal[idx * 3: idx * 3 + 3])
        h, s, v = colorsys.rgb_to_hsv(r, g, b)
        if s < 0.18 or v < 0.12:
            continue
        scored.append((n * (0.3 + s) * (0.3 + v), h, s))
    scored.sort(reverse=True)
    out, hues = [], []
    for _, h, s in scored:
        if any(min(abs(h - o), 1 - abs(h - o)) < 0.04 for o in hues):
            continue   # skip near-duplicate hues
        hues.append(h)
        out.append(np.array(colorsys.hsv_to_rgb(h, min(1.0, s * 1.3 + 0.15), 1.0)))
        if len(out) == count:
            break
    if not out:  # monochrome image: fall back to a soft white
        out = [np.array([1.0, 0.85, 0.7])]
    return out
