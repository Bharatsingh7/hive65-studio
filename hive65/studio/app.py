"""Hive65 Studio main window and tray icon."""
import sys

from PySide6.QtCore import QSize, QTimer, Qt
from PySide6.QtGui import QColor, QIcon, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow, QMenu,
                               QPushButton, QScrollArea, QStackedWidget, QSystemTrayIcon,
                               QVBoxLayout, QWidget)

from ..core import Core
from . import theme
from .automation_page import AutomationPage
from .builder_page import BuilderPage
from .home import HomePage
from .motion import fade_in
from .pages import (AmbientPage, EffectsPage, HardwarePage, KeyboardPage, NotificationsPage,
                    SettingsPage, TuningPage)
from .scenes_page import ScenesPage
from .widgets import KeyboardView


def app_icon():
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    cols = ["#ec4899", "#8b5cf6", "#06b6d4", "#22c55e"]
    for i, c in enumerate(cols):
        p.setBrush(QColor(c))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(4 + (i % 2) * 30, 4 + (i // 2) * 30, 26, 26, 7, 7)
    p.end()
    return QIcon(pm)


NAV_SECTIONS = (("PLAY", ("Home", "Effects", "Scenes & Mixer", "Automations", "Effect Builder")),
                ("DEVICE", ("Keyboard", "Hardware")),
                ("SYSTEM", ("Notifications", "Ambient & Movie", "Display tuning", "Settings")))


def _icon_btn(name, tip, fn):
    b = QPushButton(objectName="icon")
    ic = theme.icon(name)
    if ic.isNull():
        b.setText(tip[:1])
    else:
        b.setIcon(ic)
        b.setIconSize(QSize(18, 18))
    b.setFixedSize(32, 32)
    b.setToolTip(tip)
    b.clicked.connect(fn)
    return b


class MainWindow(QMainWindow):
    def __init__(self, core):
        super().__init__()
        self.core = core
        self.setWindowTitle("Hive65 Studio")
        self.setWindowIcon(app_icon())
        self.setMinimumSize(760, 480)
        self._placed = False
        root = QWidget(objectName="root")
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        side = QWidget(objectName="sidebar")
        side.setFixedWidth(206)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(0, 0, 0, 8)
        sv.setSpacing(0)
        sv.addWidget(QLabel("Hive65 Studio", objectName="brand"))
        sv.addWidget(QLabel("Kreo Hive 65 · open driver", objectName="tagline"))
        search = QPushButton("  Search…        Ctrl+K", objectName="nav")
        search.setIcon(theme.icon("mdi6.magnify", theme.MUTED))
        search.clicked.connect(self.open_palette)
        sv.addWidget(search)

        self.stack = QStackedWidget()
        self.effects = EffectsPage(core)
        self.home = HomePage(core, self)
        self.scenes = ScenesPage(core, self)
        pages = {"Home": self.home, "Effects": self.effects, "Scenes & Mixer": self.scenes,
                 "Automations": AutomationPage(core), "Effect Builder": BuilderPage(core, self),
                 "Keyboard": KeyboardPage(core), "Hardware": HardwarePage(core),
                 "Notifications": NotificationsPage(core),
                 "Ambient & Movie": AmbientPage(core, self.effects),
                 "Display tuning": TuningPage(core, self.effects), "Settings": SettingsPage(core)}
        self.page_titles = []
        self.nav = []
        nav_host = QWidget()
        nav_l = QVBoxLayout(nav_host)
        nav_l.setContentsMargins(0, 0, 0, 0)
        nav_l.setSpacing(0)
        nav_area = QScrollArea()          # short windows: the nav scrolls, the cards stay put
        nav_area.setWidgetResizable(True)
        nav_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        nav_area.setWidget(nav_host)
        sv.addWidget(nav_area, 1)
        for section, titles in NAV_SECTIONS:
            sec = QLabel(section, objectName="navSection")
            nav_l.addWidget(sec)
            for title in titles:
                i = len(self.page_titles)
                self.page_titles.append(title)
                # Every page scrolls instead of forcing the window bigger than the screen.
                area = QScrollArea()
                area.setWidgetResizable(True)
                area.setWidget(pages[title])
                self.stack.addWidget(area)
                b = QPushButton("  " + title.replace("&", "&&"), objectName="nav")
                b.setIcon(theme.icon(theme.NAV_ICONS.get(title, "mdi6.circle"), theme.MUTED))
                b.setIconSize(QSize(18, 18))
                b.setCheckable(True)
                b.clicked.connect(lambda _=False, i=i: self.go(i))
                nav_l.addWidget(b)
                self.nav.append(b)
        nav_l.addStretch()

        # now-playing mini card
        np_card = QFrame(objectName="nowPlaying")
        nv = QVBoxLayout(np_card)
        nv.setContentsMargins(10, 8, 10, 8)
        nv.setSpacing(4)
        self.mini = KeyboardView(labels=False)
        self.mini.setMinimumHeight(0)
        self.mini.setFixedHeight(52)
        nv.addWidget(self.mini)
        self.np_name = QLabel()
        self.np_name.setStyleSheet("font-weight: 700; color: white;")
        self.status = QLabel(objectName="muted")
        self.status.setStyleSheet("font-size: 11px;")
        self.status.setWordWrap(True)
        row = QHBoxLayout()
        row.setSpacing(4)
        row.addWidget(self.np_name, 1)
        self.np_pause = _icon_btn("mdi6.pause", "Pause / resume (Ctrl+Alt+P)", self._toggle_pause)
        row.addWidget(self.np_pause)
        row.addWidget(_icon_btn("mdi6.skip-next", "Next favourite (Ctrl+Alt+→)",
                                lambda: (core.next_favorite(1), self.effect_changed())))
        nv.addLayout(row)
        nv.addWidget(self.status)
        sv.addWidget(np_card)

        h.addWidget(side)
        h.addWidget(self.stack, 1)
        self.setCentralWidget(root)
        self.go(0, animate=False)
        QShortcut(QKeySequence("Ctrl+K"), self, self.open_palette)
        QShortcut(QKeySequence("Ctrl+F"), self, self.open_palette)

        # live preview + status from the engine thread
        core.engine.listeners.append(self._on_frame)
        self._latest = None
        QTimer(self, timeout=self._push_preview, interval=33).start()
        QTimer(self, timeout=self._update_status, interval=500).start()
        self._last_effect = core.engine.effect_name
        self._update_status()

    def showEvent(self, ev):
        super().showEvent(ev)
        if not self._placed:
            # Fit the screen the window opens on (laptops are often 1536x816 at 125 %).
            self._placed = True
            avail = (self.screen() or QApplication.primaryScreen()).availableGeometry()
            w = min(1400, int(avail.width() * 0.9))
            h = min(880, int(avail.height() * 0.9))
            self.resize(w, h)
            self.move(avail.x() + (avail.width() - w) // 2, avail.y() + (avail.height() - h) // 2)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self.mini.setVisible(self.height() >= 620)

    def go(self, i, animate=True):
        self.stack.setCurrentIndex(i)
        for j, b in enumerate(self.nav):
            b.setChecked(i == j)
            b.setIcon(theme.icon(theme.NAV_ICONS.get(self.page_titles[j], "mdi6.circle"),
                                 "white" if i == j else theme.MUTED))
        if animate:
            fade_in(self.stack.currentWidget())

    def go_to(self, title):
        if title in self.page_titles:
            self.go(self.page_titles.index(title))

    def open_palette(self):
        from .palette_cmd import CommandPalette
        CommandPalette(self).exec()

    # called by pages after they change what is playing
    def effect_changed(self):
        self.effects.select(self.core.engine.effect_name)
        self._last_effect = self.core.engine.effect_name
        self.scenes.sync()
        self._update_status()

    def effects_changed(self):
        self.effects.sync_cards()

    def favorites_changed(self):
        self.effects.refresh_favorites()
        self.home.refresh_shelves()

    def _toggle_pause(self):
        self.core.toggle_pause()
        self._update_status()

    def _on_frame(self, colors):
        self._latest = colors

    def _push_preview(self):
        c = self._latest
        self.effects.preview.set_live(c)
        self.home.set_live(c)
        self.mini.set_live(c)

    def _update_status(self):
        e = self.core.engine
        if e.effect_name != self._last_effect:     # changed by an automation, hotkey or IPC
            self._last_effect = e.effect_name
            self.effects.select(e.effect_name)
        name = e.effect_name.replace("_", " ").title() if e.effect_name else "Own lighting"
        self.np_name.setText(name)
        ic = theme.icon("mdi6.play" if e.paused else "mdi6.pause")
        if not ic.isNull():
            self.np_pause.setIcon(ic)
        if e.last_error:
            text = f"⚠ {e.last_error}"
        elif e.paused:
            text = "Paused: keyboard shows its own mode"
        elif e.effect_name:
            text = f"{e.measured_fps:.0f} fps" + (f" · scene {self.core.settings['active_scene']}"
                                                   if self.core.settings.get("active_scene") else "")
        else:
            text = "No live effect running"
        self.status.setText(text)

    def closeEvent(self, ev):
        # Keep running in the tray; Quit from the tray menu exits.
        ev.ignore()
        self.hide()


class Tray(QSystemTrayIcon):
    def __init__(self, app, window, core):
        super().__init__(app_icon(), app)
        self.app, self.window, self.core = app, window, core
        self.setToolTip("Hive65 Studio")
        self.menu = QMenu()
        self.menu.aboutToShow.connect(self.build)
        self.build()
        self.setContextMenu(self.menu)
        self.activated.connect(lambda reason: self.show_window()
                               if reason == QSystemTrayIcon.Trigger else None)
        self.show()

    def _play(self, name):
        self.core.set_effect(name)
        self.window.effect_changed()

    def _scene(self, name):
        self.core.apply_scene(name)
        self.window.effect_changed()

    def build(self):
        """Rebuilt each time it opens so favourites and scenes are current."""
        core, menu = self.core, self.menu
        menu.clear()
        menu.addAction("Open Hive65 Studio", self.show_window)
        menu.addSeparator()
        favs = menu.addMenu("★ Favourites")
        for n in core.settings.get("favorites", []):
            favs.addAction(n.replace("_", " ").title(), lambda n=n: self._play(n))
        scenes = menu.addMenu("Scenes")
        for sc in core.settings.get("scenes", []):
            scenes.addAction(sc["name"], lambda n=sc["name"]: self._scene(n))
        effects = menu.addMenu("All effects")
        from ..effects import CATEGORIES, load_all
        reg = load_all()
        for cat in CATEGORIES:
            names = sorted(n for n, c in reg.items() if c.category == cat)
            if names:
                sub = effects.addMenu(cat.title())
                for name in names:
                    sub.addAction(name.replace("_", " ").title(), lambda n=name: self._play(n))
        menu.addSeparator()
        menu.addAction("Resume live effects" if core.engine.paused else "Pause live effects",
                       lambda: (core.toggle_pause(), self.window._update_status()))
        menu.addAction("Next favourite", lambda: (core.next_favorite(1), self.window.effect_changed()))
        menu.addAction("Keyboard's own lighting", lambda: self._play(None))
        menu.addSeparator()
        menu.addAction("Quit", self.app.quit)

    def show_window(self):
        self.window.showNormal()
        self.window.raise_()
        self.window.activateWindow()


def _install_crash_log():
    """Write Python errors and native crashes to studio-crash.log in the settings folder."""
    import faulthandler
    import time
    import traceback
    import warnings

    from ..settings import config_dir
    warnings.filterwarnings("ignore", message="data discontinuity in recording")
    path = config_dir() / "studio-crash.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    log = open(path, "a", buffering=1, encoding="utf-8")
    log.write(f"\n=== Hive65 Studio started {time.ctime()} ===\n")
    faulthandler.enable(file=log, all_threads=True)

    def hook(exc_type, exc, tb):
        log.write("".join(traceback.format_exception(exc_type, exc, tb)))

    sys.excepthook = hook
    import threading
    threading.excepthook = lambda a: hook(a.exc_type, a.exc_value, a.exc_traceback)
    return log


def main():
    _crash_log = _install_crash_log()   # keep the file open for faulthandler
    app = QApplication(sys.argv)
    app.setApplicationName("Hive65 Studio")
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(theme.QSS)
    core = Core()
    core.start()
    win = MainWindow(core)
    tray = Tray(app, win, core)
    if "--minimized" not in sys.argv and not core.settings.get("start_minimized"):
        win.show()
    app.aboutToQuit.connect(core.stop)
    rc = app.exec()
    del tray
    sys.exit(rc)


if __name__ == "__main__":
    main()
