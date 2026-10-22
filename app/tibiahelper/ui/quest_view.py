"""Strona z krokami jednego questa."""

from html import escape

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..core.models import Quest, Step


class QuestView(QWidget):
    back_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        back = QPushButton("← Lista questów")
        back.clicked.connect(self.back_requested)

        self._scroll = QScrollArea(widgetResizable=True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        layout = QVBoxLayout(self)
        layout.addWidget(back, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self._scroll, 1)

    def show_quest(self, quest: Quest) -> None:
        # Przy każdym queście budujemy treść od nowa: prościej niż aktualizować stare widżety.
        content = QWidget()
        layout = QVBoxLayout(content)

        title = _label(quest.name)
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        info = f"Level {quest.min_level}+ · {'premium' if quest.premium else 'free'}"
        layout.addWidget(_label(info, muted=True))

        if quest.status == "draft":
            layout.addWidget(_warning("Szkic (draft): ten poradnik nie został jeszcze przejrzany."))
        if quest.needs_review:
            layout.addWidget(_warning("Strona na TibiaWiki zmieniła się. Poradnik może być nieaktualny."))

        if quest.required_items:
            layout.addWidget(_label("Potrzebne: " + ", ".join(quest.required_items)))

        for number, step in enumerate(quest.steps, start=1):
            layout.addWidget(_step_label(number, step))

        if quest.rewards:
            layout.addWidget(_label("Nagrody: " + ", ".join(quest.rewards)))

        # Link do źródła jest wymagany przez licencję CC BY-SA.
        source = QLabel(
            f'Źródło: <a href="{escape(quest.source_url, quote=True)}">TibiaWiki</a>'
            " (CC BY-SA 4.0)"
        )
        source.setOpenExternalLinks(True)
        layout.addWidget(source)

        layout.addStretch(1)
        self._scroll.setWidget(content)


def _label(text: str, muted: bool = False) -> QLabel:
    # PlainText: tekst z pliku danych nie jest interpretowany jako HTML.
    label = QLabel(text, wordWrap=True, textFormat=Qt.TextFormat.PlainText)
    if muted:
        label.setStyleSheet("color: gray;")
    return label


def _warning(text: str) -> QLabel:
    label = _label(text)
    label.setStyleSheet("color: #b36b00;")
    return label


def _step_label(number: int, step: Step) -> QLabel:
    lines = [f"{number}. {step.text}"]
    details = []
    if step.location:
        details.append(f"miejsce: {step.location}")
    if step.npc:
        details.append(f"NPC: {step.npc}")
    if step.items:
        details.append("przedmioty: " + ", ".join(step.items))
    if details:
        lines.append("    " + " · ".join(details))
    label = _label("\n".join(lines))
    label.setContentsMargins(0, 4, 0, 4)
    return label
