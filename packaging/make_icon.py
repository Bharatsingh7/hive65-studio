"""Draw the Hive65 icon (four coloured keycaps) as hive65.png and hive65.ico."""
from pathlib import Path

from PIL import Image, ImageDraw

here = Path(__file__).parent
size = 256
img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((0, 0, size - 1, size - 1), radius=56, fill=(12, 14, 22, 255))
colors = [(236, 72, 153), (139, 92, 246), (6, 182, 212), (34, 197, 94)]
pad, gap = 34, 16
cell = (size - 2 * pad - gap) // 2
for i, c in enumerate(colors):
    x = pad + (i % 2) * (cell + gap)
    y = pad + (i // 2) * (cell + gap)
    d.rounded_rectangle((x, y, x + cell, y + cell), radius=22, fill=c + (255,))
    d.rounded_rectangle((x + 10, y + 8, x + cell - 10, y + cell * 0.45), radius=14,
                        fill=tuple(min(255, v + 40) for v in c) + (255,))
img.save(here / "hive65.png")
img.save(here / "hive65.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("wrote", here / "hive65.png", here / "hive65.ico")
