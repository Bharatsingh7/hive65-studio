"""Global hotkeys (Windows / X11 via pynput).

Wayland compositors don't allow global key grabs; on Hyprland bind the same
actions to the CLI instead, e.g. in hyprland.conf:
    bind = CTRL ALT, right, exec, hive65 next
    bind = CTRL ALT, left,  exec, hive65 prev
    bind = CTRL ALT, up,    exec, hive65 brightness +0.1
    bind = CTRL ALT, down,  exec, hive65 brightness -0.1
    bind = CTRL ALT, P,     exec, hive65 pause
"""
import sys

BINDINGS = {
    "<ctrl>+<alt>+<right>": "next",
    "<ctrl>+<alt>+<left>": "prev",
    "<ctrl>+<alt>+<up>": "brighter",
    "<ctrl>+<alt>+<down>": "dimmer",
    "<ctrl>+<alt>+p": "pause",
}


def start(core):
    """Start listening; returns the listener (or None where unsupported)."""
    if sys.platform.startswith("linux"):
        import os
        if os.environ.get("WAYLAND_DISPLAY"):
            return None
    try:
        from pynput import keyboard
    except Exception:
        return None
    actions = {
        "next": lambda: core.next_favorite(),
        "prev": lambda: core.next_favorite(step=-1),
        "brighter": lambda: core.set_brightness(min(1.0, core.engine.brightness + 0.1)),
        "dimmer": lambda: core.set_brightness(max(0.05, core.engine.brightness - 0.1)),
        "pause": core.toggle_pause,
    }
    hk = keyboard.GlobalHotKeys({combo: actions[name] for combo, name in BINDINGS.items()})
    hk.daemon = True
    hk.start()
    return hk
