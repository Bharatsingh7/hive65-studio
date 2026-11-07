"""No-code Effect Builder with a live preview."""
import re

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox,
                               QVBoxLayout, QWidget)

from ..effects import load_all
from ..effects.builder import DEFAULT_DESIGN, DIRECTIONS, PATTERNS, REACTIONS, make_class
from .pages import card, h2, header, muted
from .scenes_page import labelled
from .widgets import ColorButton, HeroKeyboard, slider_row, toast

PRESETS = {
    "Sunset wave": {"pattern": "wave", "colors": ["#ff5e00", "#ff0066", "#6a00ff"], "direction": "right"},
    "Ice radar": {"pattern": "radial", "colors": ["#00e5ff", "#0044ff", "#ffffff"], "direction": "out",
                  "reaction": "bass"},
    "Toxic rain": {"pattern": "rain", "colors": ["#39ff14", "#00ff99"], "reaction": "beat"},
    "Candy noise": {"pattern": "noise", "colors": ["#ff71ce", "#01cdfe", "#b967ff", "#fffb96"]},
    "Typing stars": {"pattern": "sparkle", "colors": ["#ffffff", "#ffd166"], "reaction": "typing"},
}


class BuilderPage(QWidget):
    def __init__(self, core, main):
        super().__init__()
        self.core, self.main = core, main
        self.preview_fx = None
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 20, 24, 20)
        v.setSpacing(16)
        v.addWidget(header("Effect Builder", "Design your own effect without code. Saved designs appear "
                                             "in the Effects gallery under Custom."))
        self.view = HeroKeyboard(labels=False, reflection=False)
        self.view.setMinimumHeight(180)
        self.view.override = {}
        pre = QHBoxLayout()
        pre.addWidget(QLabel("Start from:"))
        for name in PRESETS:
            b = QPushButton(name, objectName="chip")
            b.clicked.connect(lambda _=False, n=name: self.load(dict(DEFAULT_DESIGN, **PRESETS[n],
                                                                     name=self._slug(n))))
            pre.addWidget(b)
        pre.addStretch()
        pw = QWidget()
        pw.setLayout(pre)
        v.addWidget(card(self.view, pw))

        form = QWidget()
        f = QVBoxLayout(form)
        f.setContentsMargins(0, 0, 0, 0)
        self.saved = QComboBox()
        self.saved.currentIndexChanged.connect(self._load_saved)
        f.addWidget(labelled("Your designs", self.saved))
        self.name = QLineEdit()
        self.name.setPlaceholderText("name (letters, numbers, _)")
        f.addWidget(labelled("Name", self.name))
        self.pattern = QComboBox()
        self.pattern.addItems(PATTERNS)
        f.addWidget(labelled("Pattern", self.pattern))
        crow = QWidget()
        ch = QHBoxLayout(crow)
        ch.setContentsMargins(0, 0, 0, 0)
        self.count = QSpinBox()
        self.count.setRange(1, 4)
        ch.addWidget(self.count)
        self.color_btns = [ColorButton("#ffffff") for _ in range(4)]
        for b in self.color_btns:
            b.colorChanged.connect(lambda _c: self.rebuild())
            ch.addWidget(b)
        ch.addStretch()
        f.addWidget(labelled("Colours", crow))
        self.direction = QComboBox()
        self.direction.addItems(DIRECTIONS)
        f.addWidget(labelled("Direction", self.direction))
        self.reaction = QComboBox()
        self.reaction.addItems(REACTIONS)
        f.addWidget(labelled("Reacts to", self.reaction))
        self.speed = slider_row("Speed", 0.1, 4.0, 1.0, lambda _v: self.rebuild())
        self.scale = slider_row("Scale", 0.3, 3.0, 1.0, lambda _v: self.rebuild())
        f.addWidget(self.speed)
        f.addWidget(self.scale)
        for w in (self.pattern, self.direction, self.reaction):
            w.currentIndexChanged.connect(lambda _i: self.rebuild())
        self.count.valueChanged.connect(lambda _n: self.rebuild())
        btns = QHBoxLayout()
        play = QPushButton("Save && play on keyboard", objectName="primary")
        play.clicked.connect(lambda: self.save(play=True))
        save = QPushButton("Save")
        save.clicked.connect(lambda: self.save(play=False))
        delete = QPushButton("Delete", objectName="danger")
        delete.clicked.connect(self.delete)
        new = QPushButton("New")
        new.clicked.connect(lambda: self.load(dict(DEFAULT_DESIGN, name=self._unique("my_effect"))))
        for b in (play, save, new, delete):
            btns.addWidget(b)
        btns.addStretch()
        bw = QWidget()
        bw.setLayout(btns)
        v.addWidget(card(h2("Design"), form, muted("The preview runs on simulated music and typing."), bw))
        v.addStretch()

        self._loading = False
        self._refresh_saved()
        designs = core.settings.get("builder", [])
        self.load(dict(designs[0]) if designs else dict(DEFAULT_DESIGN, name=self._unique("my_effect")))
        self._timer = QTimer(self, interval=40, timeout=self._tick)
        self._timer.start()

    # ------------------------------------------------------------------ design <-> form
    @staticmethod
    def _slug(text):
        return re.sub(r"[^a-z0-9_]+", "_", text.lower()).strip("_") or "my_effect"

    def _unique(self, base):
        reg = load_all()
        name, i = base, 2
        while name in reg and reg[name].category != "custom" or any(
                d["name"] == name for d in self.core.settings.get("builder", [])):
            name, i = f"{base}_{i}", i + 1
        return name

    def design(self):
        n = self.count.value()
        return {"name": self._slug(self.name.text()), "pattern": self.pattern.currentText(),
                "colors": [b.color for b in self.color_btns[:n]],
                "speed": round(self._slider(self.speed, 0.1, 4.0), 2),
                "scale": round(self._slider(self.scale, 0.3, 3.0), 2),
                "direction": self.direction.currentText(), "reaction": self.reaction.currentText()}

    @staticmethod
    def _slider(row, lo, hi):
        return lo + (hi - lo) * row.slider.value() / 1000

    @staticmethod
    def _set_slider(row, lo, hi, value):
        row.slider.setValue(int((float(value) - lo) / (hi - lo) * 1000))

    def load(self, d):
        self._loading = True
        d = dict(DEFAULT_DESIGN, **d)
        self.name.setText(d["name"])
        self.pattern.setCurrentText(d["pattern"])
        cols = list(d["colors"])[:4] or ["#ffffff"]
        self.count.setValue(len(cols))
        for i, b in enumerate(self.color_btns):
            b.set_color(cols[i] if i < len(cols) else "#ffffff")
        self.direction.setCurrentText(d["direction"])
        self.reaction.setCurrentText(d["reaction"])
        self._set_slider(self.speed, 0.1, 4.0, d["speed"])
        self._set_slider(self.scale, 0.3, 3.0, d["scale"])
        self._loading = False
        self.rebuild()

    def rebuild(self):
        if self._loading:
            return
        for i, b in enumerate(self.color_btns):
            b.setVisible(i < self.count.value())
        from .thumbs import LivePreview
        if self.preview_fx is not None:
            self.preview_fx.close()
        try:
            self.preview_fx = LivePreview(make_class(self.design()), self.core.engine.ctx.palette)
        except Exception as e:
            self.preview_fx = None
            toast(self, f"Preview failed: {e}")

    def _tick(self):
        if not self.isVisible() or self.preview_fx is None:
            return
        try:
            self.view.override = self.preview_fx.step(0.04)
        except Exception:
            self.preview_fx = None

    # ------------------------------------------------------------------ saved designs
    def _refresh_saved(self, select=None):
        self.saved.blockSignals(True)
        self.saved.clear()
        self.saved.addItem("—", None)
        for d in self.core.settings.get("builder", []):
            self.saved.addItem(d["name"], d["name"])
        self.saved.setCurrentIndex(max(0, self.saved.findData(select)))
        self.saved.blockSignals(False)

    def _load_saved(self):
        name = self.saved.currentData()
        for d in self.core.settings.get("builder", []):
            if d["name"] == name:
                self.load(dict(d))

    def save(self, play):
        d = self.design()
        reg = load_all()
        if d["name"] in reg and reg[d["name"]].category != "custom":
            toast(self, f"'{d['name']}' is a built-in effect name; pick another.")
            return
        self.name.setText(d["name"])
        self.core.save_design(d)
        self._refresh_saved(d["name"])
        self.main.effects_changed()
        if play:
            self.core.set_effect(d["name"], {})
            self.main.effect_changed()
            toast(self, f"Saved and playing {d['name']}")
        else:
            toast(self, f"Saved {d['name']} (Effects > Custom)")

    def delete(self):
        name = self._slug(self.name.text())
        if not any(d["name"] == name for d in self.core.settings.get("builder", [])):
            toast(self, "This design isn't saved yet.")
            return
        self.core.delete_design(name)
        self._refresh_saved()
        self.main.effects_changed()
        toast(self, f"Deleted {name}")

    def hideEvent(self, e):
        super().hideEvent(e)
        if self.preview_fx is not None:      # keep nothing running while hidden
            self.preview_fx.close()
            self.preview_fx = None

    def showEvent(self, e):
        super().showEvent(e)
        if self.preview_fx is None:
            self.rebuild()
