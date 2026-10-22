"""Strona z listą questów: wyszukiwarka, filtr levelu i lista."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..core.filters import filter_quests
from ..core.models import Quest

MAX_LEVEL = 5000


class QuestListPage(QWidget):
    # object, a nie Quest: Qt nie zna typów pydantic, a object przekazuje referencję bez kopiowania.
    quest_selected = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._quests: list[Quest] = []

        self._search = QLineEdit(placeholderText="Szukaj questa…", clearButtonEnabled=True)
        self._level = QSpinBox(minimum=0, maximum=MAX_LEVEL)
        # Wartość 0 oznacza "bez filtra", więc pokazujemy ją jako tekst.
        self._level.setSpecialValueText("każdy level")
        self._level.setPrefix("mój level: ")
        self._level.setToolTip("Pokaż tylko questy dostępne dla Twojego levelu")

        self._list = QListWidget()
        self._empty = QLabel(alignment=Qt.AlignmentFlag.AlignCenter, wordWrap=True)

        filters = QHBoxLayout()
        filters.addWidget(self._search, 1)
        filters.addWidget(self._level)

        layout = QVBoxLayout(self)
        layout.addLayout(filters)
        layout.addWidget(self._list, 1)
        layout.addWidget(self._empty, 1)

        self._search.textChanged.connect(self._refresh)
        self._level.valueChanged.connect(self._refresh)
        # Tylko pojedyncze kliknięcie: itemActivated odpaliłby się dodatkowo przy dwukliku.
        self._list.itemClicked.connect(self._on_item_clicked)

    def set_quests(self, quests: list[Quest]) -> None:
        self._quests = quests
        self._refresh()

    def _refresh(self) -> None:
        level = self._level.value() or None
        shown = filter_quests(self._quests, self._search.text(), level)

        self._list.clear()
        for quest in shown:
            item = QListWidgetItem(_item_text(quest))
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


def _item_text(quest: Quest) -> str:
    details = [f"lvl {quest.min_level}+"]
    if quest.premium:
        details.append("premium")
    if quest.status == "draft":
        details.append("DRAFT")
    return f"{quest.name}  ({', '.join(details)})"
