"""Ctrl+K command palette: fuzzy-run any effect, scene, page or action."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout

from ..effects import load_all
from . import theme


def score(query, text):
    """Subsequence match score (higher is better), None when it doesn't match."""
    q, t = query.lower(), text.lower()
    if not q:
        return 0
    if q in t:
        return 100 - t.index(q) - len(t) * 0.1
    pos, total, last = 0, 0, -2
    for ch in q:
        i = t.find(ch, pos)
        if i < 0:
            return None
        total += 5 if i == last + 1 else 1
        last, pos = i, i + 1
    return total - len(t) * 0.1


class CommandPalette(QDialog):
    def __init__(self, main):
        super().__init__(main, Qt.FramelessWindowHint | Qt.Dialog)
        self.main, self.core = main, main.core
        self.setObjectName("palette")
        self.setModal(True)
        self.setStyleSheet(f"QDialog#palette {{ background: {theme.PANEL_SOLID}; border: 1px solid "
                           f"rgba(139,92,246,0.7); border-radius: 16px; }}")
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 14, 14, 10)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("Type an effect, scene, page or action…")
        self.edit.setStyleSheet("font-size: 16px; padding: 10px 14px;")
        self.list = QListWidget()
        self.list.setStyleSheet("background: transparent; border: none;")
        hint = QLabel("↑↓ to choose · Enter to run · Esc to close")
        hint.setObjectName("muted")
        v.addWidget(self.edit)
        v.addWidget(self.list, 1)
        v.addWidget(hint)
        self.commands = self._commands()
        self.edit.textChanged.connect(self.refresh)
        self.edit.returnPressed.connect(self.run)
        self.list.itemActivated.connect(lambda _it: self.run())
        self.resize(560, 420)
        self.refresh("")

    def _commands(self):
        core, main = self.core, self.main
        cmds = []
        for n, cls in sorted(load_all().items()):
            cmds.append((f"{n.replace('_', ' ').title()}", f"effect · {cls.category}",
                         lambda n=n: (core.set_effect(n), main.effect_changed())))
            if cls.category != "screen":
                cmds.append((f"Layer: {n.replace('_', ' ')}", "mixer layer over the current effect",
                             lambda n=n: core.set_layer(n, None, core.engine.layer_blend,
                                                        core.engine.layer_opacity)))
        for sc in core.settings.get("scenes", []):
            cmds.append((f"Scene: {sc['name']}", "scene",
                         lambda n=sc["name"]: (core.apply_scene(n), main.effect_changed())))
        for title in main.page_titles:
            cmds.append((f"Go to {title}", "page", lambda t=title: main.go_to(t)))
        cmds += [
            ("Stop live effect", "action · keyboard's own lighting",
             lambda: (core.set_effect(None), main.effect_changed())),
            ("Pause / resume", "action", core.toggle_pause),
            ("Next favourite", "action", lambda: (core.next_favorite(1), main.effect_changed())),
            ("Random favourite", "action", lambda: (core.next_favorite(shuffle=True), main.effect_changed())),
            ("Remove mixer layer", "action", lambda: core.set_layer(None)),
            ("Save current as scene", "action", lambda: main.go_to("Scenes & Mixer")),
        ]
        for pct in (100, 75, 50, 25, 10):
            cmds.append((f"Brightness {pct}%", "action", lambda p=pct: core.set_brightness(p / 100)))
        for t in ("volume", "app", "media", "flash", "done"):
            cmds.append((f"Test notification: {t}", "action",
                         lambda t=t: core.notify(t, 0.7 if t == "volume" else ("Hive65" if t == "app" else None))))
        return cmds

    def refresh(self, text):
        self.list.clear()
        ranked = []
        for title, kind, fn in self.commands:
            s = score(text, title)
            if s is not None:
                ranked.append((s, title, kind, fn))
        ranked.sort(key=lambda r: -r[0])
        for s, title, kind, fn in ranked[:60]:
            it = QListWidgetItem(f"{title}     {kind}")
            it.setData(Qt.UserRole, fn)
            self.list.addItem(it)
        if self.list.count():
            self.list.setCurrentRow(0)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Down, Qt.Key_Up) and self.list.count():
            step = 1 if e.key() == Qt.Key_Down else -1
            self.list.setCurrentRow((self.list.currentRow() + step) % self.list.count())
            return
        super().keyPressEvent(e)

    def run(self):
        it = self.list.currentItem()
        if it is None:
            return
        fn = it.data(Qt.UserRole)
        self.accept()
        try:
            fn()
        except Exception as e:
            from .widgets import toast
            toast(self.main, f"Couldn't run that: {e}")

    def showEvent(self, e):
        super().showEvent(e)
        g = self.main.geometry()
        self.move(g.x() + (g.width() - self.width()) // 2, g.y() + int(g.height() * 0.14))
        self.edit.setFocus()
