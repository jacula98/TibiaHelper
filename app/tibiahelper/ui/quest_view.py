"""Strona z krokami jednego questa."""

from html import escape

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..core.models import Quest, Step
from ..core.progress import ProgressStore


class QuestView(QWidget):
    back_requested = Signal()
    # Wysyłany po każdej zmianie checkboxa, żeby lista odświeżyła licznik kroków.
    progress_changed = Signal()

    def __init__(self, progress: ProgressStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._progress = progress
        self._quest: Quest | None = None
        self._step_rows: list[_StepRow] = []

        back = QPushButton("← Lista questów")
        back.clicked.connect(self.back_requested)

        self._counter = QLabel()
        reset = QPushButton("Resetuj postęp")
        reset.clicked.connect(self._reset)

        top = QHBoxLayout()
        top.addWidget(back)
        top.addStretch(1)
        top.addWidget(self._counter)
        top.addWidget(reset)

        self._scroll = QScrollArea(widgetResizable=True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self._scroll, 1)

    def show_quest(self, quest: Quest) -> None:
        self._quest = quest
        done = self._progress.done_steps(quest.id)
        self._step_rows = []

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

        for index, step in enumerate(quest.steps):
            row = _StepRow(index, step, checked=index in done)
            row.toggled.connect(self._on_step_toggled)
            self._step_rows.append(row)
            layout.addWidget(row)

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
        self._update_counter()

    def _on_step_toggled(self, index: int, checked: bool) -> None:
        if self._quest is None:
            return
        self._progress.set_step(self._quest.id, index, checked)
        self._update_counter()
        self.progress_changed.emit()

    def _reset(self) -> None:
        if self._quest is None:
            return
        self._progress.reset_quest(self._quest.id)
        for row in self._step_rows:
            row.set_checked(False)
        self._update_counter()
        self.progress_changed.emit()

    def _update_counter(self) -> None:
        done = sum(row.is_checked() for row in self._step_rows)
        self._counter.setText(f"{done}/{len(self._step_rows)}")


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


class _StepRow(QWidget):
    """Jeden krok: checkbox + zawijany opis.

    Sam QCheckBox nie zawija długiego tekstu, dlatego tekst jest w osobnym
    QLabel, a kliknięcie w niego też przełącza checkbox.
    """

    toggled = Signal(int, bool)

    def __init__(self, index: int, step: Step, checked: bool) -> None:
        super().__init__()
        self._index = index
        self._box = QCheckBox()
        self._box.setChecked(checked)
        self._text = _label(_step_text(index + 1, step))
        self._text.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.addWidget(self._box, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self._text, 1)

        self._box.toggled.connect(self._on_toggled)
        self._apply_style()

    def is_checked(self) -> bool:
        return self._box.isChecked()

    def set_checked(self, checked: bool) -> None:
        # blockSignals: zmiana z kodu (reset) nie powinna drugi raz zapisywać postępu.
        self._box.blockSignals(True)
        self._box.setChecked(checked)
        self._box.blockSignals(False)
        self._apply_style()

    def mousePressEvent(self, event) -> None:  # noqa: N802 (nazwa z Qt)
        # Tylko lewy przycisk: prawy/środkowy nie powinien zmieniać postępu.
        if event.button() == Qt.MouseButton.LeftButton:
            self._box.toggle()

    def _on_toggled(self, checked: bool) -> None:
        self._apply_style()
        self.toggled.emit(self._index, checked)

    def _apply_style(self) -> None:
        # Zrobione kroki wyszarzamy, żeby wzrok od razu trafiał na następny.
        self._text.setStyleSheet("color: gray;" if self._box.isChecked() else "")


def _step_text(number: int, step: Step) -> str:
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
    return "\n".join(lines)
