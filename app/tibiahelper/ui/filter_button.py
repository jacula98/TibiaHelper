"""Przycisk „Filtry” z listą grup do pokazania (np. bossy, quest itemy).

Każda grupa to pole do zaznaczenia w menu. Domyślnie wszystkie są odznaczone, czyli
ukryte: lista od razu pokazuje to, czego gracz zwykle szuka, bez „śmieci”.
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QMenu, QToolButton, QWidget


class FilterButton(QToolButton):
    changed = Signal()

    def __init__(self, groups: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setToolTip("Zaznacz, co jeszcze pokazać na liście")
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self)
        menu.addSection("Pokaż też:")
        self._actions = []
        for name in groups:
            action = menu.addAction(name)
            action.setCheckable(True)
            action.toggled.connect(self._on_toggled)
            self._actions.append(action)
        self.setMenu(menu)
        self._update_text()

    def shown(self) -> set[str]:
        """Nazwy grup, które gracz zaznaczył (pokazuje je mimo domyślnego ukrycia)."""
        return {action.text() for action in self._actions if action.isChecked()}

    def _on_toggled(self) -> None:
        self._update_text()
        self.changed.emit()

    def _update_text(self) -> None:
        # Liczba ukrytych grup w napisie przypomina, że lista nie jest pełna.
        hidden = len(self._actions) - len(self.shown())
        self.setText(f"Filtry ({hidden} ukr.)" if hidden else "Filtry")
