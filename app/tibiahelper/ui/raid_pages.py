"""Narzędzie „Raidy i world change”: wklejony komunikat z gry -> co się dzieje i timer fal (logika w core/raids.py)."""

from datetime import datetime
from html import escape

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..core.i18n import tr
from ..core.models import WIKI_URL_PREFIX
from ..core.raids import ChangeMatch, RaidData, RaidMatch, format_countdown, next_wave, recognize
from . import theme
from .qol_pages import _top_bar

MAX_CREATURES = 12  # dłuższa lista potworów nie mieści się w wąskim oknie


def _source_link(url: str) -> QLabel | None:
    """Link „TibiaWiki ↗” do strony źródłowej (CC BY-SA wymaga linku przy danych). Tylko adresy TibiaWiki."""
    if not url.startswith(WIKI_URL_PREFIX):
        return None
    link = QLabel(f"<a href='{escape(url, quote=True)}'>TibiaWiki ↗</a>")
    link.setOpenExternalLinks(True)
    return link


def _label(text: str, muted: bool = False) -> QLabel:
    label = QLabel(text, wordWrap=True)
    label.setTextFormat(Qt.TextFormat.RichText)
    if muted:
        label.setObjectName("muted")
    return label


class _RaidCard(QFrame):
    """Raid z listą fal. Godziny i odliczanie odświeża tick() co sekundę."""

    def __init__(self, match: RaidMatch) -> None:
        super().__init__()
        self.setObjectName("offer")
        self._match = match
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 8)
        layout.setSpacing(3)
        raid = match.raid
        place = " · ".join(escape(p) for p in (raid.area, raid.subarea) if p)
        layout.addWidget(_label(f"⚔ <b>{escape(raid.name)}</b>"))
        if place:
            layout.addWidget(_label(place, muted=True))
        if raid.historic:
            layout.addWidget(_label(tr("Raid z eventu: zdarza się tylko w czasie wydarzeń."), muted=True))
        if not match.from_clock:
            layout.addWidget(_label(tr("W tekście nie ma godziny, więc liczę od teraz."), muted=True))
        self._waves = [_label("") for _ in raid.waves]
        for label in self._waves:
            layout.addWidget(label)
        if raid.creatures:
            names = ", ".join(raid.creatures[:MAX_CREATURES]) + ("…" if len(raid.creatures) > MAX_CREATURES else "")
            layout.addWidget(_label(escape(tr("Potwory: {names}", names=names)), muted=True))
        if link := _source_link(raid.source_url):
            layout.addWidget(link)
        now = datetime.now()
        self._upcoming = next_wave(match, now)
        self.tick(now)

    def tick(self, now: datetime) -> bool:
        """Odświeża fale. Zwraca True, jeśli od ostatniego razu przyszła nowa fala (sygnał dźwiękowy)."""
        upcoming = next_wave(self._match, now)
        for index, (label, wave) in enumerate(zip(self._waves, self._match.raid.waves, strict=True)):
            moment = self._match.wave_time(index)
            message = escape(wave.message) if wave.message else f"<i>{escape(tr('fala bez komunikatu'))}</i>"
            clock = moment.strftime("%H:%M:%S")
            if moment <= now:
                label.setText(f"<span style='color: {theme.MUTED};'>✓ {clock} · {message}</span>")
            else:
                left = escape(tr("za {time}", time=format_countdown((moment - now).total_seconds())))
                line = f"{clock} ({left}) · {message}"
                label.setText(f"<b style='color: {theme.ACCENT};'>▶ {line}</b>" if index == upcoming else line)
        arrived = upcoming != self._upcoming
        self._upcoming = upcoming
        return arrived


def _change_card(match: ChangeMatch) -> QFrame:
    frame = QFrame()
    frame.setObjectName("offer")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(10, 6, 10, 8)
    layout.setSpacing(3)
    change = match.change
    kind = tr("Mini world change") if change.kind == "mini" else tr("World change")
    layout.addWidget(_label(f"🌍 <b>{escape(change.name)}</b> · {escape(kind)}"))
    if match.message is None:
        layout.addWidget(_label(tr("Rozpoznane po nazwie (ten world change nie ma komunikatu w grze)."), muted=True))
    elif match.message.note:
        layout.addWidget(_label(escape(match.message.note), muted=True))
    if change.description:
        layout.addWidget(_label(f"<i>{escape(change.description)}</i>"))
    for text, value in (
        (tr("Gdzie:"), change.location),
        (tr("Potwory:"), change.dangers),
        (tr("Co daje:"), change.reward),
    ):
        if value:
            layout.addWidget(_label(f"<b>{escape(text)}</b> {escape(value)}"))
    if link := _source_link(change.source_url):
        layout.addWidget(link)
    return frame


class RaidHelperPage(QWidget):
    back_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._data = RaidData()
        self._cards: list[_RaidCard] = []
        title = QLabel(tr("Raidy i world change"))
        title.setObjectName("title")
        info = QLabel(
            tr(
                "Skopiuj komunikat z gry razem z godziną (np. z Server Log albo wiadomość Towncryera) "
                "i wklej tutaj. Program pokaże, co się dzieje, a przy raidzie odliczy czas do kolejnych fal."
            ),
            wordWrap=True,
        )
        info.setObjectName("muted")

        self._input = QPlainTextEdit(placeholderText=tr("np. 10:31 Rat plague in Thais!"))
        self._input.setFixedHeight(90)
        self._input.textChanged.connect(self._update)
        paste = QPushButton(tr("Wklej ze schowka"))
        paste.setObjectName("primary")
        paste.setCursor(Qt.CursorShape.PointingHandCursor)
        paste.clicked.connect(lambda: self._input.setPlainText(QGuiApplication.clipboard().text()))
        clear = QPushButton(tr("Wyczyść"))
        clear.clicked.connect(self._input.clear)
        self._sound = QCheckBox(tr("Dźwięk przy fali"))
        self._sound.setChecked(True)
        buttons = QHBoxLayout()
        buttons.addWidget(paste)
        buttons.addWidget(clear)
        buttons.addStretch(1)

        self._status = _label("", muted=True)
        self._results = QVBoxLayout()
        self._results.setSpacing(6)
        box = QWidget()
        box_layout = QVBoxLayout(box)
        box_layout.setContentsMargins(0, 0, 0, 0)
        box_layout.addLayout(self._results)
        box_layout.addStretch(1)
        scroll = QScrollArea(widgetResizable=True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(box)
        source = QLabel(tr("Komunikaty i czasy fal z TibiaWiki (CC BY-SA). Czas liczony od pierwszego komunikatu raidu."),
                        wordWrap=True)
        source.setObjectName("muted")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addLayout(_top_bar(tr("← Narzędzia"), self.back_requested))
        layout.addWidget(title)
        layout.addWidget(info)
        layout.addWidget(self._input)
        layout.addLayout(buttons)
        # W osobnej linii: obok przycisków nie mieści się w wąskim oknie.
        layout.addWidget(self._sound)
        layout.addWidget(self._status)
        layout.addWidget(scroll, 1)
        layout.addWidget(source)

        # Odliczanie co sekundę. Zegar chodzi tylko, gdy jest jakiś raid (bez raidu nie ma czego liczyć).
        self._timer = QTimer(self, interval=1000)
        self._timer.timeout.connect(self._tick)
        self._update()

    def set_data(self, data: RaidData) -> None:
        self._data = data
        self._update()

    def _update(self) -> None:
        self._timer.stop()
        self._cards = []
        while self._results.count():
            widget = self._results.takeAt(0).widget()
            if widget is not None:
                # hide() od razu: deleteLater() usuwa widżet dopiero w pętli zdarzeń, a do tego czasu byłby widoczny.
                widget.hide()
                widget.deleteLater()
        text = self._input.toPlainText()
        if not text.strip():
            self._status.setText("")
            return
        found = recognize(text, self._data)
        if not found.raids and not found.changes:
            self._status.setText(
                escape(tr("Nie rozpoznaję tej wiadomości. Wklej cały komunikat z gry, po angielsku, tak jak w kliencie."))
            )
            return
        self._status.setText(
            escape(tr("Rozpoznane: raidy {raids}, world change {changes}.", raids=len(found.raids),
                      changes=len(found.changes)))
        )
        for match in found.raids:
            card = _RaidCard(match)
            self._cards.append(card)
            self._results.addWidget(card)
        for change in found.changes:
            self._results.addWidget(_change_card(change))
        if self._cards:
            self._timer.start()

    def _tick(self) -> None:
        now = datetime.now()
        arrived = [card.tick(now) for card in self._cards]
        if any(arrived) and self._sound.isChecked() and self.isVisible():
            QApplication.beep()
