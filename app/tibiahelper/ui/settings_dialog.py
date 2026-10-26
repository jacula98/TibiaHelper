"""Okno ustawień otwierane trybikiem ⚙ w nagłówku."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout

from ..core.settings import MAX_OPACITY, MIN_OPACITY


class SettingsDialog(QDialog):
    # Zmiana od razu widoczna w głównym oknie, bez przycisku "Zastosuj".
    opacity_changed = Signal(float)

    def __init__(self, opacity: float, data_version: int, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Ustawienia")
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
        header.addWidget(QLabel("Widoczność okna"))
        header.addStretch(1)
        header.addWidget(self._value)

        version = QLabel(f"Wersja poradników: {data_version}")
        version.setObjectName("muted")

        # Źródła i licencje: CC BY-SA wymaga podania, skąd są dane.
        sources = QLabel(
            "Źródła:<br>"
            '• poradniki na podstawie <a href="https://tibia.fandom.com/">TibiaWiki</a> '
            '(<a href="https://creativecommons.org/licenses/by-sa/4.0/">CC BY-SA 4.0</a>)<br>'
            '• mapy z <a href="https://tibiamaps.io/">tibiamaps</a> '
            '(<a href="https://github.com/tibiamaps/tibia-map-data">tibia-map-data</a>)<br>'
            "• obrazki potworów z TibiaWiki, © CipSoft GmbH (pobierane przy pierwszym użyciu)"
        )
        sources.setObjectName("muted")
        sources.setWordWrap(True)
        sources.setOpenExternalLinks(True)

        close = QPushButton("Zamknij")
        close.setObjectName("primary")
        close.clicked.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addLayout(header)
        layout.addWidget(slider)
        layout.addSpacing(12)
        layout.addWidget(version)
        layout.addWidget(sources)
        layout.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)

    def _on_slider(self, percent: int) -> None:
        self._show_value(percent)
        self.opacity_changed.emit(percent / 100)

    def _show_value(self, percent: int) -> None:
        self._value.setText(f"{percent}%")
