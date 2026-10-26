"""Główne okno: przełącza między listą questów a widokiem kroków."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMainWindow, QStackedWidget, QWidget

from ..core.models import Quest
from ..core.progress import ProgressStore
from .quest_list import QuestListPage
from .quest_view import QuestView


class MainWindow(QMainWindow):
    def __init__(
        self, quests: list[Quest], progress: ProgressStore, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("TibiaHelper")
        # Okno zawsze nad grą. Przezroczystość i zapamiętywanie pozycji dochodzą w etapie 6.
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

        self._list_page.set_quests(quests)

    def _open_quest(self, quest: Quest) -> None:
        self._quest_view.show_quest(quest)
        self._stack.setCurrentWidget(self._quest_view)

    def _show_list(self) -> None:
        self._stack.setCurrentWidget(self._list_page)
