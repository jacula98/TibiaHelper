"""Ekran startowy: duże przyciski jeden pod drugim (Questy, Hunt/Bestiary zones, Bossy, Przedmioty, Potwory, Narzędzia, Quality of life)."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget

from ..core.i18n import tr


class HomePage(QWidget):
    quests_requested = Signal()
    monsters_requested = Signal()
    items_requested = Signal()
    tools_requested = Signal()
    qol_requested = Signal()
    bosses_requested = Signal()
    hunts_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(10)

        quests = _menu_button("📜  " + tr("Questy"), tr("Poradniki questów krok po kroku"))
        quests.clicked.connect(self.quests_requested)
        layout.addWidget(quests)

        # „Hunt/Bestiary zones” bez tłumaczenia: to nazwa, której gracze używają w każdym języku.
        zones = _menu_button("⚔  Hunt/Bestiary zones", tr("Miejsca na twój lvl, potwory i Bestiary"))
        zones.clicked.connect(self.hunts_requested)
        layout.addWidget(zones)

        bosses = _menu_button("💀  " + tr("Bossy"), tr("Wymagania, dojście, jak bić i Bosstiary"))
        bosses.clicked.connect(self.bosses_requested)
        layout.addWidget(bosses)

        items = _menu_button("🎒  " + tr("Przedmioty"), tr("Komu sprzedać, gdzie kupić, z czego wypada"))
        items.clicked.connect(self.items_requested)
        layout.addWidget(items)

        monsters = _menu_button("🐉  " + tr("Potwory"), tr("HP, exp, słabości, loot i gdzie występują"))
        monsters.clicked.connect(self.monsters_requested)
        layout.addWidget(monsters)

        tools = _menu_button("🧮  " + tr("Narzędzia"), tr("Store, podział lootu, stamina i skille"))
        tools.clicked.connect(self.tools_requested)
        layout.addWidget(tools)

        qol = _menu_button("✨  Quality of life", tr("Minimapa, loot filter, UI i hotkeye"))
        qol.clicked.connect(self.qol_requested)
        layout.addWidget(qol)

        layout.addStretch(1)


def _menu_button(text: str, hint: str) -> QPushButton:
    # Dwie linie w jednym przycisku: nazwa i krótki opis pod spodem.
    button = QPushButton(f"{text}\n{hint}")
    button.setObjectName("menu")
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button
