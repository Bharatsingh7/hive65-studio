"""Scenes: named snapshots of everything the keyboard is showing.

A scene stores the base effect (+ options), an optional mixer layer, the
key-highlight set, brightness, speed and music sensitivity.
"""
import copy

# Keys kept lit over any effect while a highlight set is active.
HIGHLIGHT_SETS = {
    "none": {},
    "gaming": {**{k: (1.0, 1.0, 1.0) for k in ("W", "A", "S", "D")},
               **{k: (1.0, 0.25, 0.0) for k in ("Space", "LShift", "LCtrl")},
               **{k: (0.0, 0.8, 1.0) for k in ("Q", "E", "R", "F", "1", "2", "3", "4")}},
    "editor": {**{k: (0.3, 0.7, 1.0) for k in ("LCtrl", "C", "V", "X", "Z", "S", "F")},
               "Esc": (1.0, 0.3, 0.1)},
    "media": {k: (0.2, 1.0, 0.5) for k in ("Space", "Left", "Right", "Up", "Down")},
}

DEFAULT_SCENES = [
    {"name": "Gaming", "effect": "movie", "options": {"region": "window", "mode": "edges"},
     "highlights": "gaming", "brightness": 1.0},
    {"name": "Chill", "effect": "aurora", "brightness": 0.5, "speed": 1.0},
    {"name": "Party", "effect": "fireworks", "layer": "disco", "blend": "screen", "opacity": 0.6,
     "sensitivity": 1.6, "brightness": 1.0},
    {"name": "Focus", "effect": "pomodoro", "brightness": 0.7, "highlights": "editor"},
    {"name": "Night", "effect": "candle", "brightness": 0.2, "speed": 1.0},
    {"name": "Music", "effect": "center_bars", "layer": "pulse_rings", "blend": "add", "opacity": 0.5},
    {"name": "Screensaver", "effect": "starfield", "brightness": 0.35, "speed": 1.0},
]

FIELDS = ("effect", "options", "layer", "layer_options", "blend", "opacity", "highlights",
          "brightness", "speed", "sensitivity")


def capture(core, name):
    """Snapshot of what is playing now, as a scene dict."""
    e = core.engine
    return {"name": name, "effect": e.effect_name, "options": dict(e.effect_options),
            "layer": e.layer_name, "blend": e.layer_blend, "opacity": e.layer_opacity,
            "highlights": core.settings.get("highlight_set", "none"),
            "brightness": e.brightness, "speed": e.speed,
            "sensitivity": e.ctx.audio_sensitivity}


def apply(core, scene, remember=True):
    """Switch the keyboard to a scene. Missing fields keep their defaults."""
    s = copy.deepcopy(scene)
    core.set_effect(s.get("effect"), s.get("options") or None, remember=remember)
    core.set_layer(s.get("layer"), s.get("layer_options"), s.get("blend", "screen"),
                   s.get("opacity", 0.7), save=remember)
    core.set_highlight_set(s.get("highlights", "none"), save=remember)
    core.engine.brightness = float(s.get("brightness", core.settings.get("brightness", 1.0)))
    core.engine.speed = float(s.get("speed", core.settings.get("speed", 1.6)))
    if "sensitivity" in s:
        core.set_audio_sensitivity(s["sensitivity"], save=False)
    if remember:
        core.settings["active_scene"] = s.get("name")
        core.save()


def find(core, name):
    for s in core.settings.get("scenes", []):
        if s["name"].lower() == str(name).lower():
            return s
    return None
