"""Główne okno: przełącza między listą questów a widokiem kroków."""

from pathlib import Path

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QLabel, QMainWindow, QSlider, QStackedWidget, QWidget

from ..core.models import Quest
from ..core.progress import ProgressStore
from ..core.settings import MAX_OPACITY, MIN_OPACITY, load_settings, save_settings
from .quest_list import QuestListPage
from .quest_view import QuestView


class MainWindow(QMainWindow):
    def __init__(
        self, progress: ProgressStore, settings_path: Path, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("TibiaHelper")
        # Okno zawsze nad grą.
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.resize(360, 520)

        # Dwie "strony" w jednym oknie zamiast dwóch okien: mniej miejsca obok gry.
        self._list_page = QuestListPage(progress)
        self._quest_view = QuestView(progress)
        self._stack = QStackedWidget()
        self._stack.addWidget(self._list_page)
        self._stack.addWidget(self._quest_view)
        self.setCentralWidget(self._stack)

        self._list_page.quest_selected.connect(self._open_quest)
        self._quest_view.back_requested.connect(self._show_list)
        self._quest_view.progress_changed.connect(self._list_page.refresh_progress)

        self._settings_path = settings_path
        self._settings = load_settings(settings_path)
        self._build_status_bar()
        if self._settings.geometry:
            # Qt sam pilnuje, żeby okno nie wylądowało poza ekranem (np. po odłączeniu monitora).
            self.restoreGeometry(QByteArray.fromBase64(self._settings.geometry.encode("ascii")))

    def set_quests(self, quests: list[Quest], data_version: int, note: str = "") -> None:
        self._list_page.set_quests(quests)
        self._quest_view.set_data_version(data_version)
        self._data_label.setText(f"dane v{data_version}" + (f" · {note}" if note else ""))

    def _build_status_bar(self) -> None:
        # Suwak w procentach, bo QSlider przyjmuje tylko liczby całkowite.
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(int(MIN_OPACITY * 100), int(MAX_OPACITY * 100))
        slider.setValue(round(self._settings.opacity * 100))
        slider.setMaximumWidth(120)
        slider.setToolTip("Przezroczystość okna")
        slider.valueChanged.connect(self._on_opacity_changed)
        self.setWindowOpacity(self._settings.opacity)

        self._data_label = QLabel()
        self._data_label.setStyleSheet("color: gray;")
        bar = self.statusBar()
        bar.addWidget(self._data_label, 1)
        bar.addPermanentWidget(QLabel("Widoczność:"))
        bar.addPermanentWidget(slider)

    def _on_opacity_changed(self, percent: int) -> None:
        # Zapisujemy dopiero przy zamknięciu okna, żeby nie pisać na dysk przy każdym ruchu suwaka.
        self._settings.opacity = percent / 100
        self.setWindowOpacity(self._settings.opacity)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 (nazwa z Qt)
        self._settings.geometry = bytes(self.saveGeometry().toBase64()).decode("ascii")
        save_settings(self._settings_path, self._settings)
        super().closeEvent(event)

    def _open_quest(self, quest: Quest) -> None:
        self._quest_view.show_quest(quest)
        self._stack.setCurrentWidget(self._quest_view)

    def _show_list(self) -> None:
        self._stack.setCurrentWidget(self._list_page)
