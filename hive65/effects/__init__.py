"""Effect registry. Built-in effects live in this package; your own go in the
user effects folder (see `hive65 effects --dir`) as any *.py file using:

    from hive65.effects import Effect, effect

    @effect("my_effect", "what it does")
    class MyEffect(Effect):
        def render(self, canvas, t, dt):
            canvas.clear((t % 1, 0, 0))
"""
import importlib
import importlib.util
import os
import sys
from pathlib import Path

REGISTRY = {}
CATEGORIES = ("music", "typing", "display", "ambient", "screen", "custom")


def param(kind, default, lo=None, hi=None, choices=None, label=None):
    """Declare a tweakable effect setting; the Studio app builds controls from these.

    kind: "float", "int", "bool", "color", "text" or "choice".
    """
    return {"kind": kind, "default": default, "min": lo, "max": hi,
            "choices": choices, "label": label}


class Effect:
    """Base class. ctx gives .layout, .audio, .pressed_keys() and .palette (all lazy)."""

    category = "ambient"
    params = {}

    def __init__(self, ctx, **options):
        self.ctx = ctx
        self.options = options
        self._seen = {}

    def hit(self, name="beat"):
        """True once for each new audio hit ("beat", "kick", "snare", "hat").

        Each effect keeps its own counter, so several can react to one beat.
        """
        count = self.ctx.audio.hits[name]
        last = self._seen.get(name)
        self._seen[name] = count
        return last is not None and count > last

    def palette_color(self, x, fallback_hue=None):
        """Colour at position x (0..1, wraps) along the ambient palette.

        Falls back to a rainbow when no wallpaper/screen palette is active.
        """
        pal = self.ctx.palette
        if not pal:
            from ..canvas import hsv
            return hsv(x if fallback_hue is None else fallback_hue)
        x = (x % 1.0) * len(pal)
        i = int(x)
        a, b = pal[i % len(pal)], pal[(i + 1) % len(pal)]
        f = x - i
        return a * (1 - f) + b * f

    def opt(self, name, default=None):
        spec = self.params.get(name)
        if default is None and spec:
            default = spec["default"]
        value = self.options.get(name, default)
        if isinstance(default, bool):
            return value if isinstance(value, bool) else str(value).lower() in ("1", "true", "yes", "on")
        if isinstance(default, float):
            return float(value)
        if isinstance(default, int):
            return int(float(value))
        return value

    def render(self, canvas, t, dt):
        raise NotImplementedError

    def close(self):
        """Called when the effect is replaced; stop background threads here."""
        for p in getattr(self, "_pollers", []):
            p.stop()

    def poll(self, fn, interval, default=None, demo=None):
        """Run fn() every `interval` s on a background thread; returns a Poller
        whose .value holds the latest result (or `default`) and .error any failure.

        In demo mode (gallery thumbnails) nothing runs: .value is `demo`."""
        from ._util import Poller, StaticPoller
        if getattr(self.ctx, "demo", False):
            return StaticPoller(demo if demo is not None else default)
        p = Poller(fn, interval, default)
        self.__dict__.setdefault("_pollers", []).append(p)
        return p


def effect(name, description="", category=None):
    def register(cls):
        cls.effect_name, cls.description = name, description
        if category:
            cls.category = category
        elif "category" not in cls.__dict__:
            mod = cls.__module__.rsplit(".", 1)[-1].rstrip("0123456789")
            cls.category = mod if mod in CATEGORIES else "ambient"
        REGISTRY[name] = cls
        return cls
    return register


def user_effects_dir():
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "hive65" / "effects"


_LOADED = False


def load_all():
    global _LOADED
    if _LOADED:
        return REGISTRY
    _LOADED = True
    for mod in ("ambient", "ambient2", "music", "music2", "matrix", "typing", "typing2",
                "display", "display2", "screen", "fx3"):
        importlib.import_module(f"{__name__}.{mod}")
    try:   # designs from the Studio's Effect Builder
        from .. import settings
        from .builder import register_all
        register_all(settings.load().get("builder", []))
    except Exception as e:
        print(f"warning: builder effects failed to load: {e}", file=sys.stderr)
    folder = user_effects_dir()
    if folder.is_dir():
        for path in sorted(folder.glob("*.py")):
            spec = importlib.util.spec_from_file_location(f"hive65_user_{path.stem}", path)
            module = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(module)
            except Exception as e:  # a broken plugin shouldn't kill the rest
                print(f"warning: effect plugin {path.name} failed to load: {e}", file=sys.stderr)
    return REGISTRY
