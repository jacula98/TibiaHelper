"""Strona z krokami jednego questa.

Kroki to karty. „Aktualny” krok (pierwszy nieodhaczony) ma złotą ramkę
i po odhaczeniu poprzedniego okno samo przewija się tak, żeby był na górze.
Zrobione kroki zostają wyżej, wyszarzone.
"""

import threading
from html import escape
from pathlib import Path

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
from PySide6.QtGui import QCursor, QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from ..core.issues import issue_url
from ..core.models import Monster, Quest, Step
from ..core.monsters import download_missing, sprite_path
from ..core.progress import ProgressStore
from .map_window import MapPanel
from .rich_text import monster_tooltip, parse_monster_link, parse_pin_link, step_html
from .sprites import display_sprite
from .theme import ASSETS_DIR, icon

SCROLL_MARGIN = 6  # odstęp aktualnego kroku od górnej krawędzi
SCROLL_MS = 250
TILE_SPRITE = 48  # obrazek w sekcji „Potwory”
TOOLTIP_SPRITE = 64  # obrazek w dymku (oryginalny rozmiar z wiki)
TILE_COLUMNS = 4


class _SpriteLoader(QObject):
    """Pobiera obrazki potworów w tle; sygnał wraca do wątku okna (jak _FloorLoader mapy)."""

    loaded = Signal(str)  # id questa, dla którego pobierano


def _img(path: Path | None, size: int) -> str:
    """Znacznik <img> obrazka potwora albo łapka, gdy obrazek jeszcze się nie pobrał."""
    if path is None:
        return "🐾"
    # middle: obrazek wyższy niż linia stoi na środku tekstu, a nie wystaje nad nim.
    return f'<img src="{path.as_uri()}" width="{size}" height="{size}" style="vertical-align: middle">'


class QuestView(QWidget):
    back_requested = Signal()
    # Wysyłany po każdej zmianie checkboxa, żeby lista odświeżyła licznik kroków.
    progress_changed = Signal()
    # Tryb autora: przycisk „Edytuj” przy queście.
    edit_requested = Signal(object)
    # Kliknięty potwór (w tekście kroku albo w sekcji „Potwory”): otwiera jego stronę.
    monster_requested = Signal(object)

    def __init__(
        self,
        progress: ProgressStore,
        maps_dir: Path,
        sprites_dir: Path,
        editable: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._progress = progress
        self._sprites_dir = sprites_dir
        self._monsters: dict[str, Monster] = {}
        self._tiles: list[_MonsterTile] = []
        self._sprite_loader = _SpriteLoader(self)
        self._sprite_loader.loaded.connect(self._on_sprites_loaded)
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
        if editable:
            edit = QPushButton("✎ Edytuj")
            edit.setObjectName("primary")
            edit.clicked.connect(self._request_edit)
            top.addWidget(edit)

        self._scroll = QScrollArea(widgetResizable=True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        # Treść zawsze mieści się w szerokości okna (tekst się zawija), więc bez paska w poziomie.
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
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

        # Mapa wysuwa się na dole, pod krokami: widać naraz tekst kroku i miejsce.
        self._map = MapPanel(maps_dir, closable=True)
        self._map.close_requested.connect(self._hide_map)
        self._map.setMaximumHeight(0)
        self._map.hide()
        self._map_open = False
        self._map_row: _StepRow | None = None
        self._map_animation = QPropertyAnimation(self._map, b"maximumHeight", self)
        self._map_animation.setDuration(SCROLL_MS)
        self._map_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._map_animation.finished.connect(self._on_map_animation_done)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(top)
        layout.addWidget(self._scroll, 1)
        layout.addWidget(self._map)
        layout.addWidget(report, 0, Qt.AlignmentFlag.AlignRight)

    def set_data_version(self, data_version: int) -> None:
        # Wersja danych trafia do zgłoszenia, żeby było wiadomo, którego pliku dotyczy błąd.
        self._data_version = data_version

    def set_monsters(self, monsters: dict[str, Monster]) -> None:
        self._monsters = monsters

    def show_quest(self, quest: Quest) -> None:
        self._quest = quest
        self._hide_map(animated=False)
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

        self._tiles = []
        counts = [(self._monsters[i], n) for i, n in quest.monster_counts() if i in self._monsters]
        if counts:
            layout.addWidget(_label("POTWORY", "sectionTitle"))
            grid = QGridLayout()
            grid.setSpacing(4)
            # Równe kolumny: jeden potwór zajmuje 1/4 szerokości, a nie cały wiersz.
            for column in range(TILE_COLUMNS):
                grid.setColumnStretch(column, 1)
            for position, (monster, count) in enumerate(counts):
                tile = _MonsterTile(monster, count, self._sprites_dir)
                tile.clicked.connect(self.monster_requested)
                self._tiles.append(tile)
                grid.addWidget(tile, position // TILE_COLUMNS, position % TILE_COLUMNS)
            layout.addLayout(grid)

        layout.addWidget(_label("KROKI", "sectionTitle"))
        for index, step in enumerate(quest.steps):
            row = _StepRow(index, step, index in done, self._monsters, self._sprites_dir)
            row.toggled.connect(self._on_step_toggled)
            # row=row: lambda zapamiętuje swój krok (inaczej wszystkie wskazywałyby ostatni).
            row.map_requested.connect(lambda points, focus, row=row: self._show_map(points, focus, row))
            row.monster_requested.connect(self.monster_requested)
            self._step_rows.append(row)
            layout.addWidget(row)

        self._finished = _label("✓ Quest ukończony!", "title")
        layout.addWidget(self._finished)

        if quest.rewards:
            layout.addWidget(_label("NAGRODY", "sectionTitle"))
            layout.addWidget(_label(", ".join(quest.rewards)))

        # Link do źródła jest wymagany przez licencję CC BY-SA.
        credits = " (CC BY-SA 4.0)"
        if counts:
            credits += " · obrazki potworów © CipSoft"
        source = QLabel(
            f'Źródło: <a href="{escape(quest.source_url, quote=True)}">TibiaWiki</a>{credits}'
        )
        source.setObjectName("muted")
        source.setWordWrap(True)
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
        self._load_sprites(quest)

    # --- obrazki potworów -----------------------------------------------------

    def _load_sprites(self, quest: Quest) -> None:
        """Brakujące obrazki pobieramy w tle; do tego czasu w tekście jest łapka 🐾."""
        ids = {m.id for step in quest.steps for m in step.monsters}
        missing = [
            self._monsters[i]
            for i in sorted(ids)
            if i in self._monsters and sprite_path(self._sprites_dir, i) is None
        ]
        if not missing:
            return

        def run() -> None:
            if download_missing(self._sprites_dir, missing):
                self._sprite_loader.loaded.emit(quest.id)

        # daemon=True: zamknięcie okna nie czeka na pobieranie.
        threading.Thread(target=run, daemon=True, name="sprites").start()

    def _on_sprites_loaded(self, quest_id: str) -> None:
        # Gracz mógł w międzyczasie otworzyć inny quest: wtedy nic nie odświeżamy.
        if self._quest is None or self._quest.id != quest_id:
            return
        for row in self._step_rows:
            row.refresh_text()
        for tile in self._tiles:
            tile.refresh()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 (nazwa z Qt)
        if event.type() == QEvent.Type.Resize and self._tail is not None:
            self._tail.setFixedHeight(self._scroll.viewport().height())
        return super().eventFilter(watched, event)

    # --- mapa na dole ----------------------------------------------------------

    def _map_height(self) -> int:
        # Mniej więcej 45% wysokości: kroki dalej są widoczne nad mapą.
        return max(200, int(self.height() * 0.45))

    def _show_map(self, points: list, focus, row: "_StepRow") -> None:
        """Klik w pinezkę: wysuwa mapę albo tylko przełącza ją na inne miejsce."""
        self._map.show_points(points, focus)
        self._map_row = row
        if self._map_open:
            return
        self._map_open = True
        self._map.show()
        self._animate_map(self._map_height())

    def _hide_map(self, animated: bool = True) -> None:
        if not self._map_open:
            return
        self._map_open = False
        if animated:
            self._animate_map(0)
        else:
            self._map_animation.stop()
            self._map.setMaximumHeight(0)
            self._map.hide()

    def _animate_map(self, height: int) -> None:
        self._map_animation.stop()
        self._map_animation.setStartValue(self._map.maximumHeight())
        self._map_animation.setEndValue(height)
        self._map_animation.start()

    def _on_map_animation_done(self) -> None:
        # Po schowaniu ukrywamy widżet całkiem, żeby nie zajmował miejsca w układzie.
        if not self._map_open:
            self._map.hide()
            return
        # Po wysunięciu: mapa na punkcie, a krok z klikniętą pinezką na górze nad mapą.
        self._map.recenter()
        if self._map_row is not None:
            self._scroll_to(self._map_row.y() - SCROLL_MARGIN, animated=True)

    def resizeEvent(self, event) -> None:  # noqa: N802 (nazwa z Qt)
        super().resizeEvent(event)
        if self._map_open and self._map_animation.state() != QPropertyAnimation.State.Running:
            self._map.setMaximumHeight(self._map_height())

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
        self._scroll_to(target, animated)

    def _scroll_to(self, target: int, animated: bool) -> None:
        bar = self._scroll.verticalScrollBar()
        target = max(bar.minimum(), min(bar.maximum(), target))
        self._scroll_animation.stop()
        if animated:
            self._scroll_animation.setStartValue(bar.value())
            self._scroll_animation.setEndValue(target)
            self._scroll_animation.start()
        else:
            bar.setValue(target)

    def _request_edit(self) -> None:
        if self._quest is not None:
            self.edit_requested.emit(self._quest)

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
    monster_requested = Signal(object)

    def __init__(
        self, index: int, step: Step, checked: bool, monsters: dict[str, Monster], sprites_dir: Path
    ) -> None:
        super().__init__()
        self.setObjectName("step")
        self.index = index
        self._step = step
        self._monsters = monsters
        self._sprites_dir = sprites_dir
        self._rich: QLabel | None = None
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
        if not step.markers and not step.monsters:
            return _label(f"{number}. {step.text}")
        label = QLabel(wordWrap=True, textFormat=Qt.TextFormat.RichText)
        self._rich = label
        self.refresh_text()
        label.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
        label.linkActivated.connect(self._on_link)
        label.linkHovered.connect(self._on_hover)
        return label

    def refresh_text(self) -> None:
        """Buduje HTML kroku od nowa (np. gdy obrazki potworów się pobrały)."""
        if self._rich is None:
            return
        # Pinezka ma wysokość linii tekstu, żeby nie rozpychała wiersza.
        line = self._rich.fontMetrics().height()
        size = line - 2
        pin = (ASSETS_DIR / "pin.svg").as_uri()
        pin_img = f'<img src="{pin}" height="{size}" width="{size * 3 // 4}">'
        # Potwór jest większy (2 linie): w wysokości linii obrazek 64 px byłby nieczytelny.
        self._rich.setText(
            step_html(self.index + 1, self._step, pin_img, lambda i: _img(self._sprite(i), line * 2))
        )

    def _sprite(self, index: int) -> Path | None:
        return display_sprite(self._sprites_dir, self._step.monsters[index].id)

    def _on_hover(self, link: str) -> None:
        # Zapamiętujemy, czy kursor jest nad pinezką/potworem: wtedy klik nie odhacza kroku.
        self._hovered_link = link
        index = parse_monster_link(link)
        if index is None or index >= len(self._step.monsters):
            QToolTip.hideText()
            return
        monster = self._monsters.get(self._step.monsters[index].id)
        if monster is not None:
            text = monster_tooltip(monster, _img(self._sprite(index), TOOLTIP_SPRITE))
            QToolTip.showText(QCursor.pos(), text, self._rich)

    def _on_link(self, link: str) -> None:
        index = parse_pin_link(link)
        if index is not None and index < len(self._step.markers):
            self.map_requested.emit(list(self._step.markers), self._step.markers[index])
        index = parse_monster_link(link)
        if index is not None and index < len(self._step.monsters):
            monster = self._monsters.get(self._step.monsters[index].id)
            if monster is not None:
                QToolTip.hideText()
                self.monster_requested.emit(monster)

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


class _MonsterTile(QLabel):
    """Kafelek w sekcji „Potwory”: obrazek, a pod nim „2x Skeleton”. Dymek jak w tekście kroku.

    Kliknięcie otwiera stronę potwora w zakładce „Potwory”.
    """

    clicked = Signal(object)

    def __init__(self, monster: Monster, count: int | None, sprites_dir: Path) -> None:
        super().__init__(textFormat=Qt.TextFormat.RichText, alignment=Qt.AlignmentFlag.AlignCenter)
        self.setObjectName("monsterTile")
        self.setWordWrap(True)
        # Ignored: kafelki dzielą się szerokością okna, zamiast ją rozpychać długą nazwą.
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._monster = monster
        self._count = count
        self._sprites_dir = sprites_dir
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh()

    def mousePressEvent(self, event) -> None:  # noqa: N802 (nazwa z Qt)
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._monster)

    def refresh(self) -> None:
        path = display_sprite(self._sprites_dir, self._monster.id)
        name = escape(self._monster.name)
        caption = f"{self._count}x {name}" if self._count else name
        self.setText(f"{_img(path, TILE_SPRITE)}<br>{caption}")
        self.setToolTip(monster_tooltip(self._monster, _img(path, TOOLTIP_SPRITE)))


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
