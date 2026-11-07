"""Wallpaper changes -> keyboard palette.

Windows: the registry path of the current wallpaper (and its file mtime).
Hyprland: swww, hyprpaper or pywal, whichever is in use.
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

from . import LINUX, WINDOWS, Source


def current_wallpaper():
    if WINDOWS:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop") as k:
            path = winreg.QueryValueEx(k, "WallPaper")[0]
        if not path or not os.path.exists(path):
            # Slideshows / Spotlight keep the live image here.
            cached = Path(os.environ["APPDATA"]) / "Microsoft/Windows/Themes/TranscodedWallpaper"
            path = str(cached) if cached.exists() else None
        return path
    if LINUX:
        if shutil.which("swww"):
            out = subprocess.run(["swww", "query"], capture_output=True, text=True).stdout
            for line in out.splitlines():
                if "image:" in line:
                    return line.split("image:", 1)[1].strip()
        if shutil.which("hyprctl"):
            out = subprocess.run(["hyprctl", "hyprpaper", "listactive"],
                                 capture_output=True, text=True).stdout
            for line in out.splitlines():
                if "=" in line:
                    return line.split("=", 1)[1].strip()
        wal = Path.home() / ".cache/wal/wal"
        if wal.exists():
            return wal.read_text().strip()
    return None


def pywal_colors():
    f = Path.home() / ".cache/wal/colors.json"
    if not f.exists():
        return None
    import numpy as np
    data = json.loads(f.read_text())
    hexes = [data["colors"][f"color{i}"] for i in range(1, 7)]
    return [np.array([int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]) for h in hexes]


class Wallpaper(Source):
    name = "wallpaper"
    interval = 2.0

    def setup(self):
        self.last = None

    def poll(self):
        path = current_wallpaper()
        if not path or not os.path.exists(path):
            return
        sig = (path, os.path.getmtime(path))
        if sig == self.last:
            return
        self.last = sig
        colors = pywal_colors() if LINUX else None
        if not colors:
            from PIL import Image

            from ..ambient.palette import extract
            colors = extract(Image.open(path), 6)
        self.emit("wallpaper", colors, path=path)


def create(emit):
    return Wallpaper(emit)
