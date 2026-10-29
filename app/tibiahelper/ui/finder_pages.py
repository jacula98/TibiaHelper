"""Narzędzie „Exiva finder”: gdzie może być fiendish potwór albo gracz (logika w core/finder.py).

Gracz klika na mapie, gdzie stoi, rzuca exiva i klika kierunek z komunikatu. Każdy kolejny
odczyt z innego miejsca zawęża obszar. Na mapie wszystko poza możliwym obszarem jest
przyciemnione, a sam obszar podświetlony na zielono.
"""

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import (
    QButtonGroup,
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..core.finder import Area, Direction, Distance, FloorHint, Reading, floor_ranges, possible_area
from ..core.i18n import N_, tr
from ..core.mapdata import floor_label, to_pixel
from ..core.models import MAP_X_MIN, MAP_Y_MIN, MapPoint
from . import theme
from .map_window import MapPanel
from .qol_pages import _top_bar

START = MapPoint(x=32369, y=32241, z=7, label="Thais")  # świątynia w Thais: punkt startowy mapy
AREA_COLOR = "#69f0ae"  # jasna zieleń: dobrze widać ją i na wodzie, i na trawie
DIM = QColor(0, 0, 0, 150)  # przyciemnienie mapy poza możliwym obszarem
MAX_READINGS_SHOWN = 4
MARKER = 14  # px na ekranie: znacznik gracza ma stały rozmiar przy każdym przybliżeniu

# Odległość -> napis na przycisku, podpowiedź z komunikatem z gry (po angielsku, jak w kliencie).
_DISTANCES: tuple[tuple[Distance, str, str], ...] = (
    ("close", N_("Blisko"), "5–100: „is to the north”"),
    ("far", N_("Daleko"), "101–250: „is far to the north”"),
    ("very_far", N_("B. daleko"), "251+: „is very far to the north”"),
)
_FLOORS: tuple[tuple[FloorHint, str, str], ...] = (
    ("same", N_("To piętro"), "„is to the north”"),
    ("up", N_("Wyżej"), "„is above you” / „is on a higher level to the north”"),
    ("down", N_("Niżej"), "„is below you” / „is on a lower level to the north”"),
)
# Siatka 3 x 3 jak róża wiatrów; środek to „obok” (0–4 kratki, bez kierunku).
_COMPASS: tuple[tuple[Direction | None, str, int, int], ...] = (
    ("NW", "↖", 0, 0), ("N", "↑", 0, 1), ("NE", "↗", 0, 2),
    ("W", "←", 1, 0), (None, "•", 1, 1), ("E", "→", 1, 2),
    ("SW", "↙", 2, 0), ("S", "↓", 2, 1), ("SE", "↘", 2, 2),
)
DIRECTION_NAMES = {
    "N": N_("północ"), "NE": N_("północny wschód"), "E": N_("wschód"), "SE": N_("południowy wschód"),
    "S": N_("południe"), "SW": N_("południowy zachód"), "W": N_("zachód"), "NW": N_("północny zachód"),
}
DISTANCE_NAMES = {"beside": N_("obok"), "close": N_("blisko"), "far": N_("daleko"), "very_far": N_("bardzo daleko")}


def _chip(text: str, hint: str, group: QButtonGroup, checked: bool) -> QPushButton:
    chip = QPushButton(text)
    chip.setObjectName("chip")
    chip.setCheckable(True)
    chip.setChecked(checked)
    chip.setToolTip(hint)
    chip.setCursor(Qt.CursorShape.PointingHandCursor)
    group.addButton(chip)
    return chip


def _floors_text(area: Area) -> str:
    if len(area.floors) == 16:
        return tr("każde")
    parts = [floor_label(a) if a == b else f"{floor_label(a)}…{floor_label(b)}" for a, b in floor_ranges(area.floors)]
    return ", ".join(parts)


class FinderPage(QWidget):
    back_requested = Signal()

    def __init__(self, maps_dir: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._position: tuple[int, int, int] | None = None
        self._readings: list[Reading] = []
        self._area: Area | None = None
        self._distance: Distance = "close"
        self._floor: FloorHint = "same"

        title = QLabel(tr("Exiva finder (fiendish)"))
        title.setObjectName("title")
        info = QLabel(
            tr("1. Kliknij na mapie, gdzie stoisz. 2. Rzuć exiva (np. „exiva moe res”). "
               "3. Wybierz odległość i piętro, kliknij strzałkę z komunikatu. Potem podejdź gdzie indziej i powtórz. "
               "Piętro czar podaje tylko z bliska (do 100 kratek)."),
            wordWrap=True,
        )
        info.setObjectName("muted")

        # Odległość i piętro: przełączane „chipy” (zawsze zaznaczony jeden), strzałka dodaje odczyt.
        distances = QHBoxLayout()
        distances.setSpacing(3)
        group = QButtonGroup(self)
        for index, (key, label, hint) in enumerate(_DISTANCES):
            chip = _chip(tr(label), hint, group, index == 0)
            chip.clicked.connect(lambda _=False, k=key: self._set_distance(k))
            distances.addWidget(chip)
        distances.addStretch(1)
        floors = QHBoxLayout()
        floors.setSpacing(3)
        group = QButtonGroup(self)
        for index, (key, label, hint) in enumerate(_FLOORS):
            chip = _chip(tr(label), hint, group, index == 0)
            chip.clicked.connect(lambda _=False, k=key: setattr(self, "_floor", k))
            floors.addWidget(chip)
        floors.addStretch(1)

        compass = QGridLayout()
        compass.setSpacing(2)
        self._compass: list[QPushButton] = []
        for direction, arrow, row, column in _COMPASS:
            button = QPushButton(arrow)
            button.setFixedSize(34, 28)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            if direction is None:
                button.setToolTip(tr("Obok (0–4 kratki): „is standing next to you” / „above you”"))
            else:
                button.setToolTip(tr(DIRECTION_NAMES[direction]))
            button.clicked.connect(lambda _=False, d=direction: self._add_reading(d))
            compass.addWidget(button, row, column)
            self._compass.append(button)

        undo = QPushButton(tr("↶ Cofnij"))
        undo.clicked.connect(self._undo)
        clear = QPushButton(tr("Wyczyść"))
        clear.clicked.connect(self._clear)
        actions = QVBoxLayout()
        actions.addWidget(undo)
        actions.addWidget(clear)
        actions.addStretch(1)

        choices = QVBoxLayout()
        choices.setSpacing(4)
        choices.addLayout(distances)
        choices.addLayout(floors)
        choices.addStretch(1)
        controls = QHBoxLayout()
        controls.addLayout(compass)
        controls.addLayout(choices, 1)
        controls.addLayout(actions)

        self._status = QLabel(wordWrap=True)
        self._history = QLabel(wordWrap=True)
        self._history.setObjectName("muted")

        self._map = MapPanel(maps_dir)
        self._map.tile_clicked.connect(self._set_position)
        self._map_started = False
        source = QLabel(tr("Zasady exivy z TibiaWiki (CC BY-SA). Mapa: tibiamaps."), wordWrap=True)
        source.setObjectName("muted")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addLayout(_top_bar(tr("← Narzędzia"), self.back_requested))
        layout.addWidget(title)
        layout.addWidget(info)
        layout.addLayout(controls)
        layout.addWidget(self._status)
        layout.addWidget(self._history)
        layout.addWidget(self._map, 1)
        layout.addWidget(source)
        self._update()

    def showEvent(self, event) -> None:  # noqa: N802 (nazwa z Qt)
        # Mapę ładujemy dopiero przy pierwszym otwarciu: kto nie używa findera, nie pobiera piętra.
        super().showEvent(event)
        if not self._map_started:
            self._map_started = True
            self._map.start_free(tr("Exiva finder"), tr("Kliknij, gdzie stoisz"), START, self._draw_overlay)
            self._update()

    def _set_distance(self, distance: Distance) -> None:
        self._distance = distance
        self._update()

    def _set_position(self, x: int, y: int, z: int) -> None:
        self._position = (x, y, z)
        self._update()

    def _add_reading(self, direction: Direction | None) -> None:
        if self._position is None:
            return
        distance: Distance = "beside" if direction is None else self._distance
        # Daleko czar nie mówi o piętrze, więc wybór piętra pomijamy.
        floor = self._floor if distance in ("beside", "close") else "same"
        self._readings.append(Reading(*self._position, distance, direction, floor))
        self._recompute(fit=True)

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
            self._map.fit_rect(rect.adjusted(-10, -10, 10, 10))

    def _update(self) -> None:
        for button in self._compass:
            button.setEnabled(self._position is not None)

        if self._position is None:
            self._status.setText(tr("Kliknij na mapie, gdzie stoisz."))
        elif not self._readings:
            self._status.setText(tr("Rzuć exiva i kliknij strzałkę z komunikatu (środek = obok)."))
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
            text = tr(DISTANCE_NAMES[reading.distance])
            if reading.direction:
                text += ", " + tr(DIRECTION_NAMES[reading.direction])
            if reading.floor != "same":
                text += ", " + (tr("wyżej") if reading.floor == "up" else tr("niżej"))
            lines.append(f"{number}. {text} ({reading.x}, {reading.y}, {floor_label(reading.z)})")
        self._history.setText("\n".join(lines[-MAX_READINGS_SHOWN:]))
        self._history.setVisible(bool(lines))
        if self._position is not None:
            x, y, z = self._position
            self._map.set_legend(tr("Stoisz: x {x}, y {y}, piętro {floor}", x=x, y=y, floor=floor_label(z)))
        else:
            self._map.set_legend(tr("Kliknij, gdzie stoisz"))
        if self._map_started:
            self._map.redraw()

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
            if reading.z == z:
                self._marker(scene, reading.x, reading.y, QColor("#ffd54f"), str(number), font)
        # Obecne miejsce tylko, gdy nie leży pod numerem odczytu (inaczej zasłoniłoby numer).
        taken = {(r.x, r.y, r.z) for r in self._readings}
        if self._position is not None and self._position[2] == z and self._position not in taken:
            self._marker(scene, self._position[0], self._position[1], QColor(theme.ACCENT), "", font)

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
