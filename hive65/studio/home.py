"""Home dashboard: big live keyboard, transport controls, quick toggles, shelves."""
import time

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ..effects import load_all
from . import theme
from .pages import card, h2, muted
from .widgets import (AuroraHeader, FlowLayout, HeroKeyboard, Tile, ToggleSwitch, clear_layout,
                      keyboard_pixmap, slider_row, toast)


def icon_button(icon, tip, fn, size=40):
    b = QPushButton(objectName="icon")
    ic = theme.icon(icon)
    if ic.isNull():
        b.setText(tip[:1])
    else:
        b.setIcon(ic)
        b.setIconSize(QSize(20, 20))
    b.setFixedSize(size, size)
    b.setToolTip(tip)
    b.setCursor(Qt.PointingHandCursor)
    b.clicked.connect(fn)
    return b


def greeting():
    h = time.localtime().tm_hour
    return "Good morning" if 5 <= h < 12 else "Good afternoon" if h < 18 else "Good evening"


class HomePage(QWidget):
    def __init__(self, core, main):
        super().__init__()
        self.core, self.main = core, main
        self._shelf_key = None
        self._thumb_queue = []
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 20, 24, 20)
        v.setSpacing(16)

        # --- hero: now playing + transport + big keyboard on an aurora tinted by the LEDs
        self.hero = AuroraHeader()
        hv = QVBoxLayout(self.hero)
        hv.setContentsMargins(22, 18, 22, 12)
        hv.setSpacing(6)
        top = QHBoxLayout()
        text = QVBoxLayout()
        text.setSpacing(2)
        self.kicker = QLabel(objectName="kicker")
        self.now = QLabel(objectName="h1")
        self.now.setWordWrap(True)
        self.sub = muted("")
        text.addWidget(self.kicker)
        text.addWidget(self.now)
        text.addWidget(self.sub)
        top.addLayout(text, 1)
        self.prev_btn = icon_button("mdi6.skip-previous", "Previous favourite", lambda: self._step(-1))
        self.pause_btn = icon_button("mdi6.pause", "Pause / resume live effects", self._toggle_pause, 48)
        self.next_btn = icon_button("mdi6.skip-next", "Next favourite", lambda: self._step(1))
        self.shuffle_btn = icon_button("mdi6.shuffle-variant", "Random favourite", self._shuffle)
        for b in (self.prev_btn, self.pause_btn, self.next_btn, self.shuffle_btn):
            top.addWidget(b, 0, Qt.AlignVCenter)
        hv.addLayout(top)
        chips = QWidget()
        self.chips = FlowLayout(chips, spacing=8)
        self.chip = {}
        for key in ("device", "fps", "scene", "auto", "music"):
            lab = QLabel(objectName="statusChip")
            self.chips.addWidget(lab)
            self.chip[key] = lab
        hv.addWidget(chips)
        self.keyboard = HeroKeyboard(labels=True, reflection=True)
        self.keyboard.setMinimumHeight(230)
        hv.addWidget(self.keyboard, 1)
        v.addWidget(self.hero)

        # --- quick controls
        s = core.settings
        toggles = QWidget()
        tf = FlowLayout(toggles, spacing=18)
        self.t_live = self._toggle(tf, "Live effects", not core.engine.paused, self._set_live)
        self.t_wall = self._toggle(tf, "Wallpaper colours", s["ambient"].get("wallpaper", True),
                                   core.set_wallpaper_sync)
        self.t_notif = self._toggle(tf, "Notifications", s["notifications"].get("enabled", True),
                                    self._set_notifications)
        self.t_auto = self._toggle(tf, "Automations", s.get("automation_enabled", True),
                                   lambda on: self._set("automation_enabled", on))
        self.t_play = self._toggle(tf, "Playlist (auto-shuffle)", s["playlist"].get("enabled", False),
                                   self._set_playlist)
        self.t_lock = self._toggle(tf, "Dim when locked", s.get("dim_on_lock", True),
                                   lambda on: self._set("dim_on_lock", on))
        sliders = QHBoxLayout()
        sliders.setSpacing(24)
        sliders.addWidget(slider_row("Brightness", 0.05, 1.0, s["brightness"], core.set_brightness), 1)
        sliders.addWidget(slider_row("Music sensitivity", 0.25, 3.0, s.get("audio_sensitivity", 1.0),
                                     core.set_audio_sensitivity), 1)
        sw = QWidget()
        sw.setLayout(sliders)
        v.addWidget(card(h2("Quick controls"), toggles, sw))

        # --- shelves
        self.shelves = {}
        for key, title, hint in (("favorites", "Favourites", "Star effects in the Effects gallery to pin them here."),
                                 ("scenes", "Scenes", "One click sets effect, layer, highlights and brightness."),
                                 ("recent", "Recently played", "")):
            head = QHBoxLayout()
            head.addWidget(h2(title))
            head.addStretch()
            if key == "scenes":
                more = QPushButton("Manage scenes")
                more.clicked.connect(lambda: self.main.go_to("Scenes & Mixer"))
                head.addWidget(more)
            elif key == "favorites":
                more = QPushButton("Browse effects")
                more.clicked.connect(lambda: self.main.go_to("Effects"))
                head.addWidget(more)
            hw = QWidget()
            hw.setLayout(head)
            host = QWidget()
            flow = FlowLayout(host, spacing=12)
            self.shelves[key] = (flow, muted(hint) if hint else None)
            parts = [hw] + ([self.shelves[key][1]] if hint else []) + [host]
            v.addWidget(card(*parts))
        v.addStretch()

        QTimer(self, timeout=self._update_status, interval=500).start()
        self._update_status()

    # ------------------------------------------------------------------ helpers
    def _toggle(self, flow, text, on, fn):
        t = ToggleSwitch(text)
        t.setChecked(bool(on))
        t.toggled.connect(fn)
        flow.addWidget(t)
        return t

    def _set(self, key, value):
        self.core.settings[key] = value
        self.core.save()

    def _set_live(self, on):
        self.core.engine.paused = not on

    def _set_notifications(self, on):
        self.core.settings["notifications"]["enabled"] = bool(on)
        self.core.save()

    def _set_playlist(self, on):
        self.core.settings["playlist"]["enabled"] = bool(on)
        self.core.save()
        if on and not self.core.settings.get("favorites"):
            toast(self, "Add some favourites first: the playlist shuffles through them.")

    def _toggle_pause(self):
        paused = self.core.toggle_pause()
        toast(self, "Live effects paused: the keyboard shows its own lighting" if paused
              else "Live effects resumed")

    def _step(self, step):
        if self.core.next_favorite(step) is None:
            toast(self, "No favourites yet: star some effects in the Effects gallery.")
        self.main.effect_changed()

    def _shuffle(self):
        if self.core.next_favorite(shuffle=True) is None:
            toast(self, "No favourites yet: star some effects in the Effects gallery.")
        self.main.effect_changed()

    def set_live(self, colors):
        self.keyboard.set_live(colors)
        self.hero.set_live(colors)

    # ------------------------------------------------------------------ status
    def _update_status(self):
        if not self.isVisible():
            return
        e, s = self.core.engine, self.core.settings
        name = e.effect_name
        reg = load_all()
        self.kicker.setText(f"{greeting().upper()}  ·  NOW PLAYING")
        if name and name in reg:
            self.now.setText(name.replace("_", " ").title())
            extra = f"  +  {e.layer_name.replace('_', ' ')} layer" if e.layer_name else ""
            self.sub.setText(reg[name].description + extra)
        else:
            self.now.setText("Keyboard's own lighting")
            self.sub.setText("Pick a favourite, a scene or anything from the Effects gallery.")
        ic = theme.icon("mdi6.play" if e.paused else "mdi6.pause")
        if not ic.isNull():
            self.pause_btn.setIcon(ic)
        if self.t_live.isChecked() == e.paused:
            self.t_live.blockSignals(True)
            self.t_live.setChecked(not e.paused)
            self.t_live.blockSignals(False)
        if e.last_error:
            dev = "⚠ " + str(e.last_error)[:40]
        elif e._kb is not None:
            dev = "● Keyboard connected"
        else:
            dev = "○ Keyboard idle"
        self.chip["device"].setText(dev)
        self.chip["fps"].setText(f"{e.measured_fps:.0f} fps" if name and not e.paused else "– fps")
        self.chip["scene"].setText(f"Scene: {s.get('active_scene') or 'none'}")
        auto = self.core.automation.status if self.core.automation else ""
        self.chip["auto"].setText(f"Auto: {auto}" if auto else
                                  ("Automations on" if s.get("automation_enabled", True) else "Automations off"))
        a = e.ctx._audio
        if a is not None:
            bars = "▁▂▃▄▅▆▇█"
            self.chip["music"].setText("♪ " + bars[min(7, int(a.level * 8))] + (f" {a.bpm:.0f} bpm"
                                                                                if getattr(a, "bpm", 0) else ""))
            self.chip["music"].show()
        else:
            self.chip["music"].hide()
        self.chips.update()

    # ------------------------------------------------------------------ shelves
    def showEvent(self, e):
        super().showEvent(e)
        QTimer.singleShot(0, self.refresh_shelves)

    def refresh_shelves(self, force=False):
        s = self.core.settings
        key = (tuple(s.get("favorites", [])), tuple(sc["name"] for sc in s.get("scenes", [])),
               tuple(s.get("recent", [])[:8]), s.get("active_scene"))
        if key == self._shelf_key and not force:
            return
        self._shelf_key = key
        reg = load_all()
        self._thumb_queue = []
        for flow, hint in self.shelves.values():
            clear_layout(flow)
        self._fill("favorites", [n for n in s.get("favorites", []) if n in reg], reg)
        self._fill("recent", [n for n in s.get("recent", [])[:8] if n in reg], reg)
        flow, _ = self.shelves["scenes"]
        for sc in s.get("scenes", []):
            eff = sc.get("effect")
            cat = reg[eff].category if eff in reg else "ambient"
            sub = (eff or "own lighting").replace("_", " ")
            if sc.get("layer"):
                sub += " + " + sc["layer"].replace("_", " ")
            active = sc["name"] == s.get("active_scene")
            t = Tile(("● " if active else "") + sc["name"], sub, accent=theme.CATEGORY_COLORS.get(cat))
            t.clicked.connect(lambda n=sc["name"]: self._apply_scene(n))
            flow.addWidget(t)
            if eff in reg:
                self._thumb_queue.append((t, eff))
        hint = self.shelves["favorites"][1]
        if hint is not None:
            hint.setVisible(not s.get("favorites"))
        QTimer.singleShot(30, self._next_thumb)

    def _fill(self, key, names, reg):
        flow, _ = self.shelves[key]
        for n in names:
            cat = reg[n].category
            t = Tile(n.replace("_", " ").title(), cat, accent=theme.CATEGORY_COLORS.get(cat))
            t.setToolTip(reg[n].description)
            t.clicked.connect(lambda n=n: self._play(n))
            flow.addWidget(t)
            self._thumb_queue.append((t, n))

    def _next_thumb(self):
        from .thumbs import cached_thumbnail
        if not self._thumb_queue:
            return
        tile, name = self._thumb_queue.pop(0)
        try:
            tile.set_pixmap(keyboard_pixmap(cached_thumbnail(name, self.core.engine.ctx.palette), 152, 52))
        except Exception:
            pass   # tile deleted by a refresh, or the effect failed to render
        QTimer.singleShot(10, self._next_thumb)

    def _play(self, name):
        self.core.set_effect(name)
        self.main.effect_changed()
        toast(self, f"Playing {name.replace('_', ' ')}")

    def _apply_scene(self, name):
        try:
            self.core.apply_scene(name)
        except Exception as e:
            toast(self, f"Couldn't apply {name}: {e}")
            return
        self.main.effect_changed()
        toast(self, f"Scene: {name}")
        self.refresh_shelves()
