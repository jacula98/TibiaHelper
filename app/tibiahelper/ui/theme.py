"""Wygląd aplikacji: motywy kolorystyczne w jednym miejscu (Qt Style Sheets, podobne do CSS).

Widżety dostają objectName (np. "title", "muted") albo właściwość "state",
a kolory i odstępy są tylko tutaj. Dzięki temu zmiana wyglądu nie wymaga
grzebania w kodzie stron.

Motyw to zestaw kolorów (klasa Theme). Stałe BACKGROUND, ACCENT itd. zawsze
pokazują aktualny motyw, bo apply_theme() je podmienia. Dlatego inne moduły
czytają je jako theme.ACCENT (w chwili rysowania), a nie przez
"from .theme import ACCENT" (to skopiowałoby kolor raz, przy starcie).
"""

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPalette
from PySide6.QtWidgets import QAbstractButton, QApplication, QPushButton

from ..core.settings import DEFAULT_THEME

from ..core.i18n import N_, tr

ASSETS_DIR = Path(__file__).resolve().parent / "assets"


@dataclass(frozen=True)
class Theme:
    label: str  # nazwa w ustawieniach (po polsku, tłumaczona przez tr przy wyświetlaniu)
    background: str
    surface: str  # karty, pola, przyciski
    surface_hover: str
    border: str
    text: str
    muted: str
    accent: str
    on_accent: str  # tekst na przycisku w kolorze akcentu
    warning: str
    # Paski żywiołów u potwora: zielony = tym warto bić, czerwony = odporny.
    good: str = "#81c784"
    bad: str = "#ef5350"
    # Zaokrąglenie rogów: 1.0 = nowoczesne (8 px na przyciskach), 0 = kanciaste jak w Tibii.
    roundness: float = 1.0
    # Tło przycisków: zwykły kolor albo gradient (drewno, kamień). Puste = surface.
    button: str = ""
    button_hover: str = ""
    # Ramka "wypukła" jak w starych programach: jasna krawędź u góry, ciemna u dołu.
    bevel_light: str = ""
    bevel_dark: str = ""
    # Ikony są jasne (pod ciemne tło). Jasny motyw bierze wersje "-dark", np. github-dark.svg.
    icon_suffix: str = ""


THEMES: dict[str, Theme] = {
    "dark": Theme(
        label=N_("Ciemny"),
        background="#17181c",
        surface="#22242a",
        surface_hover="#2b2e35",
        border="#33363f",
        text="#e8eaed",
        muted="#8b9099",
        accent="#e3a83b",  # złoty, jak złoto w Tibii
        on_accent="#17181c",
        warning="#f0a04b",
    ),
    "light": Theme(
        label=N_("Jasny"),
        background="#f3f4f6",
        surface="#ffffff",
        surface_hover="#e8eaee",
        border="#cfd3da",
        text="#1f2328",
        muted="#636c76",
        accent="#92600f",  # ciemniejsze złoto, żeby było czytelne na białym
        on_accent="#ffffff",
        warning="#b35c00",
        good="#2e7d32",  # ciemniejsze, bo jasna zieleń ginie na białym
        bad="#c62828",
        icon_suffix="-dark",
    ),
    # Ciepłe brązy i gradienty jak drewniane okna starego Elfbota (własne kolory, bez grafik).
    "wood": Theme(
        label=N_("Drewno"),
        background="#3a2817",
        surface="#5a3d22",
        surface_hover="#6e4b2a",
        border="#24170b",
        text="#f6e7c8",
        muted="#c9ab80",
        accent="#f2c14e",
        on_accent="#2a1a0b",
        warning="#ff9f43",
        bad="#ff7a6b",  # jaśniejszy czerwony, bo zwykły ginie na brązie
        roundness=0.25,
        button="qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #7a5430, stop:0.5 #5f3f22, stop:1 #4a311a)",
        button_hover="qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #8d6239, stop:0.5 #704b29, stop:1 #573a1f)",
        bevel_light="#9a7148",
        bevel_dark="#1c1108",
    ),
    # Szary kamień z wypukłymi ramkami, inspirowany oknami klienta Tibii (własne kolory, bez grafik CipSoft).
    "tibia": Theme(
        label=N_("Interfejs Tibii"),
        background="#2b2b2b",
        surface="#3c3c3c",
        surface_hover="#4a4a4a",
        border="#161616",
        text="#d8d8d8",
        muted="#9a9a9a",
        accent="#e2c35c",
        on_accent="#1a1a1a",
        warning="#ff9933",
        roundness=0,
        button="qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #5a5a5a, stop:1 #3a3a3a)",
        button_hover="qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #6a6a6a, stop:1 #464646)",
        bevel_light="#7c7c7c",
        bevel_dark="#121212",
    ),
}

# Aktualny motyw. Podmienia je apply_theme(); wartości startowe = motyw domyślny.
BACKGROUND = SURFACE = SURFACE_HOVER = BORDER = TEXT = MUTED = ACCENT = WARNING = GOOD = BAD = ""


def _set_colors(t: Theme) -> None:
    global BACKGROUND, SURFACE, SURFACE_HOVER, BORDER, TEXT, MUTED, ACCENT, WARNING, GOOD, BAD
    BACKGROUND, SURFACE, SURFACE_HOVER, BORDER = t.background, t.surface, t.surface_hover, t.border
    TEXT, MUTED, ACCENT, WARNING = t.text, t.muted, t.accent, t.warning
    GOOD, BAD = t.good, t.bad


_current = THEMES[DEFAULT_THEME]
_set_colors(_current)


def build_style(t: Theme) -> str:
    """Style sheet dla motywu. Ten sam układ dla wszystkich motywów, różnią się kolory i rogi."""

    def r(px: int) -> str:
        return f"{round(px * t.roundness)}px"

    button = t.button or t.surface
    button_hover = t.button_hover or t.surface_hover
    if t.bevel_light:
        button_border = (
            f"border: 1px solid {t.bevel_dark}; border-top-color: {t.bevel_light}; "
            f"border-left-color: {t.bevel_light};"
        )
    else:
        button_border = f"border: 1px solid {t.border};"
    return f"""
QWidget {{
    background: {t.background};
    color: {t.text};
    font-size: 13px;
}}
QLabel, QCheckBox {{ background: transparent; }}
QLabel#title {{ font-size: 18px; font-weight: 600; }}
QLabel#appName {{ font-size: 20px; font-weight: 600; color: {t.accent}; }}
QLabel#muted {{ color: {t.muted}; }}
QLabel#warning {{ color: {t.warning}; }}
QLabel#sectionTitle {{ color: {t.muted}; font-size: 11px; font-weight: 600; }}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {t.surface};
    border: 1px solid {t.border};
    border-radius: {r(8)};
    padding: 6px 8px;
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border-color: {t.accent}; }}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox::down-arrow {{ image: url("{ASSETS_DIR.as_posix()}/chevron-down.svg"); width: 10px; height: 6px; }}
QComboBox QAbstractItemView {{
    background: {t.surface};
    border: 1px solid {t.border};
    selection-background-color: {t.surface_hover};
    selection-color: {t.text};
}}
QToolTip {{ background: {t.surface}; color: {t.text}; border: 1px solid {t.border}; padding: 4px; }}
/* Pole tekstowe wewnątrz QSpinBox nie dostaje drugiej ramki ani odstępów. */
QSpinBox QLineEdit, QDoubleSpinBox QLineEdit {{ border: none; padding: 0; background: transparent; }}
/* Bez strzałek: w ciemnym motywie wyglądały źle, a level i tak się wpisuje (albo kółkiem myszy). */
QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{ width: 0; border: none; }}
QSpinBox::up-arrow, QSpinBox::down-arrow, QDoubleSpinBox::up-arrow, QDoubleSpinBox::down-arrow {{ width: 0; height: 0; }}

QPushButton, QToolButton {{
    background: {button};
    {button_border}
    border-radius: {r(8)};
    padding: 6px 12px;
}}
QPushButton:hover, QToolButton:hover {{ background: {button_hover}; }}
QPushButton#primary {{
    background: {t.accent};
    color: {t.on_accent};
    border: none;
    font-weight: 600;
}}
QPushButton#menu {{
    text-align: left;
    padding: 14px 16px;
    font-size: 15px;
    border-radius: {r(12)};
}}
QPushButton#menu:hover {{ border-color: {t.accent}; }}
QPushButton#menu:disabled {{ color: {t.muted}; background: transparent; }}
QPushButton#submenu {{
    text-align: left;
    padding: 9px 12px;
    font-size: 13px;
    border-radius: {r(10)};
}}
QPushButton#submenu:hover {{ border-color: {t.accent}; }}
QToolButton#icon {{ border: none; background: transparent; font-size: 18px; padding: 2px 6px; }}
QToolButton#icon:hover {{ background: {t.surface_hover}; }}
/* Boosted potwór i boss pod nagłówkiem: mały, płaski przycisk z obrazkiem. */
QToolButton#boosted {{ border: none; background: transparent; padding: 1px 4px; font-size: 12px; }}
QToolButton#boosted:hover {{ background: {t.surface_hover}; }}
QToolButton#boosted:disabled {{ color: {t.text}; }}

QListWidget {{
    background: transparent;
    border: none;
    outline: none;
}}
QListWidget::item {{
    background: {t.surface};
    border-radius: {r(8)};
    padding: 10px;
    margin: 3px 0;
}}
QListWidget::item:hover {{ background: {t.surface_hover}; }}
QListWidget::item:selected {{ background: {t.surface_hover}; color: {t.text}; }}

QFrame#banner {{
    background: {t.surface};
    border: 1px solid {t.accent};
    border-radius: {r(8)};
}}

/* Karty kroków: wygląd zależy od właściwości "state" (done / current / todo). */
QFrame#step {{
    background: {t.surface};
    {button_border}
    border-radius: {r(10)};
}}
QFrame#step:hover {{ background: {t.surface_hover}; }}
QFrame#step[state="current"] {{ border: 2px solid {t.accent}; }}
QFrame#step[state="done"] {{ background: transparent; }}
QFrame#step[state="done"] QLabel {{ color: {t.muted}; }}

/* Kafelki w sekcji „Potwory”: obrazek i podpis, jak lista potworów w poradnikach. */
QFrame#monsterTile {{
    background: {t.surface};
    {button_border}
    border-radius: {r(8)};
}}
QFrame#monsterTile QLabel {{ font-size: 11px; background: transparent; }}

/* Pinezki kroku (NPC, miejsce) jako kafelki po prawej stronie karty: klik pokazuje mapę. */
QFrame#markerTile {{
    background: {t.background};
    border: 1px solid {t.border};
    border-radius: {r(6)};
}}
QFrame#markerTile:hover {{ border: 1px solid {t.accent}; }}
QFrame#markerTile QLabel {{ font-size: 10px; background: transparent; border: none; }}

QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border-radius: {r(5)};
    border: 2px solid {t.muted};
    background: transparent;
}}
QCheckBox::indicator:checked {{ background: {t.accent}; border-color: {t.accent}; }}

QScrollArea {{ border: none; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {t.border}; border-radius: {r(4)}; min-height: 24px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}

QSlider::groove:horizontal {{ height: 4px; background: {t.border}; border-radius: {r(2)}; }}
QSlider::sub-page:horizontal {{ background: {t.accent}; border-radius: {r(2)}; }}
QSlider::handle:horizontal {{
    background: {t.text};
    width: 14px;
    margin: -6px 0;
    border-radius: {r(7)};
}}
"""


def theme_key(key: str) -> str:
    """Znany klucz motywu albo domyślny (np. po ręcznej edycji settings.json)."""
    return key if key in THEMES else DEFAULT_THEME


def apply_theme(app: QApplication, key: str = DEFAULT_THEME) -> None:
    """Ustawia motyw całej aplikacji. Można wołać w trakcie działania: okna przerysują się same."""
    global _current
    t = _current = THEMES[theme_key(key)]
    _set_colors(t)
    # Fusion wygląda tak samo na każdym systemie, więc style sheet działa przewidywalnie.
    app.setStyle("Fusion")
    app.setStyleSheet(build_style(t))
    palette = app.palette()
    # Kolor linków (np. „TibiaWiki”) bierze się z palety, nie ze style sheet.
    palette.setColor(QPalette.ColorRole.Link, QColor(t.accent))
    # Szara podpowiedź w pustych polach (np. „min lvl.”), wyraźnie inna niż wpisany tekst.
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(t.muted))
    # Tekst w polach rysowanych przez Qt (np. tekst HTML w QLabel) też z motywu.
    palette.setColor(QPalette.ColorRole.Text, QColor(t.text))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(t.text))
    app.setPalette(palette)
    # Widżety rysowane ręcznie (kafelki, paski) czytają kolory przy rysowaniu, więc wystarczy odświeżyć.
    for widget in app.allWidgets():
        name = widget.property("themedIcon")
        if name and isinstance(widget, QAbstractButton):
            widget.setIcon(icon(name))
        widget.update()


def icon(name: str) -> QIcon:
    """Ikona z assets/. Nazwa bez ".svg", bo wersję (jasną/ciemną) dobiera motyw."""
    path = ASSETS_DIR / f"{name}{_current.icon_suffix}.svg"
    if not path.exists():
        path = ASSETS_DIR / f"{name}.svg"
    return QIcon(str(path))


def report_button() -> QPushButton:
    """Przycisk „Zgłoś błąd” (logo GitHuba), ten sam przy queście i przy potworze."""
    button = QPushButton(" " + tr("Zgłoś błąd"))
    button.setIcon(icon("github"))
    # apply_theme podmieni ikonę przy zmianie motywu.
    button.setProperty("themedIcon", "github")
    button.setIconSize(QSize(16, 16))
    button.setToolTip(tr("Otwiera zgłoszenie na GitHubie (potrzebne darmowe konto GitHub)"))
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button
