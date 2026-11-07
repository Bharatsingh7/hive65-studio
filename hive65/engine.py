"""Frame loop and compositor.

Layers, bottom to top:
    base      the current effect (or nothing: the keyboard's own hardware mode)
    overlays  short notification animations with per-pixel alpha
The result goes through LEDTuning and is streamed to the keyboard.
"""
import threading
import time

import numpy as np

from .canvas import Canvas, LEDTuning
from .device import CMD_FRAME, DeviceError, Hive65, streams_paused


class Context:
    """Shared services handed to effects; audio and keys start on first use."""

    def __init__(self, canvas):
        self.canvas = canvas
        self.layout = canvas.layout
        self.palette = []          # list of RGB arrays from wallpaper/screen sync
        self.audio_sensitivity = 1.0
        self._audio = None
        self._keys = None

    @property
    def audio(self):
        if self._audio is None:
            from .audio import AudioAnalyzer
            self._audio = AudioAnalyzer(bands=self.canvas.w)
            self._audio.sensitivity = self.audio_sensitivity
        return self._audio

    @property
    def keys(self):
        if self._keys is None:
            from .keyevents import KeyListener
            self._keys = KeyListener()
        return self._keys

    def pressed_keys(self):
        """Layout keys pressed since the last call (shared by base and overlays)."""
        if not hasattr(self, "_frame_presses"):
            return [self.layout.by_vk[vk] for vk in self.keys.drain() if vk in self.layout.by_vk]
        return self._frame_presses

    def begin_frame(self):
        if self._keys is not None:
            self._frame_presses = [self.layout.by_vk[vk] for vk in self._keys.drain()
                                   if vk in self.layout.by_vk]

    def close(self):
        if self._audio:
            self._audio.close()


class Overlay:
    """A short animation drawn over the base effect.

    Subclasses draw into self.canvas and set self.alpha (h x w, 0..1); they
    finish when t >= duration. `key` lets a newer overlay replace an older
    one of the same kind (e.g. repeated volume changes).
    """

    duration = 1.5
    key = None

    def __init__(self, ctx):
        self.ctx = ctx
        self.canvas = Canvas(ctx.layout)
        self.alpha = np.zeros((self.canvas.h, self.canvas.w))
        self.start = None

    def render(self, t, dt):
        raise NotImplementedError

    def fade(self, t, fade_in=0.08, fade_out=0.35):
        """Envelope 0..1 for the overlay as a whole."""
        return min(1.0, t / fade_in) * min(1.0, max(0.0, (self.duration - t) / fade_out))


BLENDS = ("screen", "add", "max", "multiply", "mix")


def blend(base, top, mode, opacity):
    """Combine two h x w x 3 frames (0..1) with a blend mode and opacity."""
    o = max(0.0, min(1.0, opacity))
    if mode == "add":
        return np.minimum(1.0, base + top * o)
    if mode == "max":
        return np.maximum(base, top * o)
    if mode == "multiply":
        return base * (1 - o + top * o)
    if mode == "mix":
        return base * (1 - o) + top * o
    return 1 - (1 - base) * (1 - top * o)   # screen


class Engine:
    def __init__(self, settings=None, fps=None):
        from . import settings as settings_mod
        self.settings = settings or settings_mod.load()
        self.canvas = Canvas()
        self.ctx = Context(self.canvas)
        self.tuning = LEDTuning.from_settings(self.settings.get("tuning", {}))
        self.brightness = float(self.settings.get("brightness", 1.0))
        self.fps = fps or int(self.settings.get("fps", 60))
        self.speed = float(self.settings.get("speed", 1.6))
        self.clock = 0.0           # effect time, advanced by dt * speed
        self.ctx.audio_sensitivity = float(self.settings.get("audio_sensitivity", 1.0))
        self.effect = None
        self.effect_name = None
        self.effect_options = {}
        # Mixer: a second effect blended over the base.
        self.layer = None
        self.layer_name = None
        self.layer_canvas = Canvas(self.canvas.layout)
        self.layer_blend = "screen"
        self.layer_opacity = 0.7
        # Cross-fade from the previous effect's last frame.
        self._fade_from = None
        self._fade_t = 0.0
        self.fade_time = 0.6
        # Keys that stay lit over everything: {key name: rgb}
        self.highlights = {}
        self.dim = 1.0             # idle / screen-lock dimming, multiplies brightness
        self.measured_fps = 0.0
        self.overlays = []
        self.listeners = []        # callables(key_colors) for live previews
        self.paused = False        # True: send nothing, keyboard shows its own mode
        self.last_error = None
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread = None
        self._kb = None
        self._t0 = time.perf_counter()

    # --- control (thread-safe) -------------------------------------------------
    def set_effect(self, name, options=None):
        from .effects import load_all
        registry = load_all()
        with self._lock:
            new = registry[name](self.ctx, **(options or {})) if name is not None else None
            if self.effect is not None:
                self._fade_from = self.canvas.pixels.copy()   # cross-fade from here
                self._fade_t = 0.0
                try:
                    self.effect.close()
                except Exception:
                    pass
            if name is None:
                self.effect, self.effect_name, self.effect_options = None, None, {}
                self._fade_from = None
                return
            self.effect = new
            self.effect_name = name
            self.effect_options = dict(options or {})
            self.clock = 0.0
            self.canvas.clear()

    def set_layer(self, name, options=None, blend=None, opacity=None):
        """Mixer: run a second effect blended over the base (None removes it)."""
        from .effects import load_all
        registry = load_all()
        with self._lock:
            if self.layer is not None:
                try:
                    self.layer.close()
                except Exception:
                    pass
            self.layer = registry[name](self.ctx, **(options or {})) if name else None
            self.layer_name = name
            self.layer_canvas.clear()
            if blend:
                self.layer_blend = blend
            if opacity is not None:
                self.layer_opacity = float(opacity)

    def set_highlights(self, keys):
        """{key name: rgb} kept lit on top of every effect (e.g. WASD while gaming)."""
        with self._lock:
            self.highlights = {k: np.asarray(v, dtype=float) for k, v in (keys or {}).items()}
            lay = self.canvas.layout
            self._highlight_cells = [(self.canvas._key_cells.get(lay.by_name[k.lower()].led, []), rgb)
                                     for k, rgb in self.highlights.items() if k.lower() in lay.by_name]

    def push_overlay(self, overlay):
        with self._lock:
            if overlay.key:
                self.overlays = [o for o in self.overlays if o.key != overlay.key]
            overlay.start = None
            self.overlays.append(overlay)

    def set_palette(self, colors):
        self.ctx.palette = [np.asarray(c, dtype=float) for c in colors]

    def set_tuning(self, **values):
        d = dict(self.settings.get("tuning", {}), **values)
        self.settings["tuning"] = d
        self.tuning = LEDTuning.from_settings(d)

    # --- loop --------------------------------------------------------------------
    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        if self._kb:
            self._kb.close()
            self._kb = None
        self.ctx.close()

    def compose(self, now, dt):
        """Render one frame; returns the composited canvas or None for 'hardware mode'."""
        with self._lock:
            self.ctx.begin_frame()
            base_active = self.effect is not None
            sdt = min(dt, 0.1) * self.speed   # capped so a stall doesn't make things jump
            if base_active:
                self.clock += sdt
                self.effect.render(self.canvas, self.clock, sdt)
            else:
                self.canvas.clear()
            out = np.clip(self.canvas.pixels, 0, 1)   # some effects overshoot; blends need 0..1
            if self._fade_from is not None:
                self._fade_t += dt
                f = min(1.0, self._fade_t / self.fade_time)
                f = f * f * (3 - 2 * f)
                out = self._fade_from * (1 - f) + out * f
                if f >= 1:
                    self._fade_from = None
            if self.layer is not None:
                self.layer.render(self.layer_canvas, self.clock, sdt)
                out = blend(out, np.clip(self.layer_canvas.pixels, 0, 1), self.layer_blend, self.layer_opacity)
                base_active = True
            if self.highlights:
                for cells, rgb in self._highlight_cells:
                    for r, c in cells:
                        out[r, c] = rgb
                base_active = True
            alive = []
            for ov in self.overlays:
                if ov.start is None:
                    ov.start = now
                t = now - ov.start
                if t >= ov.duration:
                    continue
                ov.render(t, dt)
                a = np.clip(ov.alpha, 0, 1)[..., None]
                out = out * (1 - a) + ov.canvas.pixels * a
                alive.append(ov)
            self.overlays = alive
            if not base_active and not alive:
                return None
            result = Canvas.__new__(Canvas)
            result.__dict__.update(self.canvas.__dict__)
            result.pixels = out
            return result

    def _send(self, frame):
        if self._kb is None:
            self._kb = Hive65()
        self._kb.write(CMD_FRAME, frame)

    def _loop(self):
        import sys
        if sys.platform == "win32":
            import ctypes
            ctypes.windll.winmm.timeBeginPeriod(1)   # 1 ms sleeps instead of 15.6 ms
        period = 1.0 / self.fps
        last = time.perf_counter()
        while not self._stop.is_set():
            now = time.perf_counter()
            dt, last = now - last, now
            try:
                frame_canvas = self.compose(now, dt)
                if frame_canvas is not None:
                    colors = frame_canvas.key_colors()
                    for cb in list(self.listeners):
                        cb(colors)
                    if not self.paused and not streams_paused():
                        self._send(frame_canvas.to_frame(self.brightness * self.dim, self.tuning))
                else:
                    for cb in list(self.listeners):
                        cb(None)
                self.last_error = None
            except DeviceError as e:
                self.last_error = str(e)
                if self._kb:
                    self._kb.close()
                self._kb = None
                time.sleep(1)
            except Exception as e:  # a buggy effect must not kill the app
                self.last_error = f"{type(e).__name__}: {e}"
                time.sleep(0.2)
            if dt > 0:
                self.measured_fps = self.measured_fps * 0.95 + (1.0 / dt) * 0.05
            time.sleep(max(0.0, period - (time.perf_counter() - now)))


def run(effect_cls, fps=30, brightness=1.0, duration=None, options=None, device=None,
        stop=None, sensitivity=None):
    """Stream one effect until `duration` elapses or `stop` is set (CLI / scripts)."""
    eng = Engine(fps=fps)
    eng.brightness = brightness
    if sensitivity is not None:
        eng.ctx.audio_sensitivity = sensitivity
    if device is not None:
        eng._kb = device
    eng.effect = effect_cls(eng.ctx, **(options or {}))
    eng.effect_name = getattr(effect_cls, "effect_name", None)
    eng.start()
    t0 = time.time()
    try:
        while (duration is None or time.time() - t0 < duration) and not (stop and stop.is_set()):
            time.sleep(0.05)
    finally:
        if device is not None:
            eng._kb = None
        eng.stop()
