"""Główne okno: nagłówek z trybikiem, pasek aktualizacji i strony (lista / quest)."""

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..core.models import Quest
from ..core.progress import ProgressStore
from ..core.settings import load_settings, save_settings
from .quest_list import QuestListPage
from .quest_view import QuestView
from .settings_dialog import SettingsDialog


class MainWindow(QMainWindow):
    def __init__(
        self, progress: ProgressStore, settings_path: Path, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("TibiaHelper")
        # Okno zawsze nad grą.
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.resize(380, 560)
        self._data_version = 0

        # Dwie "strony" w jednym oknie zamiast dwóch okien: mniej miejsca obok gry.
        self._list_page = QuestListPage(progress)
        self._quest_view = QuestView(progress)
        self._stack = QStackedWidget()
        self._stack.addWidget(self._list_page)
        self._stack.addWidget(self._quest_view)

        self._banner = UpdateBanner()
        self._banner.hide()

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(12, 8, 12, 12)
        layout.addLayout(self._build_header())
        layout.addWidget(self._banner)
        layout.addWidget(self._stack, 1)
        self.setCentralWidget(central)

        self._list_page.quest_selected.connect(self._open_quest)
        self._quest_view.back_requested.connect(self._show_list)
        self._quest_view.progress_changed.connect(self._list_page.refresh_progress)

        self._settings_path = settings_path
        self._settings = load_settings(settings_path)
        self.setWindowOpacity(self._settings.opacity)
        if self._settings.geometry:
            # Qt sam pilnuje, żeby okno nie wylądowało poza ekranem (np. po odłączeniu monitora).
            self.restoreGeometry(QByteArray.fromBase64(self._settings.geometry.encode("ascii")))

    def set_quests(self, quests: list[Quest], data_version: int) -> None:
        self._data_version = data_version
        self._list_page.set_quests(quests)
        self._quest_view.set_data_version(data_version)

    def offer_update(self, data_version: int, on_accept: Callable[[], None]) -> None:
        """Pokazuje pasek „są nowsze poradniki”. Dane zmieniają się dopiero po kliknięciu."""
        self._banner.show_offer(data_version, on_accept)

    def _build_header(self) -> QHBoxLayout:
        name = QLabel("TibiaHelper")
        name.setObjectName("appName")
        gear = QToolButton(text="⚙")
        gear.setObjectName("icon")
        gear.setToolTip("Ustawienia")
        gear.setCursor(Qt.CursorShape.PointingHandCursor)
        gear.clicked.connect(self._open_settings)

        header = QHBoxLayout()
        header.addWidget(name)
        header.addStretch(1)
        header.addWidget(gear)
        return header

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self._settings.opacity, self._data_version, self)
        dialog.opacity_changed.connect(self._set_opacity)
        dialog.exec()
        # Zapis po zamknięciu dialogu, a nie przy każdym ruchu suwaka.
        self._save_settings()

    def _set_opacity(self, opacity: float) -> None:
        self._settings.opacity = opacity
        self.setWindowOpacity(opacity)

    def _save_settings(self) -> None:
        self._settings.geometry = bytes(self.saveGeometry().toBase64()).decode("ascii")
        save_settings(self._settings_path, self._settings)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 (nazwa z Qt)
        self._save_settings()
        super().closeEvent(event)

    def _open_quest(self, quest: Quest) -> None:
        self._quest_view.show_quest(quest)
        self._stack.setCurrentWidget(self._quest_view)

    def _show_list(self) -> None:
        self._stack.setCurrentWidget(self._list_page)


class UpdateBanner(QFrame):
    """Pasek nad listą: „Są nowsze poradniki” + Zaktualizuj / Później."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("banner")
        self._on_accept: Callable[[], None] | None = None

        self._text = QLabel(wordWrap=True)
        later = QPushButton("Później")
        later.clicked.connect(self.hide)
        accept = QPushButton("Zaktualizuj")
        accept.setObjectName("primary")
        accept.clicked.connect(self._accept)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(later)
        buttons.addWidget(accept)

        layout = QVBoxLayout(self)
        layout.addWidget(self._text)
        layout.addLayout(buttons)

    def show_offer(self, data_version: int, on_accept: Callable[[], None]) -> None:
        self._on_accept = on_accept
        self._text.setText(f"Są nowsze poradniki (wersja {data_version}). Zaktualizować?")
        self.show()

    def _accept(self) -> None:
        self.hide()
        if self._on_accept is not None:
            self._on_accept()
