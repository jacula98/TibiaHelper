"""Okno ustawień otwierane trybikiem ⚙ w nagłówku."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QDialog, QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout

from ..core.i18n import LANGUAGES, N_, current_language, load_catalog, tr
from ..core.settings import MAX_OPACITY, MIN_OPACITY
from .theme import THEMES, theme_key

RESTART_HINT = N_("Język zmieni się po ponownym uruchomieniu programu.")


class SettingsDialog(QDialog):
    # Zmiana od razu widoczna w głównym oknie, bez przycisku "Zastosuj".
    opacity_changed = Signal(float)
    language_changed = Signal(str)  # kod języka, np. "en"

    theme_changed = Signal(str)

    def __init__(self, opacity: float, data_version: int, language: str, theme: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Ustawienia"))
        # Dialog też musi być nad grą, inaczej schowa się pod oknem Tibii.
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setMinimumWidth(300)

        self._value = QLabel()
        # Suwak w procentach, bo QSlider przyjmuje tylko liczby całkowite.
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(round(MIN_OPACITY * 100), round(MAX_OPACITY * 100))
        slider.setValue(round(opacity * 100))
        slider.valueChanged.connect(self._on_slider)
        self._show_value(slider.value())

        header = QHBoxLayout()
        header.addWidget(QLabel(tr("Widoczność okna")))
        header.addStretch(1)
        header.addWidget(self._value)

        # Lista motywów: widać nazwę, a w danych elementu (userData) siedzi klucz do zapisu.
        themes = QComboBox()
        for key, t in THEMES.items():
            themes.addItem(tr(t.label), key)
        themes.setCurrentIndex(themes.findData(theme_key(theme)))
        themes.currentIndexChanged.connect(lambda _: self.theme_changed.emit(themes.currentData()))
        theme_row = QHBoxLayout()
        theme_row.addWidget(QLabel(tr("Motyw")))
        theme_row.addStretch(1)
        theme_row.addWidget(themes)

        # Teksty są wstawiane przy budowaniu okien, więc nowy język działa od następnego uruchomienia.
        self._restart = QLabel(wordWrap=True)
        self._restart.setObjectName("warning")
        # Nazwy języków są w tych językach, więc ich nie tłumaczymy; w danych pozycji jest kod.
        self._language = QComboBox()
        for code, name in LANGUAGES.items():
            self._language.addItem(name, code)
        self._language.setCurrentIndex(max(self._language.findData(language), 0))
        self._language.currentIndexChanged.connect(self._on_language)
        # Język mógł być zmieniony wcześniej w tej sesji: wtedy przypomnienie widać od razu.
        self._show_restart_hint(language)
        language_row = QHBoxLayout()
        language_row.addWidget(QLabel(tr("Język")))
        language_row.addStretch(1)
        language_row.addWidget(self._language)

        version = QLabel(tr("Wersja poradników: {n}", n=data_version))
        version.setObjectName("muted")

        # Źródła i licencje: CC BY-SA wymaga podania, skąd są dane.
        # Linki są wstawiane jako {wiki} itd., żeby tłumaczenie nie mogło zepsuć adresów.
        sources = QLabel(
            tr("Źródła:")
            + "<br>• "
            + tr(
                "poradniki na podstawie {wiki} ({license})",
                wiki='<a href="https://tibia.fandom.com/">TibiaWiki</a>',
                license='<a href="https://creativecommons.org/licenses/by-sa/4.0/">CC BY-SA 4.0</a>',
            )
            + "<br>• "
            + tr(
                "mapy z {maps} ({repo})",
                maps='<a href="https://tibiamaps.io/">tibiamaps</a>',
                repo='<a href="https://github.com/tibiamaps/tibia-map-data">tibia-map-data</a>',
            )
            + "<br>• "
            + tr("obrazki potworów i przedmiotów z TibiaWiki, © CipSoft GmbH (pobierane przy pierwszym użyciu)")
            + "<br>• "
            + tr("dzisiejszy boosted potwór i boss z TibiaWiki (sprawdzane raz dziennie)")
            + "<br>• "
            + tr(
                "miejsca występowania potworów: Źródło danych: {route} (za zgodą TibiaRoute)",
                route='<a href="https://tibiaroute.com/">tibiaroute.com</a>',
            )
            + "<br>• "
            + tr(
                "przycisk Stream co kilka minut sprawdza na {kick}, czy autor nadaje",
                kick='<a href="https://kick.com/jackyykick">kick.com</a>',
            )
            + "<br>• "
            + tr(
                "ostatnie raporty graczy z {form} (publiczny arkusz, najwyżej co 15 minut, przy otwarciu bossa albo miejsca)",
                form='<a href="https://docs.google.com/forms/d/e/1FAIpQLSdhU_EixKIDQvsA7Di0v8rWw1YeaPniMr8g02s3kUylfg_p6Q/viewform">Formularzy Google</a>',
            )
        )
        sources.setObjectName("muted")
        sources.setWordWrap(True)
        sources.setOpenExternalLinks(True)

        close = QPushButton(tr("Zamknij"))
        close.setObjectName("primary")
        close.clicked.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addLayout(header)
        layout.addWidget(slider)
        layout.addSpacing(8)
        layout.addLayout(language_row)
        layout.addWidget(self._restart)
        layout.addSpacing(8)
        layout.addLayout(theme_row)
        layout.addSpacing(12)
        layout.addWidget(version)
        layout.addWidget(sources)
        layout.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)

    def _on_slider(self, percent: int) -> None:
        self._show_value(percent)
        self.opacity_changed.emit(percent / 100)

    def _on_language(self, index: int) -> None:
        code = self._language.itemData(index)
        self._show_restart_hint(code)
        self.language_changed.emit(code)

    def _show_restart_hint(self, code: str) -> None:
        # Komunikat w nowym języku: gracz, który go wybrał, na pewno go przeczyta.
        self._restart.setText(restart_hint(code))
        # current_language(): język, w którym program teraz działa. Powrót do niego nie wymaga restartu.
        self._restart.setVisible(code != current_language())

    def _show_value(self, percent: int) -> None:
        self._value.setText(f"{percent}%")


def restart_hint(language: str) -> str:
    """„Uruchom program ponownie” w wybranym języku (a nie w obecnym)."""
    return load_catalog(language).get(RESTART_HINT, RESTART_HINT)
