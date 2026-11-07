"""Automations: rules that switch scenes by app, idle, time, music or fullscreen."""
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QVBoxLayout, QWidget)

from ..automation import TRIGGERS, active_app
from .pages import card, h2, header, muted
from .widgets import ToggleSwitch, clear_layout, toast

TRIGGER_TEXT = {"app": "Focused app is", "idle": "Idle for (minutes)", "time": "Time is between",
                "music": "Music is playing", "fullscreen": "A fullscreen game/video"}
PLACEHOLDER = {"app": "spotify, discord (process or Hyprland class)", "idle": "5",
               "time": "23:00-07:00", "music": "", "fullscreen": ""}


class RuleRow(QFrame):
    def __init__(self, page, i, rule):
        super().__init__()
        self.setObjectName("tile")
        h = QHBoxLayout(self)
        h.setContentsMargins(12, 8, 8, 8)
        h.setSpacing(10)
        self.page, self.i = page, i
        self.on = ToggleSwitch()
        self.on.setChecked(bool(rule.get("enabled", True)))
        self.on.setToolTip("Enable this rule")
        self.trigger = QComboBox()
        for t in TRIGGERS:
            self.trigger.addItem(TRIGGER_TEXT[t], t)
        self.trigger.setCurrentIndex(max(0, self.trigger.findData(rule.get("trigger"))))
        self.value = QLineEdit(str(rule.get("value", "")))
        self.scene = QComboBox()
        for sc in page.core.settings.get("scenes", []):
            self.scene.addItem(sc["name"])
        self.scene.setCurrentText(rule.get("scene", ""))
        up = QPushButton("↑", objectName="icon")
        up.setFixedSize(30, 30)
        up.setToolTip("Higher priority")
        up.clicked.connect(lambda: page.move(i, -1))
        rm = QPushButton("✕", objectName="icon")
        rm.setFixedSize(30, 30)
        rm.setToolTip("Delete rule")
        rm.clicked.connect(lambda: page.remove(i))
        h.addWidget(self.on)
        h.addWidget(self.trigger)
        h.addWidget(self.value, 1)
        h.addWidget(QLabel("→"))
        h.addWidget(self.scene)
        h.addWidget(up)
        h.addWidget(rm)
        self._sync_value()
        self.on.toggled.connect(self.save)
        self.trigger.currentIndexChanged.connect(lambda: (self._sync_value(), self.save()))
        self.value.editingFinished.connect(self.save)
        self.scene.currentIndexChanged.connect(self.save)

    def _sync_value(self):
        t = self.trigger.currentData()
        self.value.setPlaceholderText(PLACEHOLDER[t])
        self.value.setEnabled(t in ("app", "idle", "time"))

    def rule(self):
        return {"enabled": self.on.isChecked(), "trigger": self.trigger.currentData(),
                "value": self.value.text().strip(), "scene": self.scene.currentText()}

    def save(self, *_):
        self.page.update_rule(self.i, self.rule())


class AutomationPage(QWidget):
    def __init__(self, core):
        super().__init__()
        self.core = core
        s = core.settings
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 20, 24, 20)
        v.setSpacing(16)
        v.addWidget(header("Automations", "The keyboard changes scene on its own: music app in front, a "
                                          "game goes fullscreen, you walk away, it gets late. When the "
                                          "trigger ends, your own choice comes back."))
        top = QHBoxLayout()
        self.enabled = ToggleSwitch("Automations on")
        self.enabled.setChecked(s.get("automation_enabled", True))
        self.enabled.toggled.connect(lambda on: self._set("automation_enabled", on))
        self.lock = ToggleSwitch("Turn LEDs off while the screen is locked")
        self.lock.setChecked(s.get("dim_on_lock", True))
        self.lock.toggled.connect(lambda on: self._set("dim_on_lock", on))
        top.addWidget(self.enabled)
        top.addSpacing(24)
        top.addWidget(self.lock)
        top.addStretch()
        tw = QWidget()
        tw.setLayout(top)
        self.status = QLabel(objectName="statusChip")
        self.focus = muted("")
        v.addWidget(card(tw, self.status, self.focus))

        host = QWidget()
        self.rows = QVBoxLayout(host)
        self.rows.setContentsMargins(0, 0, 0, 0)
        self.rows.setSpacing(8)
        add = QHBoxLayout()
        for t in ("app", "idle", "time", "fullscreen", "music"):
            b = QPushButton(f"+ {TRIGGER_TEXT[t].split(' (')[0]}")
            b.clicked.connect(lambda _=False, t=t: self.add(t))
            add.addWidget(b)
        add.addStretch()
        aw = QWidget()
        aw.setLayout(add)
        v.addWidget(card(h2("Rules"), muted("Checked top to bottom every second; the first match wins."),
                         host, aw))
        v.addWidget(card(h2("Hyprland"),
                         muted("App rules read `hyprctl activewindow`. For idle, add to hypridle.conf:\n"
                               "listener { timeout = 300; on-timeout = hive65 idle on; "
                               "on-resume = hive65 idle off }")))
        v.addStretch()
        self.build()
        QTimer(self, timeout=self._tick, interval=1000).start()

    def _set(self, key, value):
        self.core.settings[key] = value
        self.core.save()

    def build(self):
        clear_layout(self.rows)
        for i, r in enumerate(self.core.settings.get("automations", [])):
            self.rows.addWidget(RuleRow(self, i, r))

    def update_rule(self, i, rule):
        rules = self.core.settings["automations"]
        if 0 <= i < len(rules):
            rules[i] = rule
            self.core.save()

    def add(self, trigger):
        scenes = self.core.settings.get("scenes", [])
        if not scenes:
            toast(self, "Save a scene first (Scenes & Mixer page).")
            return
        default = {"app": "", "idle": "5", "time": "23:00-07:00"}.get(trigger, "")
        self.core.settings["automations"].append({"enabled": True, "trigger": trigger,
                                                  "value": default, "scene": scenes[0]["name"]})
        self.core.save()
        self.build()

    def remove(self, i):
        del self.core.settings["automations"][i]
        self.core.save()
        self.build()

    def move(self, i, step):
        rules = self.core.settings["automations"]
        j = i + step
        if 0 <= j < len(rules):
            rules[i], rules[j] = rules[j], rules[i]
            self.core.save()
            self.build()

    def _tick(self):
        if not self.isVisible():
            return
        a = self.core.automation
        st = a.status if a else ""
        self.status.setText(f"Active: {st}" if st else "No rule active: your own scene is showing")
        app = active_app()
        self.focus.setText(f"Focused app right now: {app or 'unknown'} (use this name in an app rule)")

    def showEvent(self, e):
        super().showEvent(e)
        self.build()
