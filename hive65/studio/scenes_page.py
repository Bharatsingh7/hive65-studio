"""Scenes, the two-effect mixer, key highlights and the playlist."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QVBoxLayout, QWidget)

from ..effects import load_all
from ..engine import BLENDS
from ..scenes import HIGHLIGHT_SETS
from . import theme
from .pages import card, h2, header, muted
from .widgets import FlowLayout, ToggleSwitch, clear_layout, slider_row, toast

BLEND_HELP = {"screen": "brightens, never clips: the usual choice",
              "add": "adds light: strong, punchy",
              "max": "brightest of the two per key",
              "multiply": "the layer masks the base (dark parts cut it out)",
              "mix": "plain cross-mix by opacity"}


def labelled(text, widget):
    row = QWidget()
    h = QHBoxLayout(row)
    h.setContentsMargins(0, 0, 0, 0)
    lab = QLabel(text)
    lab.setMinimumWidth(130)
    h.addWidget(lab)
    h.addWidget(widget, 1)
    return row


class SceneCard(QFrame):
    def __init__(self, page, scene, active):
        super().__init__()
        self.setObjectName("tile")
        self.setFixedSize(220, 128)
        reg = load_all()
        eff = scene.get("effect")
        cat = reg[eff].category if eff in reg else "ambient"
        self.accent = theme.CATEGORY_COLORS.get(cat, theme.ACCENT)
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 12, 12, 10)
        v.setSpacing(3)
        top = QHBoxLayout()
        name = QLabel(("● " if active else "") + scene["name"])
        name.setStyleSheet(f"font-weight: 800; font-size: 15px; color: {'white' if not active else self.accent};")
        top.addWidget(name)
        top.addStretch()
        rm = QPushButton("✕", objectName="icon")
        rm.setFixedSize(26, 26)
        rm.setToolTip("Delete this scene")
        rm.clicked.connect(lambda: page.delete(scene["name"]))
        top.addWidget(rm)
        v.addLayout(top)
        parts = [(eff or "own lighting").replace("_", " ")]
        if scene.get("layer"):
            parts.append(f"+ {scene['layer'].replace('_', ' ')} ({scene.get('blend', 'screen')})")
        if scene.get("highlights", "none") != "none":
            parts.append(f"{scene['highlights']} keys")
        d = muted("  ".join(parts))
        d.setStyleSheet("font-size: 11px;")
        v.addWidget(d)
        b = int(round(float(scene.get("brightness", 1.0)) * 100))
        v.addWidget(muted(f"brightness {b}%"))
        v.addStretch()
        go = QPushButton("Apply", objectName="primary")
        go.clicked.connect(lambda: page.apply(scene["name"]))
        v.addWidget(go)

    def paintEvent(self, e):
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QColor, QPainter
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(self.accent))
        p.drawRoundedRect(QRectF(1.5, 18, 3, self.height() - 36), 1.5, 1.5)


class ScenesPage(QWidget):
    def __init__(self, core, main):
        super().__init__()
        self.core, self.main = core, main
        self.reg = load_all()
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 20, 24, 20)
        v.setSpacing(16)
        v.addWidget(header("Scenes & Mixer", "Save everything the keyboard is doing as a scene, layer a "
                                              "second effect on top, and keep important keys lit."))

        # --- scenes
        save_row = QHBoxLayout()
        self.name = QLineEdit()
        self.name.setPlaceholderText("Name for a new scene, e.g. Late night coding")
        self.name.returnPressed.connect(self.save)
        save = QPushButton("Save current as scene", objectName="primary")
        save.clicked.connect(self.save)
        save_row.addWidget(self.name, 1)
        save_row.addWidget(save)
        sr = QWidget()
        sr.setLayout(save_row)
        host = QWidget()
        self.flow = FlowLayout(host, spacing=12)
        v.addWidget(card(h2("Scenes"), muted("Switch from Home, the tray, Ctrl+K, automations or "
                                             "`hive65 scene NAME` (e.g. a Hyprland bind)."), sr, host))

        # --- mixer
        mix = QWidget()
        mv = QVBoxLayout(mix)
        mv.setContentsMargins(0, 0, 0, 0)
        self.layer = QComboBox()
        self.layer.addItem("No layer", None)
        for n in sorted(self.reg):
            if self.reg[n].category != "screen":
                self.layer.addItem(f"{n.replace('_', ' ').title()}  ·  {self.reg[n].category}", n)
        self.blend = QComboBox()
        for b in BLENDS:
            self.blend.addItem(f"{b}  –  {BLEND_HELP.get(b, '')}", b)
        mv.addWidget(labelled("Layer effect", self.layer))
        mv.addWidget(labelled("Blend", self.blend))
        self.opacity = slider_row("Opacity", 0.05, 1.0, core.engine.layer_opacity, self._opacity)
        mv.addWidget(self.opacity)
        ideas = QHBoxLayout()
        ideas.addWidget(QLabel("Try:"))
        for base, layer, blend, op in (("aurora", "spectrum", "screen", 0.7),
                                       ("starfield", "typing_fire", "add", 0.9),
                                       ("lava_flow", "bass_pulse", "screen", 0.6),
                                       ("nebula", "rain_window", "max", 0.8)):
            if base in self.reg and layer in self.reg:
                b = QPushButton(f"{base.replace('_', ' ')} + {layer.replace('_', ' ')}", objectName="chip")
                b.clicked.connect(lambda _=False, a=base, l=layer, bl=blend, o=op: self.combo(a, l, bl, o))
                ideas.addWidget(b)
        ideas.addStretch()
        iw = QWidget()
        iw.setLayout(ideas)
        mv.addWidget(iw)
        self.layer.currentIndexChanged.connect(self._layer_changed)
        self.blend.currentIndexChanged.connect(self._layer_changed)
        v.addWidget(card(h2("Mixer: two effects at once"),
                         muted("The layer is drawn over the base effect from the Effects page. Pair a "
                               "calm ambient base with a music or typing layer."), mix))

        # --- highlights
        hl = QWidget()
        hv = QHBoxLayout(hl)
        hv.setContentsMargins(0, 0, 0, 0)
        self.highlight = QComboBox()
        names = list(HIGHLIGHT_SETS) + [n for n in core.settings.get("custom_highlights", {})
                                        if n not in HIGHLIGHT_SETS]
        for n in names:
            self.highlight.addItem(n.title(), n)
        self.highlight.currentIndexChanged.connect(
            lambda: core.set_highlight_set(self.highlight.currentData()))
        hv.addWidget(labelled("Highlight set", self.highlight), 1)
        v.addWidget(card(h2("Key highlights"),
                         muted("Keys that stay lit over any effect: Gaming lights WASD, Space, Shift and "
                               "the ability keys; Editor lights the Ctrl shortcuts; Media the arrows."), hl))

        # --- playlist
        p = core.settings["playlist"]
        pl = QWidget()
        pv = QVBoxLayout(pl)
        pv.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.pl_on = ToggleSwitch("Cycle through favourites")
        self.pl_shuffle = ToggleSwitch("Shuffle")
        self.pl_drops = ToggleSwitch("Also switch on big music drops")
        for t, k in ((self.pl_on, "enabled"), (self.pl_shuffle, "shuffle"), (self.pl_drops, "on_drops")):
            t.setChecked(bool(p.get(k)))
            t.toggled.connect(lambda on, k=k: self._playlist(k, on))
            row.addWidget(t)
        row.addStretch()
        rw = QWidget()
        rw.setLayout(row)
        pv.addWidget(rw)
        pv.addWidget(slider_row("Every (minutes)", 1, 30, p.get("minutes", 5),
                                lambda m: self._playlist("minutes", m), 0))
        v.addWidget(card(h2("Playlist"), muted("Hands-free variety: favourites rotate with a smooth "
                                               "cross-fade. Paused while an automation is active."), pl))
        v.addStretch()
        self.sync()
        self.refresh()

    # ------------------------------------------------------------------ scenes
    def refresh(self):
        clear_layout(self.flow)
        active = self.core.settings.get("active_scene")
        for sc in self.core.settings.get("scenes", []):
            self.flow.addWidget(SceneCard(self, sc, sc["name"] == active))

    def save(self):
        name = self.name.text().strip()
        if not name:
            toast(self, "Type a name for the scene first.")
            return
        self.core.save_scene(name)
        self.name.clear()
        self.refresh()
        toast(self, f"Saved scene {name}")

    def apply(self, name):
        try:
            self.core.apply_scene(name)
        except Exception as e:
            toast(self, f"Couldn't apply {name}: {e}")
            return
        self.sync()
        self.refresh()
        self.main.effect_changed()
        toast(self, f"Scene: {name}")

    def delete(self, name):
        self.core.delete_scene(name)
        self.refresh()
        toast(self, f"Deleted scene {name}")

    # ------------------------------------------------------------------ mixer etc.
    def sync(self):
        """Show the engine's current layer/highlights (after a scene or automation)."""
        e = self.core.engine
        for combo, value in ((self.layer, e.layer_name), (self.blend, e.layer_blend),
                             (self.highlight, self.core.settings.get("highlight_set", "none"))):
            combo.blockSignals(True)
            i = combo.findData(value)
            combo.setCurrentIndex(max(0, i))
            combo.blockSignals(False)
        s = self.opacity.slider
        s.blockSignals(True)
        s.setValue(int((e.layer_opacity - 0.05) / 0.95 * 1000))
        s.blockSignals(False)

    def _layer_changed(self):
        try:
            self.core.set_layer(self.layer.currentData(), None, self.blend.currentData(),
                                self.core.engine.layer_opacity)
        except Exception as e:
            toast(self, f"Couldn't start that layer: {e}")

    def _opacity(self, v):
        e = self.core.engine
        e.layer_opacity = float(v)
        self.core.settings["layer"]["opacity"] = float(v)
        self.core.save()

    def combo(self, base, layer, blend, opacity):
        self.core.set_effect(base)
        self.core.set_layer(layer, None, blend, opacity)
        self.sync()
        self.main.effect_changed()
        toast(self, f"{base.replace('_', ' ')} with a {layer.replace('_', ' ')} layer")

    def _playlist(self, key, value):
        self.core.settings["playlist"][key] = value
        self.core.save()

    def showEvent(self, e):
        super().showEvent(e)
        self.sync()
        self.refresh()
