"""Reusable Studio widgets: keyboard views, effect cards, toggles, toasts, layouts."""
import math
import time

import numpy as np
from PySide6.QtCore import (Property, QEasingCurve, QPoint, QPointF, QPropertyAnimation, QRect,
                            QRectF, QSize, Qt, QTimer, Signal)
from PySide6.QtGui import (QBrush, QColor, QFont, QLinearGradient, QPainter, QPen, QPixmap,
                           QRadialGradient)
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QFrame, QGraphicsOpacityEffect,
                               QHBoxLayout, QLabel, QLayout, QLineEdit, QPushButton, QSlider,
                               QVBoxLayout, QWidget)

from ..canvas import parse_color
from ..layout import Layout
from . import theme

_LAYOUT = None


def layout():
    global _LAYOUT
    if _LAYOUT is None:
        _LAYOUT = Layout()
    return _LAYOUT


def to_qcolor(rgb, boost=True):
    rgb = np.clip(np.asarray(rgb, dtype=float), 0, 1)
    if boost:  # screens are much dimmer than LEDs look; lift for the preview
        rgb = rgb ** 0.6
    return QColor(int(rgb[0] * 255), int(rgb[1] * 255), int(rgb[2] * 255))


def paint_keyboard(p, rect, colors, selected=None, labels=True, radius=0.16):
    """Draw the Hive 65 with per-LED colours inside rect (QRectF)."""
    lay = layout()
    kw = rect.width() / (lay.width + 0.2)
    kh = rect.height() / (lay.height + 0.2)
    unit = min(kw, kh)
    ox = rect.x() + (rect.width() - unit * (lay.width + 0.2)) / 2 + unit * 0.1
    oy = rect.y() + (rect.height() - unit * (lay.height + 0.2)) / 2 + unit * 0.1
    p.setRenderHint(QPainter.Antialiasing)
    body = QRectF(ox - unit * 0.12, oy - unit * 0.12, unit * (lay.width + 0.04), unit * (lay.height + 0.04))
    p.setPen(QPen(QColor(theme.BORDER_SOLID), 1))
    p.setBrush(QColor("#0a0b10"))
    p.drawRoundedRect(body, unit * 0.25, unit * 0.25)
    font = QFont(p.font())
    font.setPixelSize(max(7, int(unit * 0.22)))
    p.setFont(font)
    rects = {}
    for k in lay.keys:
        r = QRectF(ox + (k.x - k.w / 2) * unit + unit * 0.05, oy + k.row * unit + unit * 0.05,
                   k.w * unit - unit * 0.1, unit * 0.9)
        rects[k.name] = r
        rgb = colors.get(k.led) if colors else None
        lit = rgb is not None and float(np.max(rgb)) > 0.01
        c = to_qcolor(rgb) if lit else QColor("#1a1d27")
        if lit:  # glow
            g = QColor(c)
            g.setAlpha(70)
            p.setPen(Qt.NoPen)
            p.setBrush(g)
            p.drawRoundedRect(r.adjusted(-unit * 0.08, -unit * 0.08, unit * 0.08, unit * 0.08),
                              unit * radius * 1.5, unit * radius * 1.5)
        grad = QLinearGradient(r.topLeft(), r.bottomLeft())
        grad.setColorAt(0, c.lighter(115))
        grad.setColorAt(1, c.darker(125))
        p.setBrush(QBrush(grad))
        p.setPen(QPen(QColor("white") if selected == k.name else QColor("#2b3042"),
                      2 if selected == k.name else 1))
        p.drawRoundedRect(r, unit * radius, unit * radius)
        if labels and unit > 26:
            lum = c.red() * 0.3 + c.green() * 0.59 + c.blue() * 0.11
            p.setPen(QColor("#0b0b0b") if lum > 150 else QColor("#c9cde0"))
            max_chars = int(k.w * 5)
            p.drawText(r, Qt.AlignCenter, k.name if len(k.name) <= max_chars else k.name[:max_chars])
    return rects


class KeyboardView(QWidget):
    """Live mirror of the LEDs; clicking a key emits keyClicked(name)."""

    keyClicked = Signal(str)

    def __init__(self, parent=None, labels=True):
        super().__init__(parent)
        self.colors = {}
        self.override = None     # dict led->rgb shown instead of live colours (painter)
        self.selected = None
        self.labels = labels
        self._rects = {}
        self.setMinimumHeight(120)
        self._timer = QTimer(self, timeout=self.update, interval=33)
        self._timer.start()

    def set_live(self, colors):
        self.colors = colors or {}

    def paintEvent(self, e):
        p = QPainter(self)
        self._rects = paint_keyboard(p, QRectF(self.rect()).adjusted(6, 6, -6, -6),
                                     self.override if self.override is not None else self.colors,
                                     self.selected, self.labels)

    def mousePressEvent(self, e):
        for name, r in self._rects.items():
            if r.contains(e.position()):
                self.selected = name
                self.keyClicked.emit(name)
                break


class ColorButton(QPushButton):
    colorChanged = Signal(str)

    def __init__(self, color="#ffffff", allow_rainbow=False):
        super().__init__()
        self.allow_rainbow = allow_rainbow
        self.setFixedSize(70, 30)
        self.set_color(color)
        self.clicked.connect(self.pick)

    def set_color(self, color):
        self.color = color
        if color == "rainbow":
            style = ("background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #f00, stop:0.33 #0f0,"
                     " stop:0.66 #00f, stop:1 #f0f);")
        else:
            style = f"background: {color};"
        self.setStyleSheet(style + "border-radius: 8px; border: 1px solid #333;")

    def pick(self):
        start = QColor(self.color if self.color != "rainbow" else "#ff0080")
        c = QColorDialog.getColor(start, self, "Pick a colour")
        if c.isValid():
            self.set_color(c.name())
            self.colorChanged.emit(c.name())


def slider_row(label, lo, hi, value, on_change, decimals=2):
    """Label + slider + value text. on_change(float)."""
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 0, 0, 0)
    lab = QLabel(label)
    lab.setMinimumWidth(130)
    s = QSlider(Qt.Horizontal)
    s.setRange(0, 1000)
    val = QLabel()
    val.setMinimumWidth(48)
    val.setObjectName("muted")

    def to_val(pos):
        return lo + (hi - lo) * pos / 1000

    def changed(pos):
        v = to_val(pos)
        val.setText(f"{v:.{decimals}f}" if decimals else f"{int(round(v))}")
        on_change(v if decimals else int(round(v)))

    s.setValue(int((float(value) - lo) / (hi - lo) * 1000) if hi > lo else 0)
    val.setText(f"{float(value):.{decimals}f}" if decimals else f"{int(value)}")
    s.valueChanged.connect(changed)
    h.addWidget(lab)
    h.addWidget(s, 1)
    h.addWidget(val)
    w.slider = s
    return w


class ParamPanel(QWidget):
    """Auto-built controls for an effect's declared params."""

    changed = Signal(str, object)

    def __init__(self):
        super().__init__()
        self.v = QVBoxLayout(self)
        self.v.setContentsMargins(0, 0, 0, 0)
        self.v.setSpacing(10)

    def clear(self):
        while self.v.count():
            item = self.v.takeAt(0)
            if item.widget():
                item.widget().hide()          # deleteLater is deferred; hide now
                item.widget().deleteLater()

    def build(self, cls, values):
        self.clear()
        if not cls.params:
            lab = QLabel("This effect has no settings.")
            lab.setObjectName("muted")
            self.v.addWidget(lab)
            return
        for name, spec in cls.params.items():
            cur = values.get(name, spec["default"])
            label = spec.get("label") or name.replace("_", " ").title()
            kind = spec["kind"]
            emit = lambda v, n=name: self.changed.emit(n, v)
            if kind in ("float", "int"):
                self.v.addWidget(slider_row(label, spec["min"], spec["max"], float(cur), emit,
                                            0 if kind == "int" else 2))
            elif kind == "color":
                row = QWidget()
                h = QHBoxLayout(row)
                h.setContentsMargins(0, 0, 0, 0)
                lab = QLabel(label)
                lab.setMinimumWidth(130)
                btn = ColorButton(str(cur), allow_rainbow=True)
                btn.colorChanged.connect(emit)
                h.addWidget(lab)
                h.addWidget(btn)
                if spec["default"] == "rainbow":
                    rb = QPushButton("Rainbow")
                    rb.clicked.connect(lambda _=False, b=btn, e=emit: (b.set_color("rainbow"), e("rainbow")))
                    h.addWidget(rb)
                h.addStretch()
                self.v.addWidget(row)
            elif kind == "bool":
                cb = ToggleSwitch(label)
                cb.setChecked(str(cur).lower() in ("1", "true", "yes", "on"))
                cb.toggled.connect(emit)
                self.v.addWidget(cb)
            elif kind == "choice":
                row = QWidget()
                h = QHBoxLayout(row)
                h.setContentsMargins(0, 0, 0, 0)
                lab = QLabel(label)
                lab.setMinimumWidth(130)
                combo = QComboBox()
                combo.addItems(spec["choices"])
                combo.setCurrentText(str(cur))
                combo.currentTextChanged.connect(emit)
                h.addWidget(lab)
                h.addWidget(combo, 1)
                self.v.addWidget(row)
            else:
                row = QWidget()
                h = QHBoxLayout(row)
                h.setContentsMargins(0, 0, 0, 0)
                lab = QLabel(label)
                lab.setMinimumWidth(130)
                edit = QLineEdit(str(cur))
                edit.editingFinished.connect(lambda e=edit, f=emit: f(e.text()))
                h.addWidget(lab)
                h.addWidget(edit, 1)
                self.v.addWidget(row)
        self.v.addStretch()


class EffectCard(QFrame):
    """Gallery card: thumbnail (animates while hovered), name, category edge, favourite star."""

    clicked = Signal(str)
    favToggled = Signal(str)
    _hovered = None          # only one card animates at a time

    def __init__(self, name, cls, favorite=False, palette=None):
        super().__init__()
        self.name, self.cls = name, cls
        self.palette = palette
        self.cat_color = QColor(theme.CATEGORY_COLORS.get(cls.category, theme.ACCENT))
        self.setObjectName("effectCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(212, 156)
        v = QVBoxLayout(self)
        v.setContentsMargins(12, 10, 10, 10)
        v.setSpacing(4)
        self.thumb = QLabel()
        self.thumb.setFixedHeight(66)
        self.thumb.setAlignment(Qt.AlignCenter)
        v.addWidget(self.thumb)
        top = QHBoxLayout()
        top.setSpacing(4)
        title = QLabel(name.replace("_", " ").title())
        title.setStyleSheet("font-weight: 700; color: white;")
        cat = QLabel(cls.category.upper())
        cat.setStyleSheet(f"color: {self.cat_color.name()}; font-size: 9px; font-weight: 800;"
                          " letter-spacing: 1px;")
        self.star = QPushButton(objectName="star")
        self.star.setFixedSize(24, 24)
        self.star.setCursor(Qt.PointingHandCursor)
        self.star.setToolTip("Favourite (shows on Home, in the tray and with Ctrl+Alt+arrows)")
        self.star.clicked.connect(lambda: self.favToggled.emit(self.name))
        top.addWidget(title)
        top.addStretch()
        top.addWidget(cat)
        top.addWidget(self.star)
        v.addLayout(top)
        desc = QLabel(cls.description)
        desc.setWordWrap(True)
        desc.setObjectName("muted")
        desc.setStyleSheet("font-size: 11px;")
        v.addWidget(desc, 1)
        self.setToolTip(cls.description)
        self._static = None
        self._preview = None
        self._timer = QTimer(self, interval=66, timeout=self._tick)
        self.set_favorite(favorite)

    def set_favorite(self, on):
        self.favorite = on
        ic = theme.icon("mdi6.star" if on else "mdi6.star-outline", "#facc15" if on else theme.MUTED)
        if ic.isNull():
            self.star.setText("★" if on else "☆")
        else:
            self.star.setIcon(ic)

    def set_thumbnail(self, pixmap):
        self._static = pixmap
        if self._preview is None:
            self.thumb.setPixmap(pixmap)

    def set_active(self, on):
        self.setProperty("active", "true" if on else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    # hover: play the effect inside the card on simulated music and typing
    def enterEvent(self, e):
        super().enterEvent(e)
        if EffectCard._hovered is not None and EffectCard._hovered is not self:
            EffectCard._hovered._stop_preview()
        EffectCard._hovered = self
        self._timer.start()

    def leaveEvent(self, e):
        super().leaveEvent(e)
        self._stop_preview()

    def hideEvent(self, e):
        super().hideEvent(e)
        self._stop_preview()

    def _stop_preview(self):
        self._timer.stop()
        if self._preview is not None:
            self._preview.close()
            self._preview = None
        if EffectCard._hovered is self:
            EffectCard._hovered = None
        if self._static is not None:
            self.thumb.setPixmap(self._static)

    def _tick(self):
        try:
            if self._preview is None:
                from .thumbs import LivePreview
                self._preview = LivePreview(self.cls, self.palette)
                for _ in range(8):      # warm up so the first frame isn't empty
                    self._preview.step()
            self.thumb.setPixmap(keyboard_pixmap(self._preview.step()))
        except Exception:
            self._timer.stop()

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(self.cat_color)
        p.drawRoundedRect(QRectF(1.5, 18, 3, self.height() - 36), 1.5, 1.5)

    def mousePressEvent(self, e):
        self.clicked.emit(self.name)


def keyboard_pixmap(colors, w=190, h=64):
    pm = QPixmap(w, h)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    paint_keyboard(p, QRectF(0, 0, w, h), colors, labels=False, radius=0.2)
    p.end()
    return pm


def swatch(color_rgb, size=26):
    lab = QLabel()
    lab.setFixedSize(size, size)
    c = to_qcolor(color_rgb, boost=False)
    lab.setStyleSheet(f"background: {c.name()}; border-radius: {size // 4}px; border: 1px solid #333;")
    return lab


def hex_to_rgb(text):
    return tuple(int(round(v * 255)) for v in parse_color(text))


# ----------------------------------------------------------------------------- v0.3 widgets
class ToggleSwitch(QCheckBox):
    """A checkbox drawn as a switch with a sliding knob."""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)
        self._pos = 0.0
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self.toggled.connect(self._animate)

    def _get(self):
        return self._pos

    def _set(self, v):
        self._pos = v
        self.update()

    knob = Property(float, _get, _set)

    def _animate(self, on):
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def _label(self):
        return self.text().replace("&&", "&")    # drawn by hand, so no mnemonic escaping

    def sizeHint(self):
        fm = self.fontMetrics()
        text = fm.horizontalAdvance(self._label()) + 14 if self.text() else 0
        return QSize(44 + text, max(26, fm.height() + 8))

    def minimumSizeHint(self):
        return self.sizeHint()

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        running = self._anim.state() == QPropertyAnimation.Running
        pos = self._pos if running else (1.0 if self.isChecked() else 0.0)
        track = QRectF(1, (self.height() - 22) / 2, 40, 22)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 30))
        p.drawRoundedRect(track, 11, 11)
        if pos > 0:
            g = QLinearGradient(track.topLeft(), track.topRight())
            a, b = QColor(theme.ACCENT), QColor(theme.ACCENT_2)
            a.setAlphaF(pos)
            b.setAlphaF(pos)
            g.setColorAt(0, a)
            g.setColorAt(1, b)
            p.setBrush(g)
            p.drawRoundedRect(track, 11, 11)
        knob = QRectF(track.x() + 3 + pos * 18, track.y() + 3, 16, 16)
        p.setBrush(QColor("white") if self.isEnabled() else QColor("#555"))
        p.drawEllipse(knob)
        if self.text():
            p.setPen(QColor(theme.TEXT) if self.isEnabled() else QColor(theme.MUTED))
            p.drawText(QRectF(52, 0, self.width() - 52, self.height()), Qt.AlignVCenter, self._label())


def toast(widget, text, ms=2600):
    """Small non-blocking message at the bottom right of widget's window."""
    win = widget.window()
    lab = QLabel(text, win)
    lab.setObjectName("toast")
    lab.setWordWrap(True)
    lab.setMaximumWidth(420)
    lab.adjustSize()
    live = [t for t in getattr(win, "_toasts", []) if _alive(t)]
    y = win.height() - 24 - sum(t.height() + 8 for t in live) - lab.height()
    lab.move(win.width() - lab.width() - 24, max(8, y))
    eff = QGraphicsOpacityEffect(lab)
    lab.setGraphicsEffect(eff)
    anim = QPropertyAnimation(eff, b"opacity", lab)
    anim.setDuration(180)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    lab.show()
    lab.raise_()
    anim.start()
    win._toasts = live + [lab]

    def fade():
        out = QPropertyAnimation(eff, b"opacity", lab)
        out.setDuration(350)
        out.setStartValue(1.0)
        out.setEndValue(0.0)
        out.finished.connect(lab.hide)
        out.finished.connect(lab.deleteLater)
        out.start()
    QTimer.singleShot(ms, lab, fade)
    return lab


def _alive(w):
    try:
        return w.isVisible()
    except RuntimeError:      # already deleted
        return False


class HeroKeyboard(KeyboardView):
    """The live keyboard drawn big: per-key bloom glow and an optional floor reflection."""

    def __init__(self, parent=None, labels=True, reflection=True):
        super().__init__(parent, labels)
        self.reflection = reflection
        self._pm = None
        self.setMinimumHeight(150)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        full = QRectF(self.rect()).adjusted(8, 8, -8, -8)
        kb = QRectF(full.x(), full.y(), full.width(), full.height() * (0.8 if self.reflection else 1.0))
        if kb.width() < 20 or kb.height() < 20:
            return
        colors = self.override if self.override is not None else self.colors
        lay = layout()
        unit = min(kb.width() / (lay.width + 0.2), kb.height() / (lay.height + 0.2))
        ox = kb.x() + (kb.width() - unit * (lay.width + 0.2)) / 2 + unit * 0.1
        oy = kb.y() + (kb.height() - unit * (lay.height + 0.2)) / 2 + unit * 0.1
        # bloom: soft light thrown around each lit key
        p.setPen(Qt.NoPen)
        for k in lay.keys:
            rgb = colors.get(k.led) if colors else None
            if rgb is None or float(np.max(rgb)) < 0.05:
                continue
            c = to_qcolor(rgb)
            cx, cy = ox + k.x * unit, oy + (k.row + 0.5) * unit
            rad = unit * (1.1 + 0.25 * k.w)
            g = QRadialGradient(QPointF(cx, cy), rad)
            c0 = QColor(c)
            c0.setAlpha(int(90 * float(np.max(rgb)) ** 0.5))
            c1 = QColor(c)
            c1.setAlpha(0)
            g.setColorAt(0, c0)
            g.setColorAt(1, c1)
            p.setBrush(g)
            p.drawEllipse(QPointF(cx, cy), rad, rad)
        # the keyboard itself, drawn into a pixmap so the reflection can reuse it
        dpr = self.devicePixelRatioF()
        size = QSize(int(kb.width() * dpr), int(kb.height() * dpr))
        if self._pm is None or self._pm.size() != size:
            self._pm = QPixmap(size)
            self._pm.setDevicePixelRatio(dpr)
        self._pm.fill(Qt.transparent)
        q = QPainter(self._pm)
        rects = paint_keyboard(q, QRectF(0, 0, kb.width(), kb.height()), colors, self.selected, self.labels)
        q.end()
        self._rects = {n: r.translated(kb.x(), kb.y()) for n, r in rects.items()}
        p.drawPixmap(kb.topLeft(), self._pm)
        if self.reflection:
            body_bottom = oy + unit * (lay.height + 0.04) - unit * 0.12
            refl_h = full.bottom() - body_bottom
            if refl_h > 4:
                p.save()
                p.setClipRect(QRectF(full.x(), body_bottom, full.width(), refl_h))
                p.setOpacity(0.2)
                p.translate(0, 2 * body_bottom)
                p.scale(1, -1)
                p.drawPixmap(kb.topLeft(), self._pm)
                p.restore()
                fade = QLinearGradient(0, body_bottom, 0, full.bottom())
                fade.setColorAt(0, QColor(13, 15, 24, 40))
                fade.setColorAt(1, QColor(13, 15, 24, 255))
                p.fillRect(QRectF(full.x() - 8, body_bottom, full.width() + 16, refl_h + 9), fade)


def zone_colors(colors, zones=3):
    """Average live colour of the left/middle/right of the keyboard (RGB arrays)."""
    lay = layout()
    out = []
    for z in range(zones):
        lo, hi = lay.width * z / zones, lay.width * (z + 1) / zones
        vals = [colors[k.led] for k in lay.keys if lo <= k.x < hi and k.led in colors]
        out.append(np.mean(vals, axis=0) if vals else np.zeros(3))
    return out


class AuroraHeader(QFrame):
    """Hero panel whose background is a slow aurora tinted by what the keyboard shows."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("hero")
        self._rgb = [np.array(c) for c in ((0.55, 0.36, 0.96), (0.13, 0.83, 0.93), (0.93, 0.28, 0.6))]
        self._target = list(self._rgb)
        self._t0 = time.perf_counter()
        self._timer = QTimer(self, interval=40, timeout=self._tick)
        self._timer.start()

    def set_live(self, colors):
        if not colors:
            return
        for i, z in enumerate(zone_colors(colors)):
            m = float(np.max(z))
            if m > 0.04:     # keep the old tint while a zone is dark
                self._target[i] = np.clip(z / m, 0, 1)

    def _tick(self):
        if not self.isVisible():
            return
        for i in range(3):
            self._rgb[i] = self._rgb[i] * 0.94 + self._target[i] * 0.06
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor(255, 255, 255, 22), 1))
        p.setBrush(QColor(13, 15, 24))
        p.drawRoundedRect(r, 20, 20)
        t = time.perf_counter() - self._t0
        w, h = r.width(), r.height()
        p.setPen(Qt.NoPen)
        for i, rgb in enumerate(self._rgb):
            cx = w * (0.2 + 0.3 * i) + math.sin(t * 0.21 + i * 2.1) * w * 0.12
            cy = h * (0.22 + 0.12 * math.sin(t * 0.17 + i * 1.3))
            rad = max(w, h) * (0.42 + 0.06 * math.sin(t * 0.3 + i))
            c = to_qcolor(rgb, boost=False)
            c0, c1 = QColor(c), QColor(c)
            c0.setAlpha(70)
            c1.setAlpha(0)
            g = QRadialGradient(QPointF(cx, cy), rad)
            g.setColorAt(0, c0)
            g.setColorAt(1, c1)
            p.setBrush(g)
            p.drawEllipse(QPointF(cx, cy), rad, rad * 0.55)


class FlowLayout(QLayout):
    """Lays children left to right and wraps; reflows in setGeometry (no reparenting)."""

    def __init__(self, parent=None, spacing=12):
        super().__init__(parent)
        self._items = []
        self._space = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientations(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        s = QSize()
        for it in self._items:
            s = s.expandedTo(it.minimumSize())
        return s

    def _do(self, rect, test):
        x, y, line = rect.x(), rect.y(), 0
        for it in self._items:
            w = it.widget()
            if w is not None and w.isHidden():
                continue
            hint = it.sizeHint()
            if x + hint.width() > rect.right() + 1 and line > 0:
                x, y, line = rect.x(), y + line + self._space, 0
            if not test:
                it.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self._space
            line = max(line, hint.height())
        return y + line - rect.y()


def clear_layout(lay):
    """Remove and delete every widget in a layout (never call during a resize)."""
    while lay.count():
        it = lay.takeAt(0)
        w = it.widget()
        if w is not None:
            w.hide()
            w.deleteLater()


class Tile(QFrame):
    """Clickable glass tile: optional keyboard thumbnail, title and subtitle."""

    clicked = Signal()

    def __init__(self, title, subtitle="", pixmap=None, accent=None, size=(176, 118)):
        super().__init__()
        self.setObjectName("tile")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(*size)
        self.accent = QColor(accent) if accent else None
        v = QVBoxLayout(self)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(2)
        self.thumb = QLabel()
        self.thumb.setAlignment(Qt.AlignCenter)
        self.thumb.setFixedHeight(54)
        if pixmap is not None:
            self.thumb.setPixmap(pixmap)
        v.addWidget(self.thumb)
        t = QLabel(title)
        t.setStyleSheet("font-weight: 700; color: white;")
        v.addWidget(t)
        if subtitle:
            s = QLabel(subtitle)
            s.setObjectName("muted")
            s.setStyleSheet("font-size: 11px;")
            v.addWidget(s)
        v.addStretch()

    def set_pixmap(self, pm):
        self.thumb.setPixmap(pm)

    def paintEvent(self, e):
        super().paintEvent(e)
        if self.accent is not None:
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(Qt.NoPen)
            p.setBrush(self.accent)
            p.drawRoundedRect(QRectF(14, self.height() - 5, self.width() - 28, 3), 1.5, 1.5)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit()
