"""Strona z listą questów: wyszukiwarka, filtr levelu i lista."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..core.filters import filter_quests
from ..core.models import Quest
from ..core.progress import ProgressStore

MAX_LEVEL = 5000


class QuestListPage(QWidget):
    # object, a nie Quest: Qt nie zna typów pydantic, a object przekazuje referencję bez kopiowania.
    quest_selected = Signal(object)
    back_requested = Signal()

    def __init__(self, progress: ProgressStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._progress = progress
        self._quests: list[Quest] = []

        self._search = QLineEdit(placeholderText="Szukaj questa…", clearButtonEnabled=True)
        # Pole tekstowe zamiast QSpinBox: puste pokazuje szarą podpowiedź „min lvl.”,
        # a walidator pozwala wpisać tylko liczbę.
        self._level = QLineEdit(placeholderText="min lvl.", clearButtonEnabled=True)
        self._level.setValidator(QIntValidator(0, MAX_LEVEL, self._level))
        self._level.setFixedWidth(90)
        self._level.setToolTip("Twój level: pokażę tylko questy, które możesz już zrobić")

        self._list = QListWidget()
        self._empty = QLabel(alignment=Qt.AlignmentFlag.AlignCenter, wordWrap=True)

        back = QPushButton("← Menu")
        back.clicked.connect(self.back_requested)
        top = QHBoxLayout()
        top.addWidget(back)
        top.addStretch(1)

        filters = QHBoxLayout()
        filters.addWidget(self._search, 1)
        filters.addWidget(self._level)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)  # odstępy daje już główne okno
        layout.addLayout(top)
        layout.addLayout(filters)
        layout.addWidget(self._list, 1)
        layout.addWidget(self._empty, 1)

        self._search.textChanged.connect(self._refresh)
        self._level.textChanged.connect(self._refresh)
        # Tylko pojedyncze kliknięcie: itemActivated odpaliłby się dodatkowo przy dwukliku.
        self._list.itemClicked.connect(self._on_item_clicked)

    def set_quests(self, quests: list[Quest]) -> None:
        self._quests = quests
        self._refresh()

    def refresh_progress(self) -> None:
        """Odświeża liczniki kroków po zmianie postępu w widoku questa."""
        self._refresh()

    def _refresh(self) -> None:
        level = int(self._level.text()) if self._level.text().isdigit() else None
        shown = filter_quests(self._quests, self._search.text(), level)
        # Gotowe poradniki na górze; szkiców (w trybie autora) są setki, więc idą niżej.
        shown.sort(key=lambda quest: quest.status != "reviewed")

        self._list.clear()
        for quest in shown:
            item = QListWidgetItem(_item_text(quest, self._progress.count_done(quest)))
            # Trzymamy cały obiekt questa w elemencie listy, żeby nie szukać go po nazwie.
            item.setData(Qt.ItemDataRole.UserRole, quest)
            self._list.addItem(item)

        if not self._quests:
            self._empty.setText("Brak przejrzanych questów do pokazania.")
        elif not shown:
            self._empty.setText("Nic nie pasuje do wyszukiwania.")
        self._list.setVisible(bool(shown))
        self._empty.setVisible(not shown)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        self.quest_selected.emit(item.data(Qt.ItemDataRole.UserRole))


def _item_text(quest: Quest, done: int) -> str:
    total = len(quest.steps)
    details = [f"lvl {quest.min_level}+"]
    if quest.premium:
        details.append("premium")
    if quest.status == "draft":
        details.append("DRAFT")
    if done == total:
        prefix = "✓ "
    elif done:
        prefix = f"{done}/{total} "
    else:
        prefix = ""
    return f"{prefix}{quest.name}  ({', '.join(details)})"
