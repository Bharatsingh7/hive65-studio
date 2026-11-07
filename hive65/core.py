"""The running app's brain: engine + event sources + IPC, driven by settings.

Used by the Studio GUI and by `hive65 serve` (headless, e.g. a Hyprland
exec-once or systemd user service).
"""
import time

from . import settings as settings_mod
from .engine import Engine
from .events import EventHub

FACTORY_BACKUP = settings_mod.config_dir() / "first-run-backup.json"


def ensure_backup():
    """On first run, save everything stored on the keyboard so it can be restored."""
    if FACTORY_BACKUP.exists():
        return
    import json

    from .device import (CMD_CONFIG, CMD_CUSTOM, CMD_KEYMAP, CMD_PALETTE, CONFIG_LEN, CUSTOM_LEN,
                         KEYMAP_LEN, PALETTE_LEN, Hive65, pause_streams)
    try:
        with pause_streams(), Hive65() as kb:
            state = {"time": time.ctime(), "info": kb.info().hex(),
                     "config": kb.read(CMD_CONFIG, CONFIG_LEN).hex(),
                     "palette": kb.read(CMD_PALETTE, PALETTE_LEN).hex(),
                     "custom": kb.read(CMD_CUSTOM, CUSTOM_LEN).hex(),
                     "keymap_base": kb.read(CMD_KEYMAP, KEYMAP_LEN, 0).hex(),
                     "keymap_fn": kb.read(CMD_KEYMAP, KEYMAP_LEN, 1).hex()}
        FACTORY_BACKUP.parent.mkdir(parents=True, exist_ok=True)
        FACTORY_BACKUP.write_text(json.dumps(state, indent=1))
    except Exception:
        pass   # keyboard not connected yet; try next start


class Core:
    def __init__(self):
        self.settings = settings_mod.load()
        self.engine = Engine(self.settings)
        self.events = EventHub(self.engine, self.settings)
        self.server = None
        self.automation = None
        self.hotkeys = None
        self.idle_since = None     # set by `hive65 idle on` (hypridle on Linux)

    def start(self):
        from . import ipc
        ensure_backup()
        name = self.settings.get("effect")
        if name:
            try:
                self.engine.set_effect(name, self.settings["effect_options"].get(name, {}))
            except KeyError:
                self.settings["effect"] = None
        layer = self.settings.get("layer", {})
        if layer.get("name"):
            try:
                self.engine.set_layer(layer["name"], None, layer.get("blend"), layer.get("opacity"))
            except KeyError:
                pass
        self.set_highlight_set(self.settings.get("highlight_set", "none"), save=False)
        self.engine.start()
        self.events.start()
        from . import hotkeys
        from .automation import Automation
        self.automation = Automation(self)
        self.automation.start()
        if self.settings.get("hotkeys", True):
            self.hotkeys = hotkeys.start(self)
        try:
            self.server = ipc.Server(self.handle)
        except OSError:
            self.server = None   # another instance already owns the port

    def stop(self):
        if self.automation:
            self.automation.stop()
        if self.hotkeys:
            self.hotkeys.stop()
        self.events.stop()
        self.engine.stop()
        if self.server:
            self.server.close()

    def save(self):
        settings_mod.save(self.settings)

    # --- actions shared by GUI, tray and IPC ---------------------------------
    def set_effect(self, name, options=None, remember=True):
        if options is None:
            options = self.settings["effect_options"].get(name, {}) if name else {}
        self.engine.set_effect(name, options)
        self.engine.paused = False
        if not remember:      # automations switch temporarily without touching settings
            return
        self.settings["effect"] = name
        if name:
            self.settings["effect_options"][name] = options
            recent = [n for n in self.settings.get("recent", []) if n != name]
            self.settings["recent"] = ([name] + recent)[:12]
        self.save()

    def set_layer(self, name, options=None, blend="screen", opacity=0.7, save=True):
        self.engine.set_layer(name, options, blend, opacity)
        if save:
            self.settings["layer"] = {"name": name, "blend": self.engine.layer_blend,
                                      "opacity": self.engine.layer_opacity}
            self.save()

    def set_highlight_set(self, name, save=True):
        from .scenes import HIGHLIGHT_SETS
        custom = self.settings.get("custom_highlights", {})
        keys = custom.get(name) if name in custom else HIGHLIGHT_SETS.get(name or "none", {})
        self.engine.set_highlights(keys)
        if save:
            self.settings["highlight_set"] = name or "none"
            self.save()

    def toggle_favorite(self, name):
        favs = self.settings.setdefault("favorites", [])
        if name in favs:
            favs.remove(name)
        else:
            favs.append(name)
        self.save()
        return name in favs

    def next_favorite(self, step=1, shuffle=False):
        import random
        favs = [f for f in self.settings.get("favorites", []) if f]
        if not favs:
            return None
        cur = self.engine.effect_name
        if shuffle and len(favs) > 1:
            name = random.choice([f for f in favs if f != cur])
        else:
            i = favs.index(cur) if cur in favs else -1
            name = favs[(i + step) % len(favs)]
        self.set_effect(name)
        return name

    def toggle_pause(self):
        self.engine.paused = not self.engine.paused
        return self.engine.paused

    def apply_scene(self, name):
        from . import scenes
        s = scenes.find(self, name)
        if s is None:
            raise KeyError(f"no scene called {name}")
        scenes.apply(self, s)

    def save_scene(self, name):
        from . import scenes
        snap = scenes.capture(self, name)
        lst = [s for s in self.settings.get("scenes", []) if s["name"].lower() != name.lower()]
        self.settings["scenes"] = lst + [snap]
        self.save()

    def delete_scene(self, name):
        self.settings["scenes"] = [s for s in self.settings.get("scenes", [])
                                   if s["name"].lower() != name.lower()]
        self.save()

    def save_design(self, design):
        from .effects.builder import register_all
        lst = [d for d in self.settings.get("builder", []) if d["name"] != design["name"]]
        self.settings["builder"] = lst + [dict(design)]
        register_all(self.settings["builder"])
        self.save()

    def delete_design(self, name):
        from .effects.builder import register_all
        self.settings["builder"] = [d for d in self.settings.get("builder", []) if d["name"] != name]
        register_all(self.settings["builder"])
        if self.engine.effect_name == name:
            self.set_effect(None)
        self.save()

    def set_option(self, name, key, value):
        opts = dict(self.settings["effect_options"].get(name, {}), **{key: value})
        self.settings["effect_options"][name] = opts
        if self.engine.effect_name == name:
            self.engine.set_effect(name, opts)
        self.save()

    def set_brightness(self, value):
        self.engine.brightness = self.settings["brightness"] = float(value)
        self.save()

    def set_audio_sensitivity(self, value, save=True):
        ctx = self.engine.ctx
        ctx.audio_sensitivity = float(value)
        if ctx._audio is not None:
            ctx._audio.sensitivity = ctx.audio_sensitivity
        if save:
            self.settings["audio_sensitivity"] = ctx.audio_sensitivity
            self.save()

    def set_tuning(self, **values):
        self.engine.set_tuning(**values)
        self.save()

    def set_wallpaper_sync(self, on):
        self.settings["ambient"]["wallpaper"] = bool(on)
        self.save()
        if on:
            from .events import wallpaper
            src = wallpaper.create(self.events.emit)
            self.events.sources.append(src)
            src.start()
        else:
            for s in [s for s in self.events.sources if s.name == "wallpaper"]:
                s.stop()
                self.events.sources.remove(s)
            self.engine.set_palette([])

    def reset_settings(self, restore_keyboard=False):
        """Put every app setting back to its default; optionally restore the keyboard
        from the first-run backup. Returns a short description of what was done."""
        import copy
        import json
        self.engine.set_effect(None)
        self.engine.set_layer(None)
        self.engine.set_highlights({})
        # Mutate in place: the engine and event hub share this dict.
        self.settings.clear()
        self.settings.update(copy.deepcopy(settings_mod.DEFAULTS))
        self.save()
        e = self.engine
        e.brightness = self.settings["brightness"]
        e.speed = self.settings["speed"]
        self.set_audio_sensitivity(self.settings["audio_sensitivity"])
        e.set_tuning()
        e.paused = False
        self.set_wallpaper_sync(False)
        self.set_wallpaper_sync(self.settings["ambient"]["wallpaper"])
        done = "App settings reset to defaults."
        if restore_keyboard:
            if not FACTORY_BACKUP.exists():
                return done + " No first-run backup was found, so the keyboard was not changed."
            from .device import CMD_CONFIG, CMD_CUSTOM, CMD_PALETTE, Hive65, pause_streams
            from .keymap import BASE, FN, Keymap
            from .layout import Layout
            s = json.loads(FACTORY_BACKUP.read_text())
            with pause_streams(), Hive65() as kb:
                kb.check_signature()
                kb.write(CMD_PALETTE, bytes.fromhex(s["palette"]))
                kb.write(CMD_CUSTOM, bytes.fromhex(s["custom"]))
                km = Keymap(kb, Layout())
                km.write_raw(bytes.fromhex(s["keymap_base"]), BASE)
                km.write_raw(bytes.fromhex(s["keymap_fn"]), FN)
                kb.write(CMD_CONFIG, bytes.fromhex(s["config"]))
            done += f" Keyboard restored to its state from {s.get('time', 'the first run')}."
        return done

    def notify(self, kind, value=None, **meta):
        from .overlays import make
        self.engine.push_overlay(make(self.engine.ctx, kind, value, **meta))

    def handle(self, req):
        cmd = req.get("cmd")
        if cmd == "notify":
            self.notify(req["kind"], req.get("value"), **req.get("meta", {}))
        elif cmd == "effect":
            self.set_effect(req.get("name"), req.get("options") or None)
        elif cmd == "scene":
            self.apply_scene(req["name"])
        elif cmd in ("next", "prev"):
            return {"ok": True, "effect": self.next_favorite(1 if cmd == "next" else -1)}
        elif cmd == "brightness":
            v = str(req.get("value", "1"))
            new = self.engine.brightness + float(v) if v[0] in "+-" else float(v)
            self.set_brightness(min(1.0, max(0.05, new)))
        elif cmd == "toggle_pause":
            return {"ok": True, "paused": self.toggle_pause()}
        elif cmd == "idle":
            self.idle_since = (time.time() - 3600) if req.get("on") else None
        elif cmd == "pause":
            self.engine.paused = True
        elif cmd == "resume":
            self.engine.paused = False
        elif cmd == "status":
            return {"ok": True, "effect": self.engine.effect_name, "paused": self.engine.paused,
                    "layer": self.engine.layer_name, "scene": self.settings.get("active_scene"),
                    "automation": self.automation.status if self.automation else "",
                    "fps": round(self.engine.measured_fps, 1),
                    "error": self.engine.last_error, "sources": self.events.errors()}
        else:
            return {"ok": False, "error": f"unknown command {cmd}"}
        return {"ok": True}


def serve():
    core = Core()
    core.start()
    print("hive65 running headless (Ctrl+C to stop)")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        core.stop()
