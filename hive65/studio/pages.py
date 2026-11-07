"""Studio pages."""
import json
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTime, QTimer
from PySide6.QtWidgets import (QBoxLayout, QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
                               QScrollArea, QTableWidget, QTableWidgetItem, QTimeEdit,
                               QVBoxLayout, QWidget)

from ..effects import CATEGORIES, load_all, user_effects_dir
from . import theme
from .widgets import (ColorButton, EffectCard, HeroKeyboard, KeyboardView, ParamPanel, ToggleSwitch,
                      hex_to_rgb, keyboard_pixmap, slider_row, swatch, toast)


def header(title, subtitle=None):
    w = QWidget()
    v = QVBoxLayout(w)
    v.setContentsMargins(0, 0, 0, 6)
    h = QLabel(title)
    h.setObjectName("h1")
    v.addWidget(h)
    if subtitle:
        s = QLabel(subtitle)
        s.setObjectName("muted")
        s.setWordWrap(True)
        v.addWidget(s)
    return w


def card(*widgets, spacing=10):
    f = QFrame()
    f.setObjectName("card")
    v = QVBoxLayout(f)
    v.setContentsMargins(16, 14, 16, 14)
    v.setSpacing(spacing)
    for w in widgets:
        v.addWidget(w) if isinstance(w, QWidget) else v.addLayout(w)
    return f


def h2(text):
    lab = QLabel(text)
    lab.setObjectName("h2")
    return lab


def muted(text):
    lab = QLabel(text)
    lab.setObjectName("muted")
    lab.setWordWrap(True)
    return lab


def scroll(widget):
    s = QScrollArea()
    s.setWidgetResizable(True)
    s.setWidget(widget)
    return s


def run_device(parent, fn):
    """Run a keyboard config action with live frames paused; show errors."""
    from ..device import Hive65, pause_streams
    try:
        with pause_streams(), Hive65() as kb:
            return fn(kb)
    except Exception as e:
        QMessageBox.warning(parent, "Keyboard", f"Couldn't talk to the keyboard:\n{e}")
        return None


# ----------------------------------------------------------------------------- Effects
class EffectsPage(QWidget):
    def __init__(self, core):
        super().__init__()
        self.core = core
        self.registry = load_all()
        self.cards = {}
        # Side by side when wide; the settings panel moves under the gallery when narrow.
        self.root = root = QBoxLayout(QBoxLayout.LeftToRight, self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(18)

        left = QVBoxLayout()
        left.addWidget(header("Effects", f"{len(self.registry)} live effects. Click one to play it on the keyboard."))
        self.preview = HeroKeyboard(labels=True, reflection=False)
        self.preview.setMinimumHeight(150)
        left.addWidget(card(self.preview))

        chips = QHBoxLayout()
        chips.setSpacing(6)
        self.chip_buttons = {}
        for cat in ("all",) + CATEGORIES:
            b = QPushButton(cat.title())
            b.setObjectName("chip")
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, c=cat: self.filter(c))
            chips.addWidget(b)
            self.chip_buttons[cat] = b
        chips.addStretch()
        left.addLayout(chips)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search effects...")
        self.search.textChanged.connect(lambda _: self.filter(self.category))
        left.addWidget(self.search)

        grid_host = QWidget()
        self.grid = QGridLayout(grid_host)
        self.grid.setSpacing(12)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.grid_host = grid_host
        for name in self._sorted(self.registry):
            self._make_card(name)
        self.grid_scroll = scroll(grid_host)
        self.grid_scroll.setMinimumHeight(330)
        left.addWidget(self.grid_scroll, 1)
        root.addLayout(left, 3)

        right = QVBoxLayout()
        self.title = QLabel("Keyboard's own lighting")
        self.title.setWordWrap(True)
        self.title.setObjectName("h1")
        self.desc = muted("No live effect is running; the keyboard shows its stored mode.")
        right.addWidget(self.title)
        right.addWidget(self.desc)
        self.params = ParamPanel()
        self.params.changed.connect(self.param_changed)
        right.addWidget(card(h2("Effect settings"), self.params))
        music = QWidget()
        mv = QVBoxLayout(music)
        mv.setContentsMargins(0, 0, 0, 0)
        mv.addWidget(slider_row("Sensitivity", 0.25, 3.0, core.settings.get("audio_sensitivity", 1.0),
                                core.set_audio_sensitivity))
        mv.addWidget(muted("Higher reacts to quiet music and more beats; lower only to loud parts. "
                           "Applies to every music effect."))
        self.music_card = card(h2("Music"), music)
        right.addWidget(self.music_card)
        glob = QWidget()
        gv = QVBoxLayout(glob)
        gv.setContentsMargins(0, 0, 0, 0)
        gv.addWidget(slider_row("Brightness", 0.05, 1.0, core.settings["brightness"], core.set_brightness))
        gv.addWidget(slider_row("Animation speed", 0.25, 4.0, core.settings.get("speed", 1.6), self.set_speed))
        right.addWidget(card(h2("Global"), glob))
        stop = QPushButton("Stop effect (use keyboard's own lighting)")
        stop.clicked.connect(lambda: self.apply(None))
        right.addWidget(stop)
        right.addStretch()
        self.side = side = QWidget()
        side.setLayout(right)
        side.setFixedWidth(290)
        root.addWidget(side)

        self.category = "all"
        self.filter("all")
        self._thumb_queue = list(self.cards)
        QTimer.singleShot(200, self._next_thumb)
        self.select(core.engine.effect_name)

    def _sorted(self, names):
        return sorted(names, key=lambda n: (CATEGORIES.index(self.registry[n].category)
                                            if self.registry[n].category in CATEGORIES else 9, n))

    def _make_card(self, name):
        c = EffectCard(name, self.registry[name], name in self.core.settings.get("favorites", []),
                       self.core.engine.ctx.palette)
        c.setParent(self.grid_host)
        c.hide()
        c.clicked.connect(self.apply)
        c.favToggled.connect(self.toggle_favorite)
        self.cards[name] = c
        return c

    def toggle_favorite(self, name):
        on = self.core.toggle_favorite(name)
        self.cards[name].set_favorite(on)
        toast(self, f"{'Added' if on else 'Removed'} {name.replace('_', ' ')} "
                    f"{'to' if on else 'from'} favourites")
        win = self.window()
        if hasattr(win, "favorites_changed"):
            win.favorites_changed()

    def refresh_favorites(self):
        favs = self.core.settings.get("favorites", [])
        for n, c in self.cards.items():
            c.set_favorite(n in favs)

    def sync_cards(self):
        """Pick up effects added or removed since start (Effect Builder designs)."""
        from .thumbs import _CACHE
        self.registry = load_all()
        for n in [n for n in self.cards if n not in self.registry]:
            c = self.cards.pop(n)
            self.grid.removeWidget(c)
            c.hide()
            c.deleteLater()
        for n in self.registry:
            if n not in self.cards:
                self._make_card(n)
            if self.registry[n].category == "custom":   # designs change in place
                self.cards[n].cls = self.registry[n]
                _CACHE.pop(n, None)
                self._thumb_queue.append(n)
        self.cards = {n: self.cards[n] for n in self._sorted(self.cards)}
        self.filter(self.category)
        QTimer.singleShot(50, self._next_thumb)

    def set_speed(self, v):
        self.core.engine.speed = self.core.settings["speed"] = float(v)
        self.core.save()

    def _next_thumb(self):
        from .thumbs import cached_thumbnail
        if not self._thumb_queue:
            return
        name = self._thumb_queue.pop(0)
        try:
            if name in self.cards:
                colors = cached_thumbnail(name, self.core.engine.ctx.palette)
                self.cards[name].set_thumbnail(keyboard_pixmap(colors))
        except Exception:
            pass
        QTimer.singleShot(15, self._next_thumb)

    def filter(self, cat):
        self.category = cat
        for c, b in self.chip_buttons.items():
            b.setChecked(c == cat)
        q = self.search.text().lower()
        # Move cards within the grid; never reparent them (detaching widgets in the
        # middle of a resize crashes Qt).
        for c in self.cards.values():
            self.grid.removeWidget(c)
        shown = [n for n, c in self.cards.items()
                 if (cat == "all" or self.registry[n].category == cat)
                 and (not q or q in n or q in self.registry[n].description.lower())]
        cols = self._columns()
        self._cols = cols
        for n, c in self.cards.items():
            c.setVisible(n in shown)
        for i, n in enumerate(shown):
            self.grid.addWidget(self.cards[n], i // cols, i % cols)

    NARROW = 900   # page width below which the settings panel goes under the gallery

    def _columns(self):
        avail = self.width() - 48 - (0 if self.width() < self.NARROW else 290 + 18) - 20
        return max(1, avail // 224)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        # Re-flow once the user stops dragging, outside Qt's resize handling.
        if not hasattr(self, "_relayout"):
            self._relayout = QTimer(self, singleShot=True, interval=80, timeout=self._apply_layout)
        self._relayout.start()

    def _apply_layout(self):
        narrow = self.width() < self.NARROW
        if narrow != (self.root.direction() == QBoxLayout.TopToBottom):
            self.root.setDirection(QBoxLayout.TopToBottom if narrow else QBoxLayout.LeftToRight)
            if narrow:
                self.side.setMinimumWidth(0)
                self.side.setMaximumWidth(16777215)
            else:
                self.side.setFixedWidth(290)
        if self._columns() != getattr(self, "_cols", None):
            self.filter(self.category)

    def apply(self, name):
        self.core.set_effect(name)
        self.select(name)

    def select(self, name):
        for n, c in self.cards.items():
            c.set_active(n == name)
        if not name:
            self.title.setText("Keyboard's own lighting")
            self.desc.setText("No live effect is running; the keyboard shows its stored mode.")
            self.params.clear()
            self.music_card.setVisible(False)
            return
        cls = self.registry[name]
        self.music_card.setVisible(cls.category == "music")
        self.title.setText(name.replace("_", " ").title())
        self.desc.setText(cls.description)
        self.params.build(cls, self.core.settings["effect_options"].get(name, {}))

    def param_changed(self, key, value):
        if self.core.engine.effect_name:
            self.core.set_option(self.core.engine.effect_name, key, value)


# ----------------------------------------------------------------------------- Keyboard
class KeyboardPage(QWidget):
    """Per-key colour painter (stored Self-define mode) and key remapper."""

    def __init__(self, core):
        super().__init__()
        self.core = core
        from ..keymap import CONSUMER, USAGES
        self.actions = sorted(USAGES) + sorted(CONSUMER) + ["lctrl", "lshift", "lalt", "lwin",
                                                            "rctrl", "rshift", "ralt"]
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 20, 24, 20)
        v.addWidget(header("Keyboard", "Paint per-key colours that stay on the keyboard, or remap any key. "
                                       "Click a key to select it."))
        self.view = KeyboardView()
        self.view.setMinimumHeight(200)
        self.view.override = {}
        self.view.keyClicked.connect(self.key_clicked)
        v.addWidget(card(self.view))

        row = QHBoxLayout()
        # painter
        paint = QWidget()
        pv = QVBoxLayout(paint)
        pv.setContentsMargins(0, 0, 0, 0)
        brush_row = QHBoxLayout()
        brush_row.addWidget(QLabel("Brush"))
        self.brush = ColorButton("#ff0050")
        brush_row.addWidget(self.brush)
        self.paint_on = ToggleSwitch("Paint on click")
        self.paint_on.setChecked(True)
        brush_row.addWidget(self.paint_on)
        self.erase = ToggleSwitch("Eraser")
        brush_row.addWidget(self.erase)
        brush_row.addStretch()
        pv.addLayout(brush_row)
        btns = QHBoxLayout()
        for text, fn in (("Load from keyboard", self.load_custom), ("Fill all", self.fill_all),
                         ("Clear", self.clear_custom)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            btns.addWidget(b)
        save = QPushButton("Save to keyboard")
        save.setObjectName("primary")
        save.clicked.connect(self.save_custom)
        btns.addWidget(save)
        pv.addLayout(btns)
        pv.addWidget(muted("Saving switches the keyboard to its Self-define mode and stops any live effect."))
        row.addWidget(card(h2("Per-key colours"), paint), 1)

        # remap
        remap = QWidget()
        rv = QVBoxLayout(remap)
        rv.setContentsMargins(0, 0, 0, 0)
        self.sel_label = QLabel("Selected key: —")
        rv.addWidget(self.sel_label)
        self.current = muted("")
        rv.addWidget(self.current)
        r2 = QHBoxLayout()
        self.layer = QComboBox()
        self.layer.addItems(["Base layer", "FN layer"])
        self.layer.currentIndexChanged.connect(lambda _: self.refresh_mapping())
        self.action = QComboBox()
        self.action.setEditable(True)
        self.action.addItems(self.actions)
        self.action.setCurrentText("esc")
        r2.addWidget(self.layer)
        r2.addWidget(self.action, 1)
        rv.addLayout(r2)
        rv.addWidget(muted("Combos work too: type e.g. ctrl+c, ctrl+shift+esc, or a raw 0x... value."))
        b3 = QHBoxLayout()
        apply = QPushButton("Apply remap")
        apply.setObjectName("primary")
        apply.clicked.connect(self.apply_remap)
        reset = QPushButton("Restore default for key")
        reset.clicked.connect(self.reset_key)
        b3.addWidget(apply)
        b3.addWidget(reset)
        rv.addLayout(b3)
        row.addWidget(card(h2("Remap"), remap), 1)
        v.addLayout(row)
        v.addStretch()
        self.keymaps = {}

    def key_clicked(self, name):
        from .widgets import layout
        k = layout().key(name)
        self.sel_label.setText(f"Selected key: {name}")
        if self.paint_on.isChecked():
            if self.erase.isChecked():
                self.view.override.pop(k.led, None)
            else:
                self.view.override[k.led] = tuple(c / 255 for c in hex_to_rgb(self.brush.color))
        self.refresh_mapping()

    def refresh_mapping(self):
        from ..keymap import BASE, FN, Keymap, describe
        from .widgets import layout
        name = self.view.selected
        if not name:
            return
        layer = FN if self.layer.currentIndex() else BASE
        if layer not in self.keymaps:
            self.keymaps[layer] = run_device(self, lambda kb: Keymap(kb, layout()).get(layer)) or {}
        val = self.keymaps[layer].get(name)
        self.current.setText(f"Currently: {describe(val)}" if val is not None else "")

    def load_custom(self):
        from ..lighting import Lighting
        colors = run_device(self, lambda kb: Lighting(kb).get_custom())
        if colors is not None:
            self.view.override = {led: tuple(c / 255 for c in rgb) for led, rgb in colors.items()}

    def fill_all(self):
        from .widgets import layout
        rgb = tuple(c / 255 for c in hex_to_rgb(self.brush.color))
        self.view.override = {k.led: rgb for k in layout().keys}

    def clear_custom(self):
        self.view.override = {}

    def save_custom(self):
        from ..lighting import Lighting
        colors = {led: tuple(int(round(c * 255)) for c in rgb) for led, rgb in self.view.override.items()}
        self.core.set_effect(None)
        if run_device(self, lambda kb: Lighting(kb).set_custom(colors) or True):
            toast(self, f"Saved {len(colors)} key colours to the keyboard.")

    def apply_remap(self):
        from ..keymap import BASE, FN, Keymap
        from .widgets import layout
        name = self.view.selected
        if not name:
            return
        layer = FN if self.layer.currentIndex() else BASE
        action = self.action.currentText().strip()
        try:
            run_device(self, lambda kb: Keymap(kb, layout()).remap({name: action}, layer))
        except ValueError as e:
            QMessageBox.warning(self, "Remap", str(e))
            return
        self.keymaps.pop(layer, None)
        self.refresh_mapping()

    def reset_key(self):
        from .widgets import layout
        k = layout().key(self.view.selected) if self.view.selected else None
        if not k:
            return
        from ..core import FACTORY_BACKUP
        backup_file = FACTORY_BACKUP if FACTORY_BACKUP.exists() else None
        if backup_file is None:
            toast(self, "No factory backup found; set the action manually.")
            return
        from ..keymap import BASE, FN, Keymap
        layer = FN if self.layer.currentIndex() else BASE
        raw = bytes.fromhex(json.loads(backup_file.read_text())["keymap_fn" if layer else "keymap_base"])
        value = int.from_bytes(raw[k.led * 4: k.led * 4 + 4], "big")
        run_device(self, lambda kb: Keymap(kb, layout()).remap({k.name: value}, layer))
        self.keymaps.pop(layer, None)
        self.refresh_mapping()


# ----------------------------------------------------------------------------- Hardware
class HardwarePage(QWidget):
    def __init__(self, core):
        super().__init__()
        self.core = core
        from ..lighting import MODES
        self.modes = MODES
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 20, 24, 20)
        v.addWidget(header("Hardware lighting", "Modes stored on the keyboard itself: they keep working "
                                                "without this app, even on another PC."))
        form = QWidget()
        f = QVBoxLayout(form)
        f.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        row.addWidget(QLabel("Mode"))
        self.mode = QComboBox()
        for m in MODES:
            self.mode.addItem(m.name.replace("_", " ").title(), m.name)
        row.addWidget(self.mode, 1)
        f.addLayout(row)
        self.bright = 4
        self.speed = 2
        f.addWidget(slider_row("Brightness", 0, 4, 4, lambda x: setattr(self, "bright", x), 0))
        f.addWidget(slider_row("Speed", 0, 4, 2, lambda x: setattr(self, "speed", x), 0))
        crow = QHBoxLayout()
        crow.addWidget(QLabel("Colour"))
        self.color = ColorButton("#8b5cf6")
        crow.addWidget(self.color)
        self.multi = ToggleSwitch("Multicolour")
        self.multi.setChecked(True)
        crow.addWidget(self.multi)
        crow.addStretch()
        f.addLayout(crow)
        apply = QPushButton("Apply to keyboard")
        apply.setObjectName("primary")
        apply.clicked.connect(self.apply)
        f.addWidget(apply)
        self.state = muted("")
        f.addWidget(self.state)
        v.addWidget(card(h2("Stored mode"), form))

        bk = QHBoxLayout()
        for text, fn in (("Back up keyboard...", self.backup), ("Restore backup...", self.restore),
                         ("Read current state", self.refresh)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            bk.addWidget(b)
        bk.addStretch()
        box = QWidget()
        box.setLayout(bk)
        v.addWidget(card(h2("Backup"), muted("Saves lighting, palette, per-key colours and both key-map layers."), box))
        v.addStretch()

    def apply(self):
        from ..lighting import Lighting, find_mode
        m = find_mode(self.mode.currentData())
        self.core.set_effect(None)   # live effects would hide the stored mode
        color = hex_to_rgb(self.color.color) if (m.color and not self.multi.isChecked()) else None
        run_device(self, lambda kb: Lighting(kb).apply(mode=m.name, brightness=self.bright,
                                                       speed=self.speed if m.speed else None,
                                                       color=color,
                                                       multicolor=self.multi.isChecked() and m.color))
        self.refresh()

    def refresh(self):
        from ..lighting import Lighting
        st = run_device(self, lambda kb: Lighting(kb).state())
        if st:
            self.state.setText("On the keyboard now: " + ", ".join(f"{k} {v}" for k, v in st.items()))

    def backup(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save backup", "hive65-backup.json", "JSON (*.json)")
        if path:
            from ..cli import cmd_backup
            run_device(self, lambda kb: cmd_backup(type("A", (), {"file": path}), kb))

    def restore(self):
        path, _ = QFileDialog.getOpenFileName(self, "Restore backup", "", "JSON (*.json)")
        if path:
            from ..cli import cmd_restore
            self.core.set_effect(None)
            run_device(self, lambda kb: cmd_restore(type("A", (), {"file": path}), kb))


# ----------------------------------------------------------------------------- Notifications
class NotificationsPage(QWidget):
    def __init__(self, core):
        super().__init__()
        self.core = core
        n = core.settings["notifications"]
        host = QWidget()
        v = QVBoxLayout(host)
        v.setContentsMargins(24, 20, 24, 20)
        v.addWidget(header("Notifications", "Animations that play over any effect when something happens "
                                            "on your PC."))
        rows = QWidget()
        g = QGridLayout(rows)
        g.setContentsMargins(0, 0, 0, 0)
        items = [("volume", "Volume changes", "volume", 0.65),
                 ("brightness", "Screen brightness", "brightness", 0.4),
                 ("apps", "App notifications (Discord, WhatsApp, ...)", "app", None),
                 ("media", "Track changes (Spotify, browser, ...)", "media", None),
                 ("system", "Caps Lock && battery low", "caps", True)]
        for i, (key, label, kind, val) in enumerate(items):
            cb = ToggleSwitch(label)
            cb.setChecked(n.get(key, True))
            cb.toggled.connect(lambda on, k=key: self.toggle(k, on))
            test = QPushButton("Preview")
            test.clicked.connect(lambda _=False, k=kind, vv=val: self.core.notify(k, vv, app="Discord",
                                                                                 color="#5865f2"))
            g.addWidget(cb, i, 0)
            g.addWidget(test, i, 1)
        v.addWidget(card(h2("Sources"), rows))

        self.status = muted("")
        v.addWidget(card(h2("Status"), self.status))
        QTimer(self, timeout=self.update_status, interval=2000).start()
        self.update_status()

        table = QTableWidget(0, 2)
        table.setHorizontalHeaderLabels(["App name contains", "Colour"])
        table.horizontalHeader().setStretchLastSection(True)
        table.verticalHeader().setVisible(False)
        for app, color in n["app_colors"].items():
            r = table.rowCount()
            table.insertRow(r)
            table.setItem(r, 0, QTableWidgetItem(app))
            table.setItem(r, 1, QTableWidgetItem(color))
        table.setColumnWidth(0, 240)
        table.itemChanged.connect(lambda _: self.save_colors(table))
        add = QPushButton("Add app")
        add.clicked.connect(lambda: (table.insertRow(table.rowCount()),
                                     table.setItem(table.rowCount() - 1, 0, QTableWidgetItem("app")),
                                     table.setItem(table.rowCount() - 1, 1, QTableWidgetItem("#ffffff"))))
        table.setMinimumHeight(240)
        v.addWidget(card(h2("App colours"), muted("Each app's notification ring uses its colour."), table, add))

        q = n.get("quiet_hours") or ["23:00", "07:00"]
        quiet = QWidget()
        qh = QHBoxLayout(quiet)
        qh.setContentsMargins(0, 0, 0, 0)
        self.quiet_on = ToggleSwitch("Quiet hours from")
        self.quiet_on.setChecked(bool(n.get("quiet_hours")))
        self.q1, self.q2 = QTimeEdit(QTime.fromString(q[0], "HH:mm")), QTimeEdit(QTime.fromString(q[1], "HH:mm"))
        for w in (self.quiet_on, self.q1, QLabel("to"), self.q2):
            qh.addWidget(w)
        qh.addStretch()
        for w in (self.quiet_on,):
            w.toggled.connect(lambda _: self.save_quiet())
        self.q1.timeChanged.connect(lambda _: self.save_quiet())
        self.q2.timeChanged.connect(lambda _: self.save_quiet())
        v.addWidget(card(h2("Quiet hours"), quiet))
        v.addStretch()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll(host))

    def toggle(self, key, on):
        self.core.settings["notifications"][key] = on
        self.core.save()

    def save_colors(self, table):
        colors = {}
        for r in range(table.rowCount()):
            a, c = table.item(r, 0), table.item(r, 1)
            if a and c and a.text().strip():
                colors[a.text().strip().lower()] = c.text().strip()
        self.core.settings["notifications"]["app_colors"] = colors
        self.core.save()

    def save_quiet(self):
        self.core.settings["notifications"]["quiet_hours"] = (
            [self.q1.time().toString("HH:mm"), self.q2.time().toString("HH:mm")]
            if self.quiet_on.isChecked() else None)
        self.core.save()

    def update_status(self):
        names = {s.name: s for s in self.core.events.sources}
        lines = []
        for n in ("volume", "brightness", "system", "apps", "media", "wallpaper"):
            s = names.get(n)
            if not s:
                continue
            lines.append(f"{n}: {'⚠ ' + s.error if s.error else 'listening'}")
        self.status.setText("\n".join(lines) or "No sources running.")


# ----------------------------------------------------------------------------- Ambient
class AmbientPage(QWidget):
    def __init__(self, core, effects_page):
        super().__init__()
        self.core = core
        self.effects_page = effects_page
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 20, 24, 20)
        v.addWidget(header("Ambient & movie mode", "Match the keyboard to your wallpaper, or let it copy the "
                                                  "colours of the video or game on screen."))
        wp = QWidget()
        wv = QVBoxLayout(wp)
        wv.setContentsMargins(0, 0, 0, 0)
        self.wall = ToggleSwitch("Follow my wallpaper's colours")
        self.wall.setChecked(core.settings["ambient"].get("wallpaper", False))
        self.wall.toggled.connect(core.set_wallpaper_sync)
        wv.addWidget(self.wall)
        wv.addWidget(muted("Effects that use the palette (wallpaper flow/aurora, palette pulse, plasma ring) take "
                           "these colours. Windows reads the desktop wallpaper; Hyprland uses swww, hyprpaper "
                           "or pywal."))
        self.swatches = QHBoxLayout()
        wv.addLayout(self.swatches)
        b = QHBoxLayout()
        for name in ("wallpaper_flow", "wallpaper_aurora", "palette_pulse", "plasma_ring"):
            btn = QPushButton(name.replace("_", " ").title())
            btn.clicked.connect(lambda _=False, n=name: self.play(n))
            b.addWidget(btn)
        b.addStretch()
        wv.addLayout(b)
        v.addWidget(card(h2("Wallpaper sync"), wp))

        mv = QWidget()
        mvl = QVBoxLayout(mv)
        mvl.setContentsMargins(0, 0, 0, 0)
        mvl.addWidget(muted("Captures the screen at low resolution and paints it onto the keys. "
                            "'Fit' maps the whole picture, 'Edges' works like an Ambilight, 'Average' "
                            "fills the board with the scene's colour. Choose 'Window' to follow only the "
                            "focused player window. DRM-protected video (Netflix in a browser) may show "
                            "black: turn off hardware acceleration in the browser if that happens."))
        go = QPushButton("Start movie mode")
        go.setObjectName("primary")
        go.clicked.connect(lambda: self.play("movie"))
        mvl.addWidget(go)
        v.addWidget(card(h2("Movie mode"), mv))
        v.addStretch()
        QTimer(self, timeout=self.refresh_swatches, interval=1500).start()

    def play(self, name):
        self.effects_page.apply(name)

    def refresh_swatches(self):
        while self.swatches.count():
            w = self.swatches.takeAt(0).widget()
            if w:
                w.deleteLater()
        for c in self.core.engine.ctx.palette:
            self.swatches.addWidget(swatch(c))
        self.swatches.addStretch()


# ----------------------------------------------------------------------------- Tuning
class TuningPage(QWidget):
    def __init__(self, core, effects_page):
        super().__init__()
        self.core = core
        t = core.settings["tuning"]
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 20, 24, 20)
        v.addWidget(header("Display tuning", "Make colours read clearly on your keycaps. Turn on the test "
                                            "pattern and adjust while looking at the keyboard."))
        pattern = QPushButton("Show test pattern")
        pattern.setObjectName("primary")
        pattern.clicked.connect(lambda: effects_page.apply("calibrate"))
        sliders = QWidget()
        sv = QVBoxLayout(sliders)
        sv.setContentsMargins(0, 0, 0, 0)
        sv.addWidget(slider_row("Gamma", 0.6, 2.6, t["gamma"], lambda x: core.set_tuning(gamma=x)))
        sv.addWidget(slider_row("Colour boost", 0.8, 2.0, t["saturation"], lambda x: core.set_tuning(saturation=x)))
        sv.addWidget(slider_row("Dim-key floor", 0.0, 0.4, t["floor"], lambda x: core.set_tuning(floor=x)))
        white = list(t["white"])
        for i, name in enumerate(("Red balance", "Green balance", "Blue balance")):
            sv.addWidget(slider_row(name, 0.4, 1.0, white[i],
                                    lambda x, i=i: (white.__setitem__(i, x), core.set_tuning(white=list(white)))))
        pop = ToggleSwitch("Pop: snap near-black to black")
        pop.setChecked(t.get("pop", True))
        pop.toggled.connect(lambda on: core.set_tuning(pop=on))
        sv.addWidget(pop)
        v.addWidget(card(pattern, sliders))
        v.addWidget(muted("Gamma below 2.2 keeps mid-tones visible. Lower blue balance if whites look "
                          "bluish. A floor stops dim parts of effects from vanishing."))
        v.addStretch()


# ----------------------------------------------------------------------------- Settings
class SettingsPage(QWidget):
    def __init__(self, core):
        super().__init__()
        from . import autostart
        self.core = core
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 20, 24, 20)
        v.addWidget(header("Settings"))
        box = QWidget()
        b = QVBoxLayout(box)
        b.setContentsMargins(0, 0, 0, 0)
        auto = ToggleSwitch("Start Hive65 Studio when I log in")
        auto.setChecked(autostart.is_enabled())
        auto.toggled.connect(autostart.set_enabled)
        b.addWidget(auto)
        mini = ToggleSwitch("Start minimised to the tray")
        mini.setChecked(core.settings.get("start_minimized", False))
        mini.toggled.connect(lambda on: (core.settings.__setitem__("start_minimized", on), core.save()))
        b.addWidget(mini)
        b.addWidget(slider_row("Frame rate (fps)", 15, 80, core.settings.get("fps", 60), self.set_fps, 0))
        b.addWidget(muted("Frame-rate changes apply after restarting the app."))
        v.addWidget(card(h2("App"), box))

        fx = QWidget()
        f = QVBoxLayout(fx)
        f.setContentsMargins(0, 0, 0, 0)
        f.addWidget(muted(f"Drop your own effect files (*.py) here; they appear in the gallery after a restart:\n"
                          f"{user_effects_dir()}"))
        open_btn = QPushButton("Open effects folder")
        open_btn.clicked.connect(self.open_folder)
        f.addWidget(open_btn)
        v.addWidget(card(h2("Your own effects"), fx))
        rs = QWidget()
        r = QVBoxLayout(rs)
        r.setContentsMargins(0, 0, 0, 0)
        r.addWidget(muted("Puts effects, brightness, speed, notifications, display tuning and ambient "
                          "settings back to their defaults. Your own effect files are kept."))
        self.reset_keyboard = ToggleSwitch("Also restore the keyboard")
        r.addWidget(self.reset_keyboard)
        r.addWidget(muted("Puts the keyboard's lighting, per-key colours and key map back to how they "
                          "were when Studio first ran."))
        reset_btn = QPushButton("Reset all settings...")
        reset_btn.setStyleSheet("QPushButton { border-color: #ef4444; color: #fca5a5; }"
                                "QPushButton:hover { background: #3b1219; }")
        reset_btn.clicked.connect(self.reset_all)
        r.addWidget(reset_btn)
        v.addWidget(card(h2("Reset"), rs))
        v.addWidget(card(h2("About"), muted("Hive65 Studio — open-source driver for the Kreo Hive 65 "
                                            "(SinoWealth 258a:010c). Command line: hive65 --help")))
        v.addStretch()

    def set_fps(self, v):
        self.core.settings["fps"] = int(v)
        self.core.save()

    def reset_all(self):
        kb = self.reset_keyboard.isChecked()
        text = "Reset all Hive65 Studio settings to their defaults?"
        if kb:
            text += "\n\nThe keyboard's lighting, per-key colours and key map will also be restored."
        if QMessageBox.question(self, "Reset all settings", text) != QMessageBox.Yes:
            return
        try:
            done = self.core.reset_settings(restore_keyboard=kb)
        except Exception as e:
            QMessageBox.warning(self, "Reset", f"Settings were reset, but the keyboard restore failed:\n{e}")
            done = "App settings reset to defaults."
        QMessageBox.information(self, "Reset", done + "\n\nHive65 Studio will now restart.")
        restart_app()

    def open_folder(self):
        import subprocess
        import sys
        d = user_effects_dir()
        d.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            import os
            os.startfile(d)
        else:
            subprocess.Popen(["xdg-open", str(d)])


def restart_app():
    """Relaunch Studio (so every page shows the fresh settings) and quit this instance."""
    import sys

    from PySide6.QtCore import QProcess
    from PySide6.QtWidgets import QApplication
    import os
    if os.environ.get("APPIMAGE"):
        QProcess.startDetached(os.environ["APPIMAGE"], [])
    elif getattr(sys, "frozen", False):
        QProcess.startDetached(sys.executable, [])
    else:
        QProcess.startDetached(sys.executable, ["-m", "hive65.studio.app"])
    QApplication.quit()
