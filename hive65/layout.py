"""Physical key layout of the Kreo Hive 65 and its LED-matrix view.

Every key has a firmware LED index (column-major, 6 slots per column, so
index = col * 6 + row) and a rectangle from the vendor's KB.ini, used here to
place it on a regular grid for matrix-style effects.
"""
import json
import re
from dataclasses import dataclass
from pathlib import Path

NUM_LEDS = 126
DATA = Path(__file__).with_name("data") / "layout.json"
KEY_UNIT = 39  # KB.ini pixels per 1u key pitch


@dataclass(frozen=True)
class Key:
    name: str
    led: int
    x: float  # centre, in key units
    y: float
    w: float  # width, in key units
    vk: int   # Windows virtual-key code

    @property
    def col(self):
        return int(self.x)

    @property
    def row(self):
        return round(self.y)


def parse_kb_ini(path):
    """Extract keys from the vendor KB.ini (used once to generate layout.json)."""
    keys, name, section = [], None, None
    for line in Path(path).read_text(encoding="latin-1").splitlines():
        line = line.strip()
        if line.startswith("["):
            section = line
        elif section == "[KEY]" and line.startswith(";"):
            name = line[1:]
        elif section == "[KEY]" and re.match(r"K\d+=", line):
            parts = [p.strip() for p in line.split("=", 1)[1].split(",")]
            l, t, r, b = map(int, parts[:4])
            if r == 0:  # virtual key (e.g. Mute on the knob)
                continue
            keys.append({"name": name, "led": int(parts[-1]), "vk": int(parts[5], 16),
                         "x": (l + r) / 2, "y": (t + b) / 2, "w": r - l})
    x0 = min(k["x"] - k["w"] / 2 for k in keys)
    y0 = min(k["y"] for k in keys)
    for k in keys:
        k["x"] = round((k["x"] - x0) / KEY_UNIT, 2)
        k["y"] = round((k["y"] - y0) / KEY_UNIT, 2)
        k["w"] = round(k["w"] / KEY_UNIT, 2)
    return keys


class Layout:
    def __init__(self, path=DATA):
        self.keys = [Key(**k) for k in json.loads(Path(path).read_text())]
        self.by_name = {k.name.lower(): k for k in self.keys}
        self.by_vk = {k.vk: k for k in self.keys}
        self.width = int(max(k.x for k in self.keys)) + 1
        self.height = max(k.row for k in self.keys) + 1

    def key(self, name):
        return self.by_name[name.lower()]

    def grid(self):
        """Map (col, row) cells of a width x height matrix to LED indices.

        Wide keys cover several cells, so a pixel drawn anywhere under the
        spacebar lights the spacebar.
        """
        cells = {}
        for k in self.keys:
            left, right = k.x - k.w / 2, k.x + k.w / 2
            for c in range(self.width):
                if left - 0.25 <= c + 0.5 <= right + 0.25:
                    cells.setdefault((c, k.row), k.led)
        return cells


if __name__ == "__main__":
    import sys
    keys = parse_kb_ini(sys.argv[1])
    DATA.parent.mkdir(exist_ok=True)
    DATA.write_text(json.dumps(keys, indent=1))
    lay = Layout()
    print(f"{len(keys)} keys, grid {lay.width}x{lay.height}")
    g = lay.grid()
    names = {k.led: k.name for k in lay.keys}
    for r in range(lay.height):
        print(" ".join(f"{names.get(g.get((c, r)), '.')[:4]:>4}" for c in range(lay.width)))
