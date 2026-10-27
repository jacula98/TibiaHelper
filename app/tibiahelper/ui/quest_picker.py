"""Questy wymagane np. do bossa: lista dla gracza (czerwona/zielona) i wybór w edytorze autora."""

from html import escape

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QSpinBox, QVBoxLayout, QWidget

from ..core.i18n import tr
from ..core.models import Quest, QuestRequirement
from ..core.progress import ProgressStore
from . import theme

QUEST_LINK_PREFIX = "quest:"
_STEP_ROLE = Qt.ItemDataRole.UserRole + 1


def requirements_html(requirements: list[QuestRequirement], quests: dict[str, Quest], progress: ProgressStore) -> str:
    """Każdy quest z linkiem: zielony z ✓, gdy gracz odhaczył potrzebne kroki, inaczej czerwony."""
    rows = []
    for requirement in requirements:
        quest = quests.get(requirement.quest)
        if quest is None:
            continue  # quest ukryty (szkic) albo usunięty: nie ma dokąd linkować
        done = progress.requirement_met(quest, requirement.step)
        color, mark = (theme.GOOD, "✓") if done else (theme.BAD, "✗")
        scope = tr("do kroku {n}", n=requirement.step) if requirement.step else tr("cały")
        rows.append(
            f'<span style="color: {color};">{mark}</span> '
            f'<a href="{QUEST_LINK_PREFIX}{escape(quest.id, quote=True)}" style="color: {color};">{escape(quest.name)}</a>'
            f' <span style="color: {theme.MUTED};">({escape(scope)})</span>'
        )
    return "<br>".join(rows)


class QuestPicker(QWidget):
    """Tryb autora: zaznaczasz questy, a dla zaznaczonego możesz podać krok (0 = cały quest)."""

    def __init__(self, quests: dict[str, str], chosen: list[dict], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        steps = {r["quest"]: r.get("step") for r in chosen}
        self._search = QLineEdit(placeholderText="Szukaj questa…", clearButtonEnabled=True)
        self._list = QListWidget()
        self._list.setMinimumHeight(160)
        # Zaznaczone questy na górze, żeby od razu było widać wymagania.
        for quest_id, name in sorted(quests.items(), key=lambda q: (q[0] not in steps, q[1].lower())):
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, quest_id)
            item.setData(_STEP_ROLE, steps.get(quest_id))
            item.setData(Qt.ItemDataRole.UserRole + 2, name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if quest_id in steps else Qt.CheckState.Unchecked)
            self._list.addItem(item)
            _update_text(item)
        self._step = QSpinBox(minimum=0, maximum=200, specialValueText="cały quest")
        self._step.setToolTip("Do którego kroku quest musi być zrobiony (0 = cały)")
        self._search.textChanged.connect(self._filter)
        self._list.currentItemChanged.connect(self._on_current)
        self._step.valueChanged.connect(self._on_step)

        step_row = QHBoxLayout()
        step_row.addWidget(QLabel("Zaznaczony quest wymagany do kroku:"))
        step_row.addWidget(self._step)
        step_row.addStretch(1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._search)
        layout.addWidget(self._list)
        layout.addLayout(step_row)

    def requirements(self) -> list[dict]:
        result = []
        for row in range(self._list.count()):
            item = self._list.item(row)
            if item.checkState() == Qt.CheckState.Checked:
                requirement = {"quest": item.data(Qt.ItemDataRole.UserRole)}
                if item.data(_STEP_ROLE):
                    requirement["step"] = item.data(_STEP_ROLE)
                result.append(requirement)
        return result

    def _filter(self, text: str) -> None:
        text = text.strip().lower()
        for row in range(self._list.count()):
            item = self._list.item(row)
            item.setHidden(text not in item.text().lower())

    def _on_current(self, item: QListWidgetItem | None) -> None:
        # blockSignals: samo pokazanie kroku wybranego questa nie ma go zmieniać.
        self._step.blockSignals(True)
        self._step.setValue((item.data(_STEP_ROLE) or 0) if item else 0)
        self._step.blockSignals(False)

    def _on_step(self, value: int) -> None:
        item = self._list.currentItem()
        if item is not None:
            item.setData(_STEP_ROLE, value or None)
            if value:
                item.setCheckState(Qt.CheckState.Checked)  # krok ma sens tylko przy wymaganym queście
            _update_text(item)


def _update_text(item: QListWidgetItem) -> None:
    step = item.data(_STEP_ROLE)
    name = item.data(Qt.ItemDataRole.UserRole + 2)
    item.setText(f"{name}  (do kroku {step})" if step else name)
