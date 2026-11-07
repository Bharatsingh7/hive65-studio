"""hive65 command line."""
import argparse
import json
import sys
import time
from pathlib import Path

from .canvas import parse_color
from .device import (CMD_CONFIG, CMD_CUSTOM, CMD_KEYMAP, CMD_PALETTE, CONFIG_LEN, CUSTOM_LEN,
                     KEYMAP_LEN, PALETTE_LEN, DeviceError, Hive65, pause_streams)
from .keymap import BASE, FN, Keymap, describe
from .layout import Layout
from .lighting import MODES, Lighting


def _rgb_bytes(text):
    return tuple(int(round(v * 255)) for v in parse_color(text))


def _options(pairs):
    out = {}
    for p in pairs or []:
        k, _, v = p.partition("=")
        out[k.replace("-", "_")] = v
    return out


def cmd_info(a, kb):
    print("signature:", kb.check_signature().hex(" "))
    print("lighting: ", Lighting(kb).state())


def cmd_backup(a, kb):
    state = {"time": time.ctime(), "info": kb.info().hex(),
             "config": kb.read(CMD_CONFIG, CONFIG_LEN).hex(),
             "palette": kb.read(CMD_PALETTE, PALETTE_LEN).hex(),
             "custom": kb.read(CMD_CUSTOM, CUSTOM_LEN).hex(),
             "keymap_base": kb.read(CMD_KEYMAP, KEYMAP_LEN, BASE).hex(),
             "keymap_fn": kb.read(CMD_KEYMAP, KEYMAP_LEN, FN).hex()}
    Path(a.file).write_text(json.dumps(state, indent=1))
    print(f"saved {a.file}")


def cmd_restore(a, kb):
    s = json.loads(Path(a.file).read_text())
    kb.check_signature()
    kb.write(CMD_PALETTE, bytes.fromhex(s["palette"]))
    kb.write(CMD_CUSTOM, bytes.fromhex(s["custom"]))
    Keymap(kb, Layout()).write_raw(bytes.fromhex(s["keymap_base"]), BASE)
    Keymap(kb, Layout()).write_raw(bytes.fromhex(s["keymap_fn"]), FN)
    kb.write(CMD_CONFIG, bytes.fromhex(s["config"]))
    print(f"restored {a.file} (saved {s.get('time', '?')})")


def cmd_modes(a, kb):
    for m in MODES:
        flags = ", ".join(f for f, on in (("speed", m.speed), ("colour", m.color)) if on)
        print(f"{m.id:3d}  {m.name:20s} {flags}")


def cmd_mode(a, kb):
    Lighting(kb).apply(mode=a.mode, brightness=a.brightness, speed=a.speed,
                       color=_rgb_bytes(a.color) if a.color else None,
                       multicolor=a.multicolor)
    print(Lighting(kb).state())


def cmd_perkey(a, kb):
    """hive65 perkey esc=red w=#00ff00 a,s,d=blue  (others off unless --keep)."""
    lay, light = Layout(), Lighting(kb)
    colors = light.get_custom() if a.keep else {}
    for item in a.assign:
        names, _, color = item.rpartition("=")
        for n in names.split(","):
            colors[lay.key(n).led] = _rgb_bytes(color)
    light.set_custom(colors)
    print(f"saved {len(colors)} key colours, mode = self_define")


def cmd_keymap(a, kb):
    km = Keymap(kb, Layout())
    for name, value in km.get(FN if a.fn else BASE).items():
        print(f"{name:10s} {describe(value)}")


def cmd_remap(a, kb):
    """hive65 remap capslock=esc  ralt=ctrl+c  --fn  f=mute"""
    changes = dict(item.split("=", 1) for item in a.assign)
    Keymap(kb, Layout()).remap(changes, FN if a.fn else BASE)
    print("remapped:", ", ".join(f"{k} -> {v}" for k, v in changes.items()))


def cmd_effects(a, kb=None):
    from .effects import load_all, user_effects_dir
    if a.dir:
        print(user_effects_dir())
        return
    for name, cls in sorted(load_all().items()):
        print(f"{name:14s} {cls.description}")


def cmd_notify(a, kb=None):
    """Show a notification animation (forwarded to the running Studio app if any)."""
    from . import ipc
    value = None if a.value is None else (a.value if a.kind == "app" else float(a.value))
    meta = {"color": a.color} if a.color else {}
    if a.kind == "app":
        meta["app"] = a.value or ""
    resp = ipc.send({"cmd": "notify", "kind": a.kind, "value": value, "meta": meta})
    if resp is not None:
        if not resp.get("ok"):
            sys.exit(f"error: {resp.get('error')}")
        return
    # No app running: play it here on top of nothing for its duration.
    from .engine import Engine
    from .overlays import make
    eng = Engine()
    ov = make(eng.ctx, a.kind, value, **meta)
    eng.push_overlay(ov)
    eng.start()
    time.sleep(ov.duration + 0.2)
    eng.stop()


def cmd_effect(a, kb=None):
    from . import ipc
    from .effects import load_all
    from .engine import run
    effects = load_all()
    if a.name not in effects:
        sys.exit(f"unknown effect '{a.name}'. Try: hive65 effects")
    opts = _options(a.opt)
    if a.color:
        opts["color"] = a.color
    if a.duration is None and ipc.send({"cmd": "effect", "name": a.name, "options": opts}):
        print(f"switched the running app to {a.name}")
        return
    print(f"running {a.name} at {a.fps} fps - Ctrl+C to stop")
    try:
        run(effects[a.name], fps=a.fps, brightness=a.brightness, duration=a.duration, options=opts,
            sensitivity=a.sensitivity)
    except KeyboardInterrupt:
        pass


def main(argv=None):
    p = argparse.ArgumentParser(prog="hive65", description="Kreo Hive 65 control")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("info", help="show device signature and current lighting")
    s = sub.add_parser("backup", help="save everything stored on the keyboard to JSON")
    s.add_argument("file", nargs="?", default="hive65-backup.json")
    s = sub.add_parser("restore", help="write a backup JSON back to the keyboard")
    s.add_argument("file")

    sub.add_parser("modes", help="list hardware lighting modes")
    s = sub.add_parser("mode", help="set a stored hardware lighting mode")
    s.add_argument("mode", nargs="?", help="name or id (see `hive65 modes`)")
    s.add_argument("-b", "--brightness", type=int, help="0..4")
    s.add_argument("-s", "--speed", type=int, help="0..4")
    s.add_argument("-c", "--color", help="#rrggbb or name")
    s.add_argument("-m", "--multicolor", action="store_true")

    s = sub.add_parser("perkey", help="store per-key colours (Self-define mode)")
    s.add_argument("assign", nargs="+", help="key[,key...]=color")
    s.add_argument("--keep", action="store_true", help="keep existing custom colours")

    s = sub.add_parser("keymap", help="show the key map")
    s.add_argument("--fn", action="store_true", help="show the FN layer")
    s = sub.add_parser("remap", help="remap keys, e.g. capslock=esc")
    s.add_argument("assign", nargs="+", help="key=action (esc, ctrl+c, mute, f5, 0x...)")
    s.add_argument("--fn", action="store_true", help="edit the FN layer")

    s = sub.add_parser("effects", help="list live effects")
    s.add_argument("--dir", action="store_true", help="print the folder for your own effects")
    s = sub.add_parser("effect", help="run a live effect (streams from this PC)")
    s.add_argument("name")
    s.add_argument("-c", "--color", help="colour for effects that use one")
    s.add_argument("--fps", type=int, default=30)
    s.add_argument("-b", "--brightness", type=float, default=1.0, help="0..1")
    s.add_argument("-d", "--duration", type=float, help="seconds, default forever")
    s.add_argument("-o", "--opt", action="append", help="effect option name=value")
    s.add_argument("-s", "--sensitivity", type=float,
                   help="music sensitivity 0.25..3 (default: the app setting)")

    sub.add_parser("serve", help="run effects + notifications headless (no window)")
    # Remote control for the running app (Hyprland binds, scripts, hypridle).
    s = sub.add_parser("scene", help="switch the running app to a scene")
    s.add_argument("name")
    sub.add_parser("next", help="next favourite effect")
    sub.add_parser("prev", help="previous favourite effect")
    s = sub.add_parser("brightness", help="set brightness: 0.6, +0.1 or -0.1")
    s.add_argument("value")
    sub.add_parser("pause", help="pause/resume live effects")
    s = sub.add_parser("idle", help="tell the app the PC is idle (for hypridle)")
    s.add_argument("state", choices=["on", "off"])
    s = sub.add_parser("notify", help="play a notification animation")
    s.add_argument("kind", choices=["volume", "brightness", "app", "media", "caps", "battery",
                                    "mic", "done", "flash"])
    s.add_argument("value", nargs="?", help="level 0..1 (volume/brightness), app name (app)")
    s.add_argument("-c", "--color", help="colour for app/flash")

    a = p.parse_args(argv)
    if a.cmd == "serve":
        from .core import serve
        return serve()
    remote = {"scene": lambda: {"cmd": "scene", "name": a.name},
              "next": lambda: {"cmd": "next"}, "prev": lambda: {"cmd": "prev"},
              "brightness": lambda: {"cmd": "brightness", "value": a.value},
              "pause": lambda: {"cmd": "toggle_pause"},
              "idle": lambda: {"cmd": "idle", "on": a.state == "on"}}
    if a.cmd in remote:
        from . import ipc
        resp = ipc.send(remote[a.cmd]())
        if resp is None:
            sys.exit("Hive65 Studio (or `hive65 serve`) isn't running.")
        if not resp.get("ok"):
            sys.exit(f"error: {resp.get('error')}")
        extra = {k: v for k, v in resp.items() if k != "ok"}
        if extra:
            print(extra)
        return
    handler = globals()[f"cmd_{a.cmd}"]
    if a.cmd in ("effects", "effect", "notify"):
        return handler(a)
    try:
        with pause_streams(), Hive65() as kb:
            handler(a, kb)
    except DeviceError as e:
        sys.exit(f"error: {e}")


if __name__ == "__main__":
    main()
