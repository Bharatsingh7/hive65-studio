"""Context-aware automation: switch scenes by focused app, idle, time, music
or fullscreen; dim when the screen locks; shuffle favourites (playlist).

Rules are evaluated top to bottom once a second; the first matching rule
wins. When no rule matches any more, the scene the user had chosen comes back.
"""
import json
import shutil
import subprocess
import sys
import threading
import time

from . import scenes

WINDOWS = sys.platform == "win32"
LINUX = sys.platform.startswith("linux")

TRIGGERS = ("app", "idle", "time", "music", "fullscreen")

DEFAULT_RULES = [
    {"enabled": True, "trigger": "idle", "value": "5", "scene": "Screensaver"},
    {"enabled": True, "trigger": "fullscreen", "value": "", "scene": "Gaming"},
    {"enabled": True, "trigger": "app", "value": "spotify", "scene": "Music"},
    {"enabled": False, "trigger": "app", "value": "code, pycharm, idea, nvim, kitty", "scene": "Focus"},
    {"enabled": False, "trigger": "time", "value": "23:00-07:00", "scene": "Night"},
    {"enabled": False, "trigger": "music", "value": "", "scene": "Music"},
]


# ------------------------------------------------------------------ system probes
def active_app():
    """Lower-case process name (Windows) or window class (Hyprland) of the focused window."""
    try:
        if WINDOWS:
            import ctypes
            from ctypes import wintypes

            import psutil
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            pid = wintypes.DWORD()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            return psutil.Process(pid.value).name().lower()
        if LINUX and shutil.which("hyprctl"):
            w = json.loads(subprocess.run(["hyprctl", "activewindow", "-j"],
                                          capture_output=True, text=True, timeout=1).stdout or "{}")
            return (w.get("class") or "").lower()
    except Exception:
        pass
    return ""


def is_fullscreen():
    try:
        if WINDOWS:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if not hwnd or hwnd in (user32.GetDesktopWindow(), user32.GetShellWindow()):
                return False
            cls = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(hwnd, cls, 64)
            if cls.value in ("Progman", "WorkerW"):
                return False
            r = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            mon = user32.MonitorFromWindow(hwnd, 2)

            class MONITORINFO(ctypes.Structure):
                _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                            ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]
            mi = MONITORINFO(cbSize=ctypes.sizeof(MONITORINFO))
            user32.GetMonitorInfoW(mon, ctypes.byref(mi))
            m = mi.rcMonitor
            return r.left <= m.left and r.top <= m.top and r.right >= m.right and r.bottom >= m.bottom
        if LINUX and shutil.which("hyprctl"):
            w = json.loads(subprocess.run(["hyprctl", "activewindow", "-j"],
                                          capture_output=True, text=True, timeout=1).stdout or "{}")
            return bool(w.get("fullscreen"))
    except Exception:
        pass
    return False


def idle_seconds(core):
    if WINDOWS:
        import ctypes
        from ctypes import wintypes

        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]
        li = LASTINPUTINFO(cbSize=ctypes.sizeof(LASTINPUTINFO))
        ctypes.windll.user32.GetLastInputInfo(ctypes.byref(li))
        return (ctypes.windll.kernel32.GetTickCount() - li.dwTime) / 1000.0
    # Hyprland: hypridle calls `hive65 idle on/off` (see README); that sets core.idle_since.
    return time.time() - core.idle_since if core.idle_since else 0.0


def screen_locked():
    try:
        if WINDOWS:
            import ctypes
            desk = ctypes.windll.user32.OpenInputDesktop(0, False, 0x0100)  # DESKTOP_SWITCHDESKTOP
            if not desk:
                return True
            ok = ctypes.windll.user32.SwitchDesktop(desk)
            ctypes.windll.user32.CloseDesktop(desk)
            return not ok
        if LINUX and shutil.which("loginctl"):
            out = subprocess.run(["loginctl", "show-session", "auto", "-p", "LockedHint"],
                                 capture_output=True, text=True, timeout=1).stdout
            return "yes" in out
    except Exception:
        pass
    return False


def in_time_window(value, now=None):
    try:
        start, end = [v.strip() for v in value.split("-")]
    except ValueError:
        return False
    now = now or time.strftime("%H:%M")
    return start <= now < end if start < end else (now >= start or now < end)


# ------------------------------------------------------------------ runner
class Automation(threading.Thread):
    def __init__(self, core):
        super().__init__(daemon=True)
        self.core = core
        self.stopped = threading.Event()
        self.active_rule = None     # index of the rule currently driving the scene
        self.saved_state = None     # what the user had before a rule took over
        self.music_since = None
        self.last_switch = time.time()
        self.status = ""

    def stop(self):
        self.stopped.set()

    def matches(self, rule, probes):
        t, v = rule.get("trigger"), str(rule.get("value", "")).strip().lower()
        if t == "app":
            app = probes["app"]
            return bool(app) and any(x.strip() and x.strip() in app for x in v.split(","))
        if t == "idle":
            return probes["idle"] >= float(v or 5) * 60
        if t == "time":
            return in_time_window(v)
        if t == "fullscreen":
            return probes["fullscreen"]
        if t == "music":
            return probes["music"]
        return False

    def probe(self):
        rules = [r for r in self.core.settings.get("automations", []) if r.get("enabled")]
        need = {r["trigger"] for r in rules}
        music = False
        if "music" in need:
            a = self.core.engine.ctx.audio
            if a.level > 0.15:
                self.music_since = self.music_since or time.time()
            else:
                self.music_since = None
            music = bool(self.music_since and time.time() - self.music_since > 3)
        return rules, {"app": active_app() if "app" in need else "",
                       "idle": idle_seconds(self.core) if "idle" in need else 0.0,
                       "fullscreen": is_fullscreen() if "fullscreen" in need else False,
                       "music": music}

    def tick(self):
        core = self.core
        s = core.settings
        if not s.get("automation_enabled", True):
            self._release()
            return
        rules, probes = self.probe()
        match = next((r for r in rules if self.matches(r, probes)), None)
        key = None if match is None else (match["trigger"], match.get("value"), match.get("scene"))
        if key != self.active_rule:
            if match is not None:
                scene = scenes.find(core, match.get("scene"))
                if scene:
                    if self.active_rule is None:
                        self.saved_state = scenes.capture(core, "_manual")
                    scenes.apply(core, scene, remember=False)
                    self.status = f"{match['trigger']} -> {scene['name']}"
            else:
                self._release()
            self.active_rule = key
        self.lock_dim()
        self.playlist()

    def _release(self):
        if self.active_rule is not None and self.saved_state:
            scenes.apply(self.core, self.saved_state, remember=False)
        self.active_rule, self.saved_state = None, None
        self.status = ""

    def lock_dim(self):
        if self.core.settings.get("dim_on_lock", True):
            self.core.engine.dim = 0.0 if screen_locked() else 1.0

    def playlist(self):
        p = self.core.settings.get("playlist", {})
        if not p.get("enabled") or self.active_rule is not None:
            return
        now = time.time()
        due = now - self.last_switch >= float(p.get("minutes", 5)) * 60
        if p.get("on_drops") and now - self.last_switch > 20:
            a = self.core.engine.ctx._audio
            if a is not None and a.kick > 0.95 and a.level > 0.6:
                due = True
        if due:
            self.last_switch = now
            self.core.next_favorite(shuffle=p.get("shuffle", True))

    def run(self):
        while not self.stopped.is_set():
            try:
                self.tick()
            except Exception as e:
                self.status = f"error: {e}"
            self.stopped.wait(1.0)
