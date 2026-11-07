"""Hive65 Studio look: deep dark background, glass cards, neon accents."""

BG = "#07080d"
PANEL = "rgba(22, 25, 38, 0.72)"
PANEL_SOLID = "#141724"
PANEL_2 = "#1b1f30"
BORDER = "rgba(255, 255, 255, 0.07)"
BORDER_SOLID = "#262b3d"
TEXT = "#eceef6"
MUTED = "#8b91a8"
ACCENT = "#8b5cf6"
ACCENT_2 = "#22d3ee"

CATEGORY_COLORS = {"music": "#ec4899", "typing": "#f59e0b", "display": "#22c55e",
                   "ambient": "#8b5cf6", "screen": "#06b6d4", "custom": "#f43f5e"}

NAV_ICONS = {"Home": "mdi6.home-variant", "Effects": "mdi6.palette", "Scenes & Mixer": "mdi6.layers-triple",
             "Automations": "mdi6.robot", "Effect Builder": "mdi6.creation", "Keyboard": "mdi6.keyboard",
             "Hardware": "mdi6.chip", "Notifications": "mdi6.bell-ring", "Ambient & Movie": "mdi6.movie-open-play",
             "Display tuning": "mdi6.tune-variant", "Settings": "mdi6.cog"}


def icon(name, color=TEXT):
    """qtawesome icon, or an empty icon when qtawesome isn't installed."""
    try:
        import qtawesome as qta
        return qta.icon(name, color=color)
    except Exception:
        from PySide6.QtGui import QIcon
        return QIcon()


QSS = f"""
* {{ font-family: "Inter", "Segoe UI Variable Text", "Segoe UI", "Noto Sans", sans-serif;
     font-size: 13px; color: {TEXT}; }}
QMainWindow, QWidget#root {{ background: {BG}; }}
QWidget#page {{ background: transparent; }}
QWidget#sidebar {{ background: rgba(14, 16, 26, 0.92); border-right: 1px solid {BORDER}; }}
QLabel#brand {{ font-size: 19px; font-weight: 800; padding: 20px 18px 2px 18px; color: white;
               letter-spacing: 0.5px; }}
QLabel#tagline {{ color: {MUTED}; padding: 0 18px 14px 18px; font-size: 11px; }}
QPushButton#nav {{ text-align: left; padding: 7px 14px; border: none; border-radius: 10px;
                  margin: 1px 10px; color: {MUTED}; font-size: 13px; background: transparent; }}
QPushButton#nav:hover {{ background: rgba(255,255,255,0.05); color: {TEXT}; }}
QPushButton#nav:checked {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                           stop:0 rgba(139,92,246,0.95), stop:1 rgba(34,211,238,0.55));
                           color: white; font-weight: 600; }}
QLabel#navSection {{ color: rgba(139,145,168,0.7); font-size: 10px; font-weight: 800; letter-spacing: 1.5px;
                    padding: 10px 24px 3px 24px; }}
QLabel#statusChip {{ background: rgba(255,255,255,0.06); border: 1px solid {BORDER}; border-radius: 11px;
                    padding: 3px 10px; font-size: 11px; color: {TEXT}; }}
QPushButton#star {{ background: transparent; border: none; padding: 0; color: #facc15; font-size: 15px; }}
QPushButton#star:hover {{ background: rgba(250,204,21,0.15); border-radius: 12px; }}
QLabel#h1 {{ font-size: 28px; font-weight: 800; color: white; }}
QLabel#h2 {{ font-size: 15px; font-weight: 700; color: white; }}
QLabel#kicker {{ font-size: 11px; font-weight: 700; color: {ACCENT_2}; letter-spacing: 1.5px; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#big {{ font-size: 22px; font-weight: 800; color: white; }}
QFrame#card {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 16px; }}
QFrame#tile {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 14px; }}
QFrame#tile:hover {{ border: 1px solid rgba(139,92,246,0.8); background: rgba(40, 34, 70, 0.75); }}
QFrame#effectCard {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 16px; }}
QFrame#effectCard:hover {{ border: 1px solid rgba(139,92,246,0.85); background: rgba(34, 30, 58, 0.85); }}
QFrame#effectCard[active="true"] {{ border: 2px solid {ACCENT_2}; background: rgba(12, 44, 56, 0.85); }}
QFrame#nowPlaying {{ background: rgba(255,255,255,0.04); border: 1px solid {BORDER}; border-radius: 14px;
                    margin: 8px 10px; }}
QPushButton {{ background: rgba(255,255,255,0.05); border: 1px solid {BORDER}; border-radius: 10px;
              padding: 8px 14px; }}
QPushButton:hover {{ border-color: rgba(139,92,246,0.8); background: rgba(139,92,246,0.12); }}
QPushButton:pressed {{ background: rgba(139,92,246,0.25); }}
QPushButton#primary {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {ACCENT}, stop:1 {ACCENT_2});
                      border: none; color: white; font-weight: 700; }}
QPushButton#primary:hover {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #9d74ff, stop:1 #4be0f5); }}
QPushButton#danger {{ border-color: rgba(239,68,68,0.6); color: #fca5a5; }}
QPushButton#danger:hover {{ background: rgba(239,68,68,0.15); }}
QPushButton#icon {{ padding: 6px; border-radius: 9px; }}
QPushButton#chip {{ border-radius: 15px; padding: 6px 15px; color: {MUTED}; }}
QPushButton#chip:checked {{ background: {ACCENT}; color: white; border-color: {ACCENT}; }}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTimeEdit {{ background: rgba(255,255,255,0.05);
             border: 1px solid {BORDER}; border-radius: 10px; padding: 7px 11px; }}
QLineEdit:focus, QComboBox:focus {{ border-color: {ACCENT}; }}
QComboBox QAbstractItemView {{ background: {PANEL_SOLID}; selection-background-color: {ACCENT};
                              border: 1px solid {BORDER_SOLID}; }}
QSlider::groove:horizontal {{ height: 6px; background: rgba(255,255,255,0.08); border-radius: 3px; }}
QSlider::sub-page:horizontal {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                               stop:0 {ACCENT}, stop:1 {ACCENT_2}); border-radius: 3px; }}
QSlider::handle:horizontal {{ background: white; width: 16px; margin: -6px 0; border-radius: 8px;
                             border: 3px solid {ACCENT}; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 9px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: rgba(255,255,255,0.12); border-radius: 4px; min-height: 30px; }}
QScrollBar:horizontal {{ background: transparent; height: 9px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: rgba(255,255,255,0.12); border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QTableWidget, QListWidget {{ background: rgba(255,255,255,0.03); border: 1px solid {BORDER};
                            border-radius: 12px; gridline-color: {BORDER}; }}
QListWidget::item {{ padding: 8px; border-radius: 8px; }}
QListWidget::item:selected {{ background: rgba(139,92,246,0.35); }}
QHeaderView {{ background: transparent; border: none; }}
QHeaderView::section {{ background: rgba(255,255,255,0.04); border: none; padding: 6px; color: {MUTED}; }}
QTableCornerButton::section {{ background: transparent; border: none; }}
QToolTip {{ background: {PANEL_SOLID}; border: 1px solid {BORDER_SOLID}; padding: 6px; border-radius: 6px; }}
QMenu {{ background: {PANEL_SOLID}; border: 1px solid {BORDER_SOLID}; padding: 6px; border-radius: 10px; }}
QMenu::item {{ padding: 7px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: {ACCENT}; }}
QDialog {{ background: {PANEL_SOLID}; }}
QLabel#toast {{ background: rgba(20, 22, 34, 0.96); border: 1px solid rgba(139,92,246,0.7);
               border-radius: 12px; padding: 10px 16px; color: white; }}
"""
