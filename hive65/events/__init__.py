"""Event sources (volume, brightness, notifications, media, system, wallpaper).

Each source is a daemon thread calling emit(kind, value, **meta). The EventHub
turns events into overlays on the engine, honouring the user's settings.
"""
import sys
import threading
import time

LINUX = sys.platform.startswith("linux")
WINDOWS = sys.platform == "win32"


class Source(threading.Thread):
    """Base for polling sources: override poll() and call self.emit()."""

    interval = 0.15
    name = "source"

    def __init__(self, emit):
        super().__init__(daemon=True)
        self.emit = emit
        self.stopped = threading.Event()
        self.error = None

    def setup(self):
        pass

    def poll(self):
        raise NotImplementedError

    def run(self):
        try:
            self.setup()
        except Exception as e:
            self.error = f"{self.name}: {e}"
            return
        while not self.stopped.is_set():
            try:
                self.poll()
            except Exception as e:
                self.error = f"{self.name}: {e}"
                time.sleep(2)
            self.stopped.wait(self.interval)

    def stop(self):
        self.stopped.set()


class EventHub:
    def __init__(self, engine, settings):
        self.engine = engine
        self.settings = settings
        self.sources = []
        self.listeners = []   # callables(kind, value, meta) e.g. the GUI log

    def emit(self, kind, value=None, **meta):
        from .. import overlays
        n = self.settings.get("notifications", {})
        gate = {"volume": "volume", "brightness": "brightness", "app": "apps",
                "media": "media", "caps": "system", "battery": "system", "mic": "system"}
        palette_event = kind in ("wallpaper", "screen_palette")
        if not palette_event and (not n.get("enabled", True) or not n.get(gate.get(kind, kind), True)
                                  or self._quiet()):
            return
        if kind == "app":
            app = (meta.get("app") or "").lower()
            colors = n.get("app_colors", {})
            meta["color"] = next((c for k, c in colors.items() if k in app), meta.get("color", "#00b0ff"))
        if kind == "wallpaper":
            self.engine.set_palette(value)
        elif kind == "screen_palette":
            self.engine.set_palette(value)
        else:
            self.engine.push_overlay(overlays.make(self.engine.ctx, kind, value, **meta))
        for cb in list(self.listeners):
            cb(kind, value, meta)

    def _quiet(self):
        q = self.settings.get("notifications", {}).get("quiet_hours")
        if not q:
            return False
        now = time.strftime("%H:%M")
        start, end = q
        return start <= now < end if start < end else (now >= start or now < end)

    def start(self):
        from . import apps, brightness, media, system, volume, wallpaper
        mods = [volume, brightness, system, apps, media]
        if self.settings.get("ambient", {}).get("wallpaper"):
            mods.append(wallpaper)
        for mod in mods:
            try:
                src = mod.create(self.emit)
            except Exception as e:
                print(f"event source {mod.__name__} unavailable: {e}", file=sys.stderr)
                continue
            if src:
                self.sources.append(src)
                src.start()

    def errors(self):
        return [s.error for s in self.sources if s.error]

    def stop(self):
        for s in self.sources:
            s.stop()
