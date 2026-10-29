"""Narzędzie „Exiva finder”: gdzie może być fiendish potwór albo gracz (logika w core/finder.py).

Gracz klika na mapie, gdzie stoi: pojawia się gwiazdka z 8 strzałkami. Po rzuceniu exivy klika
strzałkę w kierunku z komunikatu i wybiera z menu tekst, który pokazała gra (np. „is far to the
north”). Gwiazdka to komunikaty bez kierunku („next to you”, „above you”). Każdy kolejny odczyt
z innego miejsca zawęża obszar: reszta mapy jest przyciemniona, a obszar podświetlony na zielono.
Pod mapą lista potworów, które mają tam miejsca występowania (z trudnością z Find Fiend).
"""

import math
from collections.abc import Callable
from html import escape
from pathlib import Path

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QCursor, QFont, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import (
    QButtonGroup,
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..core.finder import (
    DIFFICULTIES,
    DIRECTIONS,
    Area,
    Direction,
    Distance,
    FloorHint,
    Reading,
    candidates,
    floor_ranges,
    message,
    possible_area,
)
from ..core.i18n import tr
from ..core.mapdata import floor_label, to_pixel
from ..core.models import MAP_X_MIN, MAP_Y_MIN, MapPoint, Monster
from ..core.spawns import SOURCE_NOTE, Spawns
from . import theme
from .map_window import BUTTON_ITEM, MapPanel
from .qol_pages import _top_bar

START = MapPoint(x=32369, y=32241, z=7, label="Thais")  # świątynia w Thais: punkt startowy mapy
AREA_COLOR = "#69f0ae"  # jasna zieleń: dobrze widać ją i na wodzie, i na trawie
STAR_COLOR = "#ffd54f"
DIM = QColor(0, 0, 0, 150)  # przyciemnienie mapy poza możliwym obszarem
MAX_READINGS_SHOWN = 4
MAX_CANDIDATES = 8  # więcej nazw nie mieści się w wąskim oknie
# Rozmiary w pikselach ekranu: gwiazdka i strzałki są tak samo duże przy każdym przybliżeniu.
MARKER = 14
STAR_RADIUS = 11
ARROW_BASE, ARROW_TIP, ARROW_HALF_WIDTH = 19, 38, 8
_ANGLES = {"E": 0, "NE": 45, "N": 90, "NW": 135, "W": 180, "SW": 225, "S": 270, "SE": 315}

# Komunikaty pod strzałką: (odległość, piętro, ile kratek). Kolejność jak w menu.
_ARROW_MESSAGES: tuple[tuple[Distance, FloorHint, str], ...] = (
    ("close", "same", "5–100"),
    ("far", "same", "101–250"),
    ("very_far", "same", "251+"),
    ("close", "up", "5–100"),
    ("close", "down", "5–100"),
)
_STAR_MESSAGES: tuple[tuple[FloorHint, str], ...] = (("same", "0–4"), ("up", "0–4"), ("down", "0–4"))


def _floors_text(area: Area) -> str:
    if len(area.floors) == 16:
        return tr("każde")
    parts = [floor_label(a) if a == b else f"{floor_label(a)}…{floor_label(b)}" for a, b in floor_ranges(area.floors)]
    return ", ".join(parts)


class _MapButton(QGraphicsPathItem):
    """Kształt na mapie, który działa jak przycisk (strzałka albo gwiazdka); klik otwiera menu."""

    def __init__(self, path: QPainterPath, color: QColor, on_click: Callable[[QPoint], None]) -> None:
        super().__init__(path)
        self._color = color
        self._on_click = on_click
        self.setData(0, BUTTON_ITEM)  # MapView nie potraktuje tego jako kliknięcia w mapę
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setPen(QPen(QColor("#000000"), 1.5))
        self.setBrush(color)
        self.setZValue(8)

    def hoverEnterEvent(self, event) -> None:  # noqa: N802 (nazwa z Qt)
        self.setBrush(QColor(theme.ACCENT))

    def hoverLeaveEvent(self, event) -> None:  # noqa: N802 (nazwa z Qt)
        self.setBrush(self._color)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (nazwa z Qt)
        event.accept()  # bez tego Qt oddałby klik mapie (przeciąganie)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (nazwa z Qt)
        # Menu dopiero po obsłudze kliknięcia: wybór w menu rysuje mapę od nowa i kasuje ten element,
        # więc nie może się to stać w trakcie jego własnej funkcji (Qt by się wysypał).
        pos = event.screenPos()
        QTimer.singleShot(0, lambda: self._on_click(pos))


def _arrow_path(direction: Direction) -> QPainterPath:
    angle = math.radians(_ANGLES[direction])
    # Minus przy y: na ekranie y rośnie w dół, a północ jest w górze.
    ux, uy = math.cos(angle), -math.sin(angle)
    px, py = -uy, ux  # prostopadle do strzałki
    path = QPainterPath()
    path.addPolygon(QPolygonF([
        QPointF(ux * ARROW_TIP, uy * ARROW_TIP),
        QPointF(ux * ARROW_BASE + px * ARROW_HALF_WIDTH, uy * ARROW_BASE + py * ARROW_HALF_WIDTH),
        QPointF(ux * ARROW_BASE - px * ARROW_HALF_WIDTH, uy * ARROW_BASE - py * ARROW_HALF_WIDTH),
    ]))
    path.closeSubpath()
    return path


def _star_path() -> QPainterPath:
    points = []
    for index in range(10):
        radius = STAR_RADIUS if index % 2 == 0 else STAR_RADIUS * 0.45
        angle = math.radians(90 + index * 36)
        points.append(QPointF(radius * math.cos(angle), -radius * math.sin(angle)))
    path = QPainterPath()
    path.addPolygon(QPolygonF(points))
    path.closeSubpath()
    return path


class FinderPage(QWidget):
    back_requested = Signal()
    monster_requested = Signal(object)  # Monster: kliknięta nazwa na liście „może to być”

    def __init__(self, maps_dir: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._position: tuple[int, int, int] | None = None
        self._readings: list[Reading] = []
        self._area: Area | None = None
        self._difficulty: str | None = None
        self._monsters: dict[str, Monster] = {}
        self._spawns = Spawns()

        title = QLabel(tr("Exiva finder (fiendish)"))
        title.setObjectName("title")
        info = QLabel(
            tr("Kliknij na mapie, gdzie stoisz. Rzuć „exiva moe res”, kliknij strzałkę w stronę z komunikatu "
               "i wybierz tekst, który pokazała gra. Gwiazdka to „next to you”, „above you” i „below you”. "
               "Potem podejdź gdzie indziej i powtórz."),
            wordWrap=True,
        )
        info.setObjectName("muted")

        # Trudność: Find Fiend podaje ją, gdy gracz ma ukończony Bestiary tego potwora.
        chips = QHBoxLayout()
        chips.setSpacing(3)
        group = QButtonGroup(self)
        for index, level in enumerate((None, *DIFFICULTIES)):
            chip = QPushButton(level or tr("Każda"))
            chip.setObjectName("chip")
            chip.setCheckable(True)
            chip.setChecked(index == 0)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setToolTip(tr("Trudność z komunikatu Find Fiend (tylko przy ukończonym Bestiary tego potwora)"))
            chip.clicked.connect(lambda _=False, lv=level: self._set_difficulty(lv))
            group.addButton(chip)
            chips.addWidget(chip)
        chips.addStretch(1)

        undo = QPushButton(tr("↶ Cofnij"))
        undo.clicked.connect(self._undo)
        clear = QPushButton(tr("Wyczyść"))
        clear.clicked.connect(self._clear)
        actions = QHBoxLayout()
        actions.addWidget(undo)
        actions.addWidget(clear)
        actions.addStretch(1)

        self._status = QLabel(wordWrap=True)
        self._history = QLabel(wordWrap=True)
        self._history.setObjectName("muted")
        # RichText z linkami: nazwy potworów są z pliku danych, więc przechodzą przez escape.
        self._candidates = QLabel(wordWrap=True, textFormat=Qt.TextFormat.RichText)
        self._candidates.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
        self._candidates.linkActivated.connect(self._open_candidate)

        self._map = MapPanel(maps_dir)
        self._map.tile_clicked.connect(self._set_position)
        self._map_started = False
        source = QLabel(
            tr("Zasady exivy z TibiaWiki (CC BY-SA). Mapa: tibiamaps.") + " " + tr(SOURCE_NOTE), wordWrap=True
        )
        source.setObjectName("muted")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addLayout(_top_bar(tr("← Narzędzia"), self.back_requested))
        layout.addWidget(title)
        layout.addWidget(info)
        layout.addLayout(chips)
        layout.addLayout(actions)
        layout.addWidget(self._status)
        layout.addWidget(self._history)
        layout.addWidget(self._candidates)
        layout.addWidget(self._map, 1)
        layout.addWidget(source)
        self._update()

    def set_monsters(self, monsters: dict[str, Monster]) -> None:
        self._monsters = monsters
        self._update()

    def set_spawns(self, spawns: Spawns) -> None:
        self._spawns = spawns
        self._update()

    def showEvent(self, event) -> None:  # noqa: N802 (nazwa z Qt)
        # Mapę ładujemy dopiero przy pierwszym otwarciu: kto nie używa findera, nie pobiera piętra.
        super().showEvent(event)
        if not self._map_started:
            self._map_started = True
            self._map.start_free(tr("Exiva finder"), tr("Kliknij, gdzie stoisz"), START, self._draw_overlay)
            self._update()

    def _set_difficulty(self, level: str | None) -> None:
        self._difficulty = level
        self._update()

    def _set_position(self, x: int, y: int, z: int) -> None:
        self._position = (x, y, z)
        self._update()

    def _add_reading(self, distance: Distance, direction: Direction | None, floor: FloorHint) -> None:
        if self._position is None:
            return
        self._readings.append(Reading(*self._position, distance, direction, floor))
        self._recompute(fit=True)

    def _show_menu(self, direction: Direction | None, screen_pos: QPoint) -> None:
        menu = self._menu(direction)
        menu.exec(screen_pos if not screen_pos.isNull() else QCursor.pos())

    def _menu(self, direction: Direction | None) -> QMenu:
        """Menu z komunikatami z gry dla klikniętej strzałki (albo gwiazdki, gdy direction=None)."""
        menu = QMenu(self)
        title = menu.addAction(tr("Co pokazała gra?"))
        title.setEnabled(False)
        if direction is None:
            options = [("beside", floor, squares) for floor, squares in _STAR_MESSAGES]
        else:
            options = list(_ARROW_MESSAGES)
        for distance, floor, squares in options:
            # Tabulator: Qt pokazuje tekst po nim w prawej kolumnie menu (tu: ile kratek).
            action = menu.addAction(f"…{message(distance, direction, floor)}\t{squares}")
            action.triggered.connect(lambda _=False, d=distance, f=floor: self._add_reading(d, direction, f))
        return menu

    def _undo(self) -> None:
        if self._readings:
            self._readings.pop()
            self._recompute(fit=True)

    def _clear(self) -> None:
        self._readings = []
        self._position = None
        self._recompute()

    def _recompute(self, fit: bool = False) -> None:
        self._area = possible_area(self._readings)
        self._update()
        if fit and self._area is not None and not self._area.empty:
            # Jeśli cel nie może być na oglądanym piętrze, przechodzimy na najbliższe możliwe.
            if self._map.floor not in self._area.floors:
                self._map.go_to_floor(min(self._area.floors, key=lambda z: abs(z - self._map.floor)))
            # Widać cały obszar i miejsce, z którego był ostatni odczyt (gracz widzi siebie).
            x0, y0, x1, y1 = self._area.bounds()
            last = self._readings[-1]
            x0, y0, x1, y1 = min(x0, last.x), min(y0, last.y), max(x1, last.x + 1), max(y1, last.y + 1)
            rect = QRectF(x0 - MAP_X_MIN, y0 - MAP_Y_MIN, x1 - x0, y1 - y0)
            self._map.fit_rect(rect.adjusted(-25, -25, 25, 25))

    def _update(self) -> None:
        if self._position is None:
            self._status.setText(tr("Kliknij na mapie, gdzie stoisz."))
        elif not self._readings:
            self._status.setText(tr("Rzuć exiva i kliknij strzałkę (albo gwiazdkę) zgodnie z komunikatem."))
        elif self._area is None or self._area.empty:
            self._status.setText(
                tr("Odczyty się wykluczają. Cofnij ostatni albo wyczyść: fiend mógł zginąć albo inny jest teraz bliżej.")
            )
        else:
            self._status.setText(
                tr("Możliwe miejsce: ok. {n} kratek · piętra: {floors}", n=f"{self._area.tiles:,}".replace(",", " "),
                   floors=_floors_text(self._area))
            )

        lines = []
        for number, reading in enumerate(self._readings, start=1):
            text = f"„…{message(reading.distance, reading.direction, reading.floor)}”"
            lines.append(f"{number}. {text} ({reading.x}, {reading.y}, {floor_label(reading.z)})")
        self._history.setText("\n".join(lines[-MAX_READINGS_SHOWN:]))
        self._history.setVisible(bool(lines))
        self._update_candidates()
        if self._position is not None:
            x, y, z = self._position
            self._map.set_legend(tr("Stoisz: x {x}, y {y}, piętro {floor}", x=x, y=y, floor=floor_label(z)))
        else:
            self._map.set_legend(tr("Kliknij, gdzie stoisz"))
        if self._map_started:
            self._map.redraw()

    def _update_candidates(self) -> None:
        area = self._area
        if area is None or area.empty or not self._spawns.monsters:
            self._candidates.hide()
            return
        found = candidates(area, self._spawns, self._monsters, self._difficulty)
        if not found:
            self._candidates.setText(tr("Żaden znany potwór{level} nie występuje w tym obszarze.",
                                        level=f" ({self._difficulty})" if self._difficulty else ""))
        else:
            links = ", ".join(
                f'<a href="{escape(monster.id)}">{escape(monster.name)}</a> ({count})'
                for monster, count in found[:MAX_CANDIDATES]
            )
            more = len(found) - MAX_CANDIDATES
            text = tr("Może to być: {list}", list=links)
            if more > 0:
                text += " " + tr("i {n} innych", n=more)
            self._candidates.setText(text)
        self._candidates.show()

    def _open_candidate(self, monster_id: str) -> None:
        monster = self._monsters.get(monster_id)
        if monster is not None:
            self.monster_requested.emit(monster)

    def _draw_overlay(self, scene: QGraphicsScene, z: int) -> None:
        rect = scene.sceneRect()
        area = self._area
        if area is not None:
            shape = QPainterPath()
            for polygon in area.polygons:
                # Współrzędne gry -> piksele mapy (jak to_pixel, ale na liczbach z przecinkiem).
                shape.addPolygon(QPolygonF([QPointF(x - MAP_X_MIN, y - MAP_Y_MIN) for x, y in polygon]))
                shape.closeSubpath()
            # Jeden kształt zamiast kawałków: bez linii w miejscach, gdzie kawałki się stykają.
            shape = shape.simplified()
            # Przyciemnienie: cała mapa minus możliwy obszar (kawałki na siebie nie zachodzą).
            dim = QPainterPath()
            dim.addRect(rect)
            if z in area.floors:
                dim.addPath(shape)
            dim.setFillRule(Qt.FillRule.OddEvenFill)
            scene.addPath(dim, QPen(Qt.PenStyle.NoPen), QBrush(DIM)).setZValue(4)
            if z in area.floors:
                fill = QColor(AREA_COLOR)
                fill.setAlpha(60)
                pen = QPen(QColor(AREA_COLOR), 2)
                pen.setCosmetic(True)  # stała grubość linii na ekranie przy każdym przybliżeniu
                scene.addPath(shape, pen, QBrush(fill)).setZValue(5)
            elif not area.empty:
                # Na tym piętrze celu nie ma: zostawiamy tylko szary, przerywany zarys.
                pen = QPen(QColor("#bdbdbd"), 1.5, Qt.PenStyle.DashLine)
                pen.setCosmetic(True)
                scene.addPath(shape, pen).setZValue(5)

        font = QFont()
        font.setPixelSize(9)
        font.setBold(True)
        for number, reading in enumerate(self._readings, start=1):
            if reading.z == z and (reading.x, reading.y, reading.z) != self._position:
                self._marker(scene, reading.x, reading.y, QColor("#90caf9"), str(number), font)
        if self._position is not None and self._position[2] == z:
            self._draw_star(scene, *self._position[:2])

    def _draw_star(self, scene: QGraphicsScene, x: int, y: int) -> None:
        px, py = to_pixel(x, y)
        center = QPointF(px + 0.5, py + 0.5)
        # Ostatni wybór z tego miejsca zostaje zielony (jak obszar), żeby było widać, co już kliknięto.
        last = self._readings[-1] if self._readings else None
        chosen = "none"
        if last is not None and (last.x, last.y, last.z) == self._position:
            chosen = last.direction  # None = gwiazdka („next to you” itd.)
        star_color = QColor(AREA_COLOR if chosen is None else STAR_COLOR)
        star = _MapButton(_star_path(), star_color, lambda pos: self._show_menu(None, pos))
        star.setToolTip("next to you / above you / below you")
        star.setPos(center)
        scene.addItem(star)
        for direction in DIRECTIONS:
            color = QColor(AREA_COLOR) if direction == chosen else QColor(255, 255, 255, 210)
            arrow = _MapButton(_arrow_path(direction), color, lambda pos, d=direction: self._show_menu(d, pos))
            arrow.setPos(center)
            scene.addItem(arrow)

    @staticmethod
    def _marker(scene: QGraphicsScene, x: int, y: int, color: QColor, text: str, font: QFont) -> None:
        px, py = to_pixel(x, y)
        center = QPointF(px + 0.5, py + 0.5)
        # ItemIgnoresTransformations: rozmiar w pikselach ekranu, a setPos to środek kratki.
        dot = scene.addEllipse(QRectF(-MARKER / 2, -MARKER / 2, MARKER, MARKER), QPen(QColor("#000000"), 1.5), QBrush(color))
        dot.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        dot.setPos(center)
        dot.setZValue(6)
        if text:
            # Numer jako dziecko kropki: ma jej układ (piksele ekranu), więc łatwo go wyśrodkować.
            label = QGraphicsSimpleTextItem(text, dot)
            label.setFont(font)
            box = label.boundingRect()
            label.setPos(-box.width() / 2, -box.height() / 2)
