"""Strona z krokami jednego questa.

Kroki to karty. „Aktualny” krok (pierwszy nieodhaczony) ma złotą ramkę
i po odhaczeniu poprzedniego okno samo przewija się tak, żeby był na górze.
Zrobione kroki zostają wyżej, wyszarzone.
"""

import threading
from collections.abc import Callable
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

from ..core.i18n import tr
from ..core.issues import issue_url
from ..core.models import MapPoint, Monster, Npc, Quest, Step
from ..core.monsters import download_items, download_missing, image_path, item_key, sprite_path
from ..core.progress import ProgressStore
from .map_window import KIND_COLORS, KIND_NAMES, MapPanel
from .monster_widgets import AnimatedSprite
from .rich_text import monster_tooltip, parse_monster_link, parse_pin_link, step_html
from .sprites import display_sprite
from .theme import icon, report_button

SCROLL_MARGIN = 6  # odstęp aktualnego kroku od górnej krawędzi
SCROLL_MS = 250
TILE_SPRITE = 48  # obrazek w sekcji „Potwory”
TOOLTIP_SPRITE = 64  # obrazek w dymku (oryginalny rozmiar z wiki)
TILE_COLUMNS = 4
MARKER_TILE_WIDTH = 58  # kafelek pinezki obok tekstu kroku
MARKER_TILE_HEIGHT = 64
MARKER_SPRITE = 36


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
        npcs_dir: Path,
        editable: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._progress = progress
        self._sprites_dir = sprites_dir
        self._npcs_dir = npcs_dir
        self._npcs: dict[str, Npc] = {}
        self._monsters: dict[str, Monster] = {}
        self._tiles: list[_MonsterTile] = []
        self._sprite_loader = _SpriteLoader(self)
        self._sprite_loader.loaded.connect(self._on_sprites_loaded)
        self._quest: Quest | None = None
        self._step_rows: list[_StepRow] = []
        self._finished: QLabel | None = None
        self._tail: QWidget | None = None
        self._data_version = 0

        back = QPushButton(tr("← Lista"))
        back.clicked.connect(self.back_requested)

        self._counter = QLabel()
        self._counter.setObjectName("muted")
        reset = QPushButton(tr("Resetuj"))
        reset.setToolTip(tr("Odznacz wszystkie kroki tego questa"))
        reset.clicked.connect(self._reset)

        top = QHBoxLayout()
        top.addWidget(back)
        top.addStretch(1)
        top.addWidget(self._counter)
        top.addWidget(reset)
        if editable:
            edit = QPushButton("✎ " + tr("Edytuj"))
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

        report = report_button()
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

    def set_npcs(self, npcs: dict[str, Npc]) -> None:
        self._npcs = npcs

    def _npc_url(self, name: str) -> str | None:
        npc = self._npcs.get(name.lower())
        return npc.image_url if npc else None

    def _npc_image(self, name: str) -> Path | None:
        return image_path(self._npcs_dir, item_key(name)) if self._npc_url(name) else None

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
            layout.addWidget(_label(tr("Szkic (draft): ten poradnik nie został jeszcze przejrzany."), "warning"))
        if quest.needs_review:
            layout.addWidget(
                _label(tr("Strona na TibiaWiki zmieniła się. Poradnik może być nieaktualny."), "warning")
            )

        if quest.required_items:
            layout.addWidget(_label(tr("POTRZEBNE"), "sectionTitle"))
            layout.addWidget(_label(", ".join(quest.required_items)))

        self._tiles = []
        counts = [(self._monsters[i], n) for i, n in quest.monster_counts() if i in self._monsters]
        if counts:
            layout.addWidget(_label(tr("POTWORY"), "sectionTitle"))
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

        layout.addWidget(_label(tr("KROKI"), "sectionTitle"))
        for index, step in enumerate(quest.steps):
            row = _StepRow(index, step, index in done, self._monsters, self._sprites_dir, self._npc_image)
            row.toggled.connect(self._on_step_toggled)
            # row=row: lambda zapamiętuje swój krok (inaczej wszystkie wskazywałyby ostatni).
            row.map_requested.connect(lambda points, focus, row=row: self._show_map(points, focus, row))
            row.monster_requested.connect(self.monster_requested)
            self._step_rows.append(row)
            layout.addWidget(row)

        self._finished = _label("✓ " + tr("Quest ukończony!"), "title")
        layout.addWidget(self._finished)

        if quest.rewards:
            layout.addWidget(_label(tr("NAGRODY"), "sectionTitle"))
            layout.addWidget(_label(", ".join(quest.rewards)))

        # Link do źródła jest wymagany przez licencję CC BY-SA.
        credits = " (CC BY-SA 4.0)"
        if counts:
            credits += " · " + tr("obrazki potworów © CipSoft")
        source = QLabel(
            escape(tr("Źródło:")) + f' <a href="{escape(quest.source_url, quote=True)}">TibiaWiki</a>{escape(credits)}'
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
        npcs = {
            marker.label: self._npc_url(marker.label)
            for step in quest.steps
            for marker in step.markers
            if marker.kind == "npc" and self._npc_url(marker.label) and self._npc_image(marker.label) is None
        }
        if not missing and not npcs:
            return

        def run() -> None:
            monsters_done = download_missing(self._sprites_dir, missing) if missing else []
            npcs_done = download_items(self._npcs_dir, npcs) if npcs else []
            if monsters_done or npcs_done:
                self._sprite_loader.loaded.emit(quest.id)

        # daemon=True: zamknięcie okna nie czeka na pobieranie.
        threading.Thread(target=run, daemon=True, name="sprites").start()

    def _on_sprites_loaded(self, quest_id: str) -> None:
        # Gracz mógł w międzyczasie otworzyć inny quest: wtedy nic nie odświeżamy.
        if self._quest is None or self._quest.id != quest_id:
            return
        for row in self._step_rows:
            row.refresh_text()
            row.refresh_markers()
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
        self,
        index: int,
        step: Step,
        checked: bool,
        monsters: dict[str, Monster],
        sprites_dir: Path,
        npc_image: Callable[[str], Path | None] = lambda name: None,
    ) -> None:
        super().__init__()
        self.setObjectName("step")
        self.index = index
        self._step = step
        self._monsters = monsters
        self._sprites_dir = sprites_dir
        self._npc_image = npc_image
        self._marker_tiles: list[_MarkerTile] = []
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
        if step.markers:
            # Pinezki po prawej jako kafelki (NPC z postacią, miejsce jako prostokąt):
            # łatwiej w nie trafić niż w małą ikonkę w tekście. Najwyżej 2 w rzędzie.
            aside = QGridLayout()
            aside.setSpacing(4)
            for position, marker in enumerate(step.markers):
                tile = _MarkerTile(marker, npc_image(marker.label) if marker.kind == "npc" else None)
                tile.clicked.connect(lambda marker: self.map_requested.emit(list(self._step.markers), marker))
                self._marker_tiles.append(tile)
                aside.addWidget(tile, position // 2, position % 2)
            layout.addLayout(aside)
            layout.setAlignment(aside, Qt.AlignmentFlag.AlignTop)

        self._box.toggled.connect(lambda value: self.toggled.emit(self.index, value))

    def _text_label(self, number: int, step: Step) -> QLabel:
        if not step.monsters:
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
        line = self._rich.fontMetrics().height()
        # Pinezki są kafelkami obok tekstu (pins=False), w tekście zostają tylko obrazki potworów.
        # Potwór jest większy (2 linie): w wysokości linii obrazek 64 px byłby nieczytelny.
        self._rich.setText(
            step_html(self.index + 1, self._step, "", lambda i: _img(self._sprite(i), line * 2), pins=False)
        )

    def refresh_markers(self) -> None:
        """Obrazki NPC mogły się właśnie pobrać."""
        for tile in self._marker_tiles:
            if tile.marker.kind == "npc":
                tile.set_image(self._npc_image(tile.marker.label))

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


class _MonsterTile(QFrame):
    """Kafelek w sekcji „Potwory”: animacja, a pod nią „2x Skeleton”. Dymek jak w tekście kroku.

    Kliknięcie otwiera stronę potwora w zakładce „Potwory”.
    """

    clicked = Signal(object)

    def __init__(self, monster: Monster, count: int | None, sprites_dir: Path) -> None:
        super().__init__()
        self.setObjectName("monsterTile")
        # Ignored: kafelki dzielą się szerokością okna, zamiast ją rozpychać długą nazwą.
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._monster = monster
        self._sprites_dir = sprites_dir
        self._sprite = AnimatedSprite(TILE_SPRITE)
        caption = f"{count}x {monster.name}" if count else monster.name
        self._caption = QLabel(caption, wordWrap=True, alignment=Qt.AlignmentFlag.AlignCenter)
        self._caption.setTextFormat(Qt.TextFormat.PlainText)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        layout.addWidget(self._sprite, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self._caption)
        self.refresh()

    def mousePressEvent(self, event) -> None:  # noqa: N802 (nazwa z Qt)
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._monster)

    def refresh(self) -> None:
        self._sprite.set_path(sprite_path(self._sprites_dir, self._monster.id))
        tooltip_img = _img(display_sprite(self._sprites_dir, self._monster.id), TOOLTIP_SPRITE)
        self.setToolTip(monster_tooltip(self._monster, tooltip_img))


class _MarkerTile(QFrame):
    """Pinezka kroku: NPC jako jego postać z imieniem, inne miejsca jako pionowy prostokąt z ikoną.

    Kliknięcie pokazuje to miejsce na mapie (i nie odhacza kroku).
    """

    clicked = Signal(object)

    def __init__(self, marker: MapPoint, image: Path | None) -> None:
        super().__init__()
        self.setObjectName("markerTile")
        self.marker = marker
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedWidth(MARKER_TILE_WIDTH)
        self.setMinimumHeight(MARKER_TILE_HEIGHT)
        self.setToolTip(
            tr("{name} ({kind}): kliknij, żeby zobaczyć na mapie", name=marker.label, kind=tr(KIND_NAMES[marker.kind]))
        )
        # Kolorowy pasek u góry: ten sam kolor co kropka tego rodzaju na mapie.
        self.setStyleSheet(f"QFrame#markerTile {{ border-top: 3px solid {KIND_COLORS[marker.kind]}; }}")

        self._sprite = AnimatedSprite(MARKER_SPRITE)
        self._icon = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self._icon.setPixmap(icon("pin").pixmap(QSize(18, 24)))
        caption = QLabel(marker.label, wordWrap=True, alignment=Qt.AlignmentFlag.AlignCenter)
        caption.setTextFormat(Qt.TextFormat.PlainText)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 4, 2, 4)
        layout.setSpacing(2)
        layout.addWidget(self._sprite, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self._icon)
        layout.addWidget(caption)
        layout.addStretch(1)
        self.set_image(image)

    def set_image(self, image: Path | None) -> None:
        # NPC z pobranym obrazkiem: jego postać; inaczej ikona pinezki.
        self._sprite.set_path(image)
        self._sprite.setVisible(image is not None)
        self._icon.setVisible(image is None)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (nazwa z Qt)
        if event.button() == Qt.MouseButton.LeftButton:
            event.accept()  # nie przekazujemy kliknięcia karcie, więc krok się nie odhacza
            self.clicked.emit(self.marker)


def _step_details(step: Step) -> str:
    details = []
    if step.location:
        # Bez ikony pinezki: ta jest tylko w tekście i oznacza klikalną mapę.
        details.append(tr("miejsce: {place}", place=step.location))
    if step.npc:
        details.append(f"NPC: {step.npc}")
    if step.items:
        details.append(tr("przedmioty: {items}", items=", ".join(step.items)))
    return " · ".join(details)
