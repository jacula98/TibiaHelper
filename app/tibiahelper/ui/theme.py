"""Wygląd aplikacji: ciemny motyw w jednym miejscu (Qt Style Sheets, podobne do CSS).

Widżety dostają objectName (np. "title", "muted") albo właściwość "state",
a kolory i odstępy są tylko tutaj. Dzięki temu zmiana wyglądu nie wymaga
grzebania w kodzie stron.
"""

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPalette
from PySide6.QtWidgets import QApplication, QPushButton

ASSETS_DIR = Path(__file__).resolve().parent / "assets"

BACKGROUND = "#17181c"
SURFACE = "#22242a"
SURFACE_HOVER = "#2b2e35"
BORDER = "#33363f"
TEXT = "#e8eaed"
MUTED = "#8b9099"
ACCENT = "#e3a83b"  # złoty, jak złoto w Tibii
WARNING = "#f0a04b"

STYLE = f"""
QWidget {{
    background: {BACKGROUND};
    color: {TEXT};
    font-size: 13px;
}}
QLabel, QCheckBox {{ background: transparent; }}
QLabel#title {{ font-size: 18px; font-weight: 600; }}
QLabel#appName {{ font-size: 20px; font-weight: 600; color: {ACCENT}; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#warning {{ color: {WARNING}; }}
QLabel#sectionTitle {{ color: {MUTED}; font-size: 11px; font-weight: 600; }}

QLineEdit, QSpinBox {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 6px 8px;
}}
QLineEdit:focus, QSpinBox:focus {{ border-color: {ACCENT}; }}
/* Pole tekstowe wewnątrz QSpinBox nie dostaje drugiej ramki ani odstępów. */
QSpinBox QLineEdit {{ border: none; padding: 0; background: transparent; }}
/* Bez strzałek: w ciemnym motywie wyglądały źle, a level i tak się wpisuje (albo kółkiem myszy). */
QSpinBox::up-button, QSpinBox::down-button {{ width: 0; border: none; }}
QSpinBox::up-arrow, QSpinBox::down-arrow {{ width: 0; height: 0; }}

QPushButton, QToolButton {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 6px 12px;
}}
QPushButton:hover, QToolButton:hover {{ background: {SURFACE_HOVER}; }}
QPushButton#primary {{
    background: {ACCENT};
    color: {BACKGROUND};
    border: none;
    font-weight: 600;
}}
QPushButton#menu {{
    text-align: left;
    padding: 14px 16px;
    font-size: 15px;
    border-radius: 12px;
}}
QPushButton#menu:hover {{ border-color: {ACCENT}; }}
QPushButton#menu:disabled {{ color: {MUTED}; background: transparent; }}
QPushButton#submenu {{
    text-align: left;
    padding: 9px 12px;
    font-size: 13px;
    border-radius: 10px;
}}
QPushButton#submenu:hover {{ border-color: {ACCENT}; }}
QToolButton#icon {{ border: none; background: transparent; font-size: 18px; padding: 2px 6px; }}
QToolButton#icon:hover {{ background: {SURFACE_HOVER}; }}

QListWidget {{
    background: transparent;
    border: none;
    outline: none;
}}
QListWidget::item {{
    background: {SURFACE};
    border-radius: 8px;
    padding: 10px;
    margin: 3px 0;
}}
QListWidget::item:hover {{ background: {SURFACE_HOVER}; }}
QListWidget::item:selected {{ background: {SURFACE_HOVER}; color: {TEXT}; }}

QFrame#banner {{
    background: {SURFACE};
    border: 1px solid {ACCENT};
    border-radius: 8px;
}}

/* Karty kroków: wygląd zależy od właściwości "state" (done / current / todo). */
QFrame#step {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}
QFrame#step:hover {{ background: {SURFACE_HOVER}; }}
QFrame#step[state="current"] {{ border: 2px solid {ACCENT}; }}
QFrame#step[state="done"] {{ background: transparent; }}
QFrame#step[state="done"] QLabel {{ color: {MUTED}; }}

/* Kafelki w sekcji „Potwory”: obrazek i podpis, jak lista potworów w poradnikach. */
QFrame#monsterTile {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}
QFrame#monsterTile QLabel {{ font-size: 11px; background: transparent; }}

/* Pinezki kroku (NPC, miejsce) jako kafelki po prawej stronie karty: klik pokazuje mapę. */
QFrame#markerTile {{
    background: {BACKGROUND};
    border: 1px solid {BORDER};
    border-radius: 6px;
}}
QFrame#markerTile:hover {{ border: 1px solid {ACCENT}; }}
QFrame#markerTile QLabel {{ font-size: 10px; background: transparent; border: none; }}

QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border-radius: 5px;
    border: 2px solid {MUTED};
    background: transparent;
}}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}

QScrollArea {{ border: none; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 4px; min-height: 24px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}

QSlider::groove:horizontal {{ height: 4px; background: {BORDER}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: {TEXT};
    width: 14px;
    margin: -6px 0;
    border-radius: 7px;
}}
"""


def apply_theme(app: QApplication) -> None:
    # Fusion wygląda tak samo na każdym systemie, więc style sheet działa przewidywalnie.
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    # Kolor linków (np. „TibiaWiki”) bierze się z palety, nie ze style sheet.
    palette = app.palette()
    palette.setColor(QPalette.ColorRole.Link, QColor(ACCENT))
    # Szara podpowiedź w pustych polach (np. „min lvl.”), wyraźnie inna niż wpisany tekst.
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(MUTED))
    app.setPalette(palette)


def icon(name: str) -> QIcon:
    return QIcon(str(ASSETS_DIR / name))


def report_button() -> QPushButton:
    """Przycisk „Zgłoś błąd” (logo GitHuba), ten sam przy queście i przy potworze."""
    button = QPushButton(" Zgłoś błąd")
    button.setIcon(icon("github.svg"))
    button.setIconSize(QSize(16, 16))
    button.setToolTip("Otwiera zgłoszenie na GitHubie (potrzebne darmowe konto GitHub)")
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button
