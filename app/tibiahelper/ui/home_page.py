"""Ekran startowy: duże przyciski jeden pod drugim (Questy, Expowiska, Bossy)."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget


class HomePage(QWidget):
    quests_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(10)

        quests = _menu_button("📜  Questy", "Poradniki questów krok po kroku")
        quests.clicked.connect(self.quests_requested)
        layout.addWidget(quests)

        # Expowiska i bossy dojdą w etapach 8 i 9; do tego czasu przyciski są nieaktywne.
        for text in ("⚔  Expowiska", "💀  Bossy"):
            button = _menu_button(text, "Wkrótce")
            button.setEnabled(False)
            layout.addWidget(button)

        layout.addStretch(1)
        note = QLabel("Dane: TibiaWiki (CC BY-SA 4.0), mapy: tibiamaps")
        note.setObjectName("muted")
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(note)


def _menu_button(text: str, hint: str) -> QPushButton:
    # Dwie linie w jednym przycisku: nazwa i krótki opis pod spodem.
    button = QPushButton(f"{text}\n{hint}")
    button.setObjectName("menu")
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button
