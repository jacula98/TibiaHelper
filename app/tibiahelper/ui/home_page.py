"""Ekran startowy: duże przyciski jeden pod drugim (Questy, Potwory, Expowiska, Bossy)."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget


class HomePage(QWidget):
    quests_requested = Signal()
    monsters_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(10)

        quests = _menu_button("📜  Questy", "Poradniki questów krok po kroku")
        quests.clicked.connect(self.quests_requested)
        layout.addWidget(quests)

        monsters = _menu_button("🐉  Potwory", "HP, exp, słabości, loot i gdzie występują")
        monsters.clicked.connect(self.monsters_requested)
        layout.addWidget(monsters)

        # Expowiska i bossy dojdą w kolejnych etapach; do tego czasu przyciski są nieaktywne.
        for text in ("⚔  Expowiska", "💀  Bossy"):
            button = _menu_button(text, "Wkrótce")
            button.setEnabled(False)
            layout.addWidget(button)

        layout.addStretch(1)


def _menu_button(text: str, hint: str) -> QPushButton:
    # Dwie linie w jednym przycisku: nazwa i krótki opis pod spodem.
    button = QPushButton(f"{text}\n{hint}")
    button.setObjectName("menu")
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button
