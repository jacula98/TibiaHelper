"""Strona z krokami jednego questa.

Kroki to karty. „Aktualny” krok (pierwszy nieodhaczony) ma złotą ramkę
i po odhaczeniu poprzedniego okno samo przewija się tak, żeby był na górze.
Zrobione kroki zostają wyżej, wyszarzone.
"""

from html import escape

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QPropertyAnimation,
    QSize,
    Qt,
    QTimer,
    QUrl,
    Signal,
)
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..core.issues import issue_url
from ..core.models import Quest, Step
from ..core.progress import ProgressStore
from .rich_text import parse_pin_link, step_html
from .theme import ASSETS_DIR, icon

SCROLL_MARGIN = 6  # odstęp aktualnego kroku od górnej krawędzi
SCROLL_MS = 250


class QuestView(QWidget):
    back_requested = Signal()
    # Wysyłany po każdej zmianie checkboxa, żeby lista odświeżyła licznik kroków.
    progress_changed = Signal()
    # Kliknięta pinezka: (wszystkie punkty kroku, kliknięty punkt).
    map_requested = Signal(object, object)

    def __init__(self, progress: ProgressStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._progress = progress
        self._quest: Quest | None = None
        self._step_rows: list[_StepRow] = []
        self._finished: QLabel | None = None
        self._tail: QWidget | None = None
        self._data_version = 0

        back = QPushButton("← Lista")
        back.clicked.connect(self.back_requested)

        self._counter = QLabel()
        self._counter.setObjectName("muted")
        reset = QPushButton("Resetuj")
        reset.setToolTip("Odznacz wszystkie kroki tego questa")
        reset.clicked.connect(self._reset)

        top = QHBoxLayout()
        top.addWidget(back)
        top.addStretch(1)
        top.addWidget(self._counter)
        top.addWidget(reset)

        self._scroll = QScrollArea(widgetResizable=True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.viewport().installEventFilter(self)
        # Animacja przewijania: płynny ruch zamiast skoku, łatwiej się nie zgubić.
        self._scroll_animation = QPropertyAnimation(self._scroll.verticalScrollBar(), b"value", self)
        self._scroll_animation.setDuration(SCROLL_MS)
        self._scroll_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        report = QPushButton(" Zgłoś błąd")
        report.setIcon(icon("github.svg"))
        report.setIconSize(QSize(16, 16))
        report.setToolTip("Otwiera zgłoszenie na GitHubie (potrzebne darmowe konto GitHub)")
        report.setCursor(Qt.CursorShape.PointingHandCursor)
        report.clicked.connect(self._report_issue)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(top)
        layout.addWidget(self._scroll, 1)
        layout.addWidget(report, 0, Qt.AlignmentFlag.AlignRight)

    def set_data_version(self, data_version: int) -> None:
        # Wersja danych trafia do zgłoszenia, żeby było wiadomo, którego pliku dotyczy błąd.
        self._data_version = data_version

    def show_quest(self, quest: Quest) -> None:
        self._quest = quest
        done = self._progress.done_steps(quest.id)
        self._step_rows = []

        # Przy każdym queście budujemy treść od nowa: prościej niż aktualizować stare widżety.
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 4, 4, 0)
        layout.setSpacing(8)

        title = _label(quest.name, "title")
        layout.addWidget(title)
        layout.addWidget(
            _label(f"Level {quest.min_level}+ · {'premium' if quest.premium else 'free'}", "muted")
        )

        if quest.status == "draft":
            layout.addWidget(_label("Szkic (draft): ten poradnik nie został jeszcze przejrzany.", "warning"))
        if quest.needs_review:
            layout.addWidget(_label("Strona na TibiaWiki zmieniła się. Poradnik może być nieaktualny.", "warning"))

        if quest.required_items:
            layout.addWidget(_label("POTRZEBNE", "sectionTitle"))
            layout.addWidget(_label(", ".join(quest.required_items)))

        layout.addWidget(_label("KROKI", "sectionTitle"))
        for index, step in enumerate(quest.steps):
            row = _StepRow(index, step, checked=index in done)
            row.toggled.connect(self._on_step_toggled)
            row.map_requested.connect(self.map_requested)
            self._step_rows.append(row)
            layout.addWidget(row)

        self._finished = _label("✓ Quest ukończony!", "title")
        layout.addWidget(self._finished)

        if quest.rewards:
            layout.addWidget(_label("NAGRODY", "sectionTitle"))
            layout.addWidget(_label(", ".join(quest.rewards)))

        # Link do źródła jest wymagany przez licencję CC BY-SA.
        source = QLabel(
            f'Źródło: <a href="{escape(quest.source_url, quote=True)}">TibiaWiki</a>'
            " (CC BY-SA 4.0)"
        )
        source.setObjectName("muted")
        source.setOpenExternalLinks(True)
        layout.addWidget(source)

        # Pusty "ogon" na dole, żeby nawet ostatni krok dało się przewinąć na samą górę.
        self._tail = QWidget()
        self._tail.setFixedHeight(self._scroll.viewport().height())
        layout.addWidget(self._tail)
        layout.addStretch(1)

        self._scroll_animation.stop()
        self._scroll.setWidget(content)
        self._update_states()
        # Pozycje kart są znane dopiero po ułożeniu okna, więc przewijamy w następnym obiegu pętli Qt.
        QTimer.singleShot(0, lambda: self._scroll_to_current(animated=False))

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 (nazwa z Qt)
        if event.type() == QEvent.Type.Resize and self._tail is not None:
            self._tail.setFixedHeight(self._scroll.viewport().height())
        return super().eventFilter(watched, event)

    def current_step(self) -> int | None:
        """Indeks pierwszego nieodhaczonego kroku albo None, gdy wszystko zrobione."""
        return next((row.index for row in self._step_rows if not row.is_checked()), None)

    def _on_step_toggled(self, index: int, checked: bool) -> None:
        if self._quest is None:
            return
        self._progress.set_step(self._quest.id, index, checked)
        self._update_states()
        self._scroll_to_current(animated=True)
        self.progress_changed.emit()

    def _reset(self) -> None:
        if self._quest is None:
            return
        self._progress.reset_quest(self._quest.id)
        for row in self._step_rows:
            row.set_checked(False)
        self._update_states()
        self._scroll_to_current(animated=True)
        self.progress_changed.emit()

    def _update_states(self) -> None:
        current = self.current_step()
        for row in self._step_rows:
            if row.is_checked():
                row.set_state("done")
            else:
                row.set_state("current" if row.index == current else "todo")
        done = sum(row.is_checked() for row in self._step_rows)
        self._counter.setText(f"{done}/{len(self._step_rows)}")
        if self._finished is not None:
            self._finished.setVisible(bool(self._step_rows) and current is None)

    def _scroll_to_current(self, animated: bool) -> None:
        current = self.current_step()
        if current is None:
            target = self._finished.y() - SCROLL_MARGIN if self._finished else 0
        elif current == 0:
            # Nic jeszcze nie zrobione: pokazujemy też nagłówek (potrzebne przedmioty itd.).
            target = 0
        else:
            target = self._step_rows[current].y() - SCROLL_MARGIN
        bar = self._scroll.verticalScrollBar()
        target = max(bar.minimum(), min(bar.maximum(), target))
        self._scroll_animation.stop()
        if animated:
            self._scroll_animation.setStartValue(bar.value())
            self._scroll_animation.setEndValue(target)
            self._scroll_animation.start()
        else:
            bar.setValue(target)

    def _report_issue(self) -> None:
        if self._quest is not None:
            QDesktopServices.openUrl(QUrl(issue_url(self._quest, self._data_version)))


def _label(text: str, name: str = "") -> QLabel:
    # PlainText: tekst z pliku danych nie jest interpretowany jako HTML.
    label = QLabel(text, wordWrap=True, textFormat=Qt.TextFormat.PlainText)
    if name:
        label.setObjectName(name)
    return label


class _StepRow(QFrame):
    """Jeden krok jako karta: checkbox + zawijany opis.

    Sam QCheckBox nie zawija długiego tekstu, dlatego tekst jest w osobnym
    QLabel, a kliknięcie w dowolne miejsce karty też przełącza checkbox.
    Wyjątek: kliknięcie pinezki otwiera mapę i nie zmienia postępu.
    """

    toggled = Signal(int, bool)
    map_requested = Signal(object, object)

    def __init__(self, index: int, step: Step, checked: bool) -> None:
        super().__init__()
        self.setObjectName("step")
        self.index = index
        self._hovered_link = ""
        self._box = QCheckBox()
        self._box.setChecked(checked)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(self._text_label(index + 1, step))
        details = _step_details(step)
        if details:
            text.addWidget(_label(details, "muted"))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addWidget(self._box, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(text, 1)

        self._box.toggled.connect(lambda value: self.toggled.emit(self.index, value))

    def _text_label(self, number: int, step: Step) -> QLabel:
        if not step.markers:
            return _label(f"{number}. {step.text}")
        self._step = step
        label = QLabel(wordWrap=True, textFormat=Qt.TextFormat.RichText)
        # Pinezka ma wysokość linii tekstu, żeby nie rozpychała wiersza.
        size = label.fontMetrics().height() - 2
        pin = (ASSETS_DIR / "pin.svg").as_uri()
        label.setText(step_html(number, step, f'<img src="{pin}" height="{size}" width="{size * 3 // 4}">'))
        label.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
        label.linkActivated.connect(self._on_link)
        # Zapamiętujemy, czy kursor jest nad pinezką: wtedy klik nie odhacza kroku.
        label.linkHovered.connect(lambda link: setattr(self, "_hovered_link", link))
        return label

    def _on_link(self, link: str) -> None:
        index = parse_pin_link(link)
        if index is not None and index < len(self._step.markers):
            self.map_requested.emit(list(self._step.markers), self._step.markers[index])

    def is_checked(self) -> bool:
        return self._box.isChecked()

    def set_checked(self, checked: bool) -> None:
        # blockSignals: zmiana z kodu (reset) nie powinna drugi raz zapisywać postępu.
        self._box.blockSignals(True)
        self._box.setChecked(checked)
        self._box.blockSignals(False)

    def set_state(self, state: str) -> None:
        """done / current / todo: wygląd karty ustawia theme.py na podstawie tej właściwości."""
        if self.property("state") == state:
            return
        self.setProperty("state", state)
        # Qt nie przelicza stylu sam po zmianie właściwości, trzeba go "odświeżyć".
        for widget in (self, *self.findChildren(QWidget)):
            widget.style().unpolish(widget)
            widget.style().polish(widget)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (nazwa z Qt)
        # Tylko lewy przycisk: prawy/środkowy nie powinien zmieniać postępu.
        if event.button() == Qt.MouseButton.LeftButton and not self._hovered_link:
            self._box.toggle()


def _step_details(step: Step) -> str:
    details = []
    if step.location:
        # Bez ikony pinezki: ta jest tylko w tekście i oznacza klikalną mapę.
        details.append(f"miejsce: {step.location}")
    if step.npc:
        details.append(f"NPC: {step.npc}")
    if step.items:
        details.append("przedmioty: " + ", ".join(step.items))
    return " · ".join(details)
