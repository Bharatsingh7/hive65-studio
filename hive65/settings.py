"""One JSON settings store shared by the CLI, engine and Studio app."""
import json
import os
import sys
import threading
from pathlib import Path

from .automation import DEFAULT_RULES
from .scenes import DEFAULT_SCENES


def config_dir():
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "hive65"


PATH = config_dir() / "settings.json"

DEFAULTS = {
    "effect": None,                 # base effect the app restores on start
    "effect_options": {},           # {effect name: {param: value}}
    "brightness": 1.0,
    "fps": 60,
    "speed": 1.6,                   # global animation speed multiplier
    "audio_sensitivity": 1.0,       # music effects: 0.25 (calm) .. 3.0 (very reactive)
    "tuning": {"gamma": 1.3, "saturation": 1.25, "floor": 0.08,
               "white": [1.0, 0.92, 0.8], "pop": True},
    "notifications": {
        "enabled": True,            # master switch (Home page)
        "volume": True, "brightness": True, "apps": True, "media": True, "system": True,
        "app_colors": {"discord": "#5865f2", "whatsapp": "#25d366", "telegram": "#2aabee",
                       "slack": "#e01e5a", "spotify": "#1db954", "outlook": "#0078d4",
                       "teams": "#6264a7", "gmail": "#ea4335"},
        "quiet_hours": None,        # e.g. ["23:00", "07:00"]
    },
    "ambient": {"wallpaper": True, "screen_mode": "fit", "screen_region": "screen",
                "smoothing": 0.25, "saturation": 1.4},
    "start_minimized": False,
    "favorites": ["aurora", "spectrum", "fireworks", "typing_fire", "warp_speed", "fluid"],
    "recent": [],
    "scenes": DEFAULT_SCENES,
    "active_scene": None,
    "layer": {"name": None, "blend": "screen", "opacity": 0.7},
    "highlight_set": "none",
    "automation_enabled": True,
    "automations": DEFAULT_RULES,
    "playlist": {"enabled": False, "minutes": 5, "shuffle": True, "on_drops": False},
    "dim_on_lock": True,
    "hotkeys": True,
    "builder": [],
}

_lock = threading.Lock()


def _merge(defaults, data):
    import copy
    out = copy.deepcopy(defaults)   # never hand out the DEFAULTS' own lists
    for k, v in data.items():
        out[k] = _merge(defaults[k], v) if isinstance(defaults.get(k), dict) and isinstance(v, dict) else v
    return out


def load():
    try:
        return _merge(DEFAULTS, json.loads(PATH.read_text()))
    except (OSError, ValueError):
        return _merge(DEFAULTS, {})


def save(data):
    with _lock:
        PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1))
        tmp.replace(PATH)


def update(**changes):
    data = load()
    data.update(changes)
    save(data)
    return data
