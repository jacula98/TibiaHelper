"""Mapa piętra Tibii z kropkami w miejscach z kroku questa.

MapPanel to sam widżet mapy: graczom wysuwa się na dole widoku questa,
pod krokami. MapWindow to ten sam panel w osobnym oknie, używany
w edytorze autora do wskazania miejsca kliknięciem.
"""

import logging
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPixmap, QWheelEvent
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..core.i18n import N_, tr
from ..core.mapdata import ensure_floor, floor_label, floor_path, to_pixel
from ..core.models import MAP_X_MIN, MAP_Y_MIN, MapPoint
from ..core.spawns import Point, busiest_spot, floors
from . import theme

log = logging.getLogger(__name__)

# Kolory kropek według rodzaju punktu.
KIND_COLORS = {
    "npc": "#4fc3f7",
    "place": theme.ACCENT,
    "passage": "#81c784",
    "use": "#ef5350",
}
# N_: tłumaczymy przy pokazaniu, tr(KIND_NAMES[...]) (zob. core/i18n.py).
KIND_NAMES = {"npc": "NPC", "place": N_("miejsce"), "passage": N_("przejście"), "use": N_("użyj")}
START_ZOOM = 4.0  # 1 kratka = 4 piksele na ekranie: widać okolicę, ale nie całą mapę
SPAWN_ZOOM = 2.0  # mapa miejsc potwora: oddalona, żeby od razu widać było całe skupisko
MIN_ZOOM, MAX_ZOOM = 0.5, 16.0
DOT_RADIUS = 1.6  # w kratkach mapy, więc kropka rośnie razem z przybliżeniem
RING_RADIUS = 3.5  # obwódka wokół kropki, żeby od razu rzucała się w oczy
# Fiolet prawie nie występuje na mapie Tibii, więc punkty nie giną na lawie czy trawie.
SPAWN_COLOR = "#e040fb"
SPAWN_HALO = 2.5  # półprzezroczysta poświata: pojedyncza kratka byłaby niewidoczna przy oddaleniu
SPAWN_ICON = 22  # px na ekranie: obrazek potwora na mapie ma stały rozmiar przy każdym przybliżeniu
SPAWN_ICON_CELL = 12  # kratki: jeden obrazek na taki kwadrat, żeby setki obrazków nie zlały się w plamę


def spawn_icon(sprite: QImage) -> QPixmap:
    """Znacznik na mapie: obrazek potwora w kółku z fioletową obwódką (widać go na każdym tle)."""
    pixmap = QPixmap(SPAWN_ICON, SPAWN_ICON)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor(SPAWN_COLOR), 1.5))
    painter.setBrush(QColor(0, 0, 0, 150))
    painter.drawEllipse(QRectF(1, 1, SPAWN_ICON - 2, SPAWN_ICON - 2))
    inner = SPAWN_ICON - 6
    scaled = sprite.scaled(inner, inner, Qt.AspectRatioMode.KeepAspectRatio)
    painter.drawImage(int((SPAWN_ICON - scaled.width()) / 2), int((SPAWN_ICON - scaled.height()) / 2), scaled)
    painter.end()
    return pixmap


def _circle(center: QPointF, radius: float) -> QRectF:
    return QRectF(center.x() - radius, center.y() - radius, radius * 2, radius * 2)


class _FloorLoader(QObject):
    """Pobiera piętro w tle i oddaje wynik do wątku okna sygnałem."""

    loaded = Signal(int, str)  # piętro, ścieżka do PNG
    failed = Signal(int, str)  # piętro, opis błędu


class MapView(QGraphicsView):
    """Widok mapy: kółko myszy przybliża, przeciąganie przesuwa."""

    # Kliknięcie bez przeciągania (współrzędne sceny = piksele mapy).
    clicked = Signal(float, float)

    def __init__(self) -> None:
        super().__init__()
        self._press_pos = None
        self.setScene(QGraphicsScene(self))
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        # Wygładzamy tylko kropki. Samej mapy nie (brak SmoothPixmapTransform):
        # to piksele, rozmyte przy przybliżeniu wyglądałyby gorzej.
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setBackgroundBrush(QColor("#000000"))
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        # Paski przewijania są zbędne: mapę przesuwa się przeciąganiem.
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (nazwa z Qt)
        self._press_pos = event.position()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (nazwa z Qt)
        super().mouseReleaseEvent(event)
        # Ruch o kilka pikseli to jeszcze kliknięcie; dalej to przesuwanie mapy.
        if self._press_pos is not None and (event.position() - self._press_pos).manhattanLength() < 5:
            scene_pos = self.mapToScene(event.position().toPoint())
            self.clicked.emit(scene_pos.x(), scene_pos.y())
        self._press_pos = None

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802 (nazwa z Qt)
        factor = 1.25 if event.angleDelta().y() > 0 else 0.8
        zoom = self.transform().m11() * factor
        if MIN_ZOOM <= zoom <= MAX_ZOOM:
            self.scale(factor, factor)


class MapPanel(QWidget):
    # Tryb wybierania (edytor autora): kliknięte miejsce jako x, y, z w grze.
    point_picked = Signal(int, int, int)
    # Kliknięty „×” (tylko gdy panel ma przycisk zamknięcia).
    close_requested = Signal()

    def __init__(self, maps_dir: Path, closable: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._maps_dir = maps_dir
        self._points: list[MapPoint] = []
        self._focus: MapPoint | None = None
        # Tryb „gdzie występuje potwór”: setki punktów bez podpisów.
        self._spawns: list[Point] = []
        self._spawn_note = ""
        self._spawn_icon: QPixmap | None = None
        self._floor = 7
        self._loading: set[int] = set()
        # Tryb trasy (boss): kolejne punkty na tym samym piętrze łączy linia.
        self._route = False

        self._loader = _FloorLoader()
        self._loader.loaded.connect(self._on_floor_loaded)
        self._loader.failed.connect(self._on_floor_failed)

        self._title = QLabel()
        self._title.setStyleSheet("font-weight: 600;")
        # Jedna linia: za długi podpis jest ucinany (pełny jest w dymku i w opisie niżej).
        self._title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        # PlainText: podpisy pochodzą z pliku danych, więc nie mogą być czytane jako HTML.
        self._legend = QLabel(textFormat=Qt.TextFormat.PlainText)
        self._legend.setObjectName("muted")
        self._legend.setWordWrap(True)

        up = QToolButton(text="▲")
        up.setToolTip(tr("Piętro wyżej"))
        up.clicked.connect(lambda: self._change_floor(-1))
        down = QToolButton(text="▼")
        down.setToolTip(tr("Piętro niżej"))
        down.clicked.connect(lambda: self._change_floor(+1))
        self._floor_label = QLabel()

        self._view = MapView()
        self._view.clicked.connect(self._on_map_clicked)
        self._picking = False
        self._view.setToolTip(tr("Kółko myszy: przybliżenie · przeciągnij: przesuwanie"))
        self._status = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self._status.setObjectName("muted")
        self._status.setWordWrap(True)

        # Jeden wiersz nagłówka: nazwa miejsca, piętro, strzałki i ewentualnie „×”.
        header = QHBoxLayout()
        header.addWidget(self._title, 1)
        header.addWidget(self._floor_label)
        header.addWidget(up)
        header.addWidget(down)
        if closable:
            close = QToolButton(text="✕")
            close.setToolTip(tr("Schowaj mapę"))
            close.clicked.connect(self.close_requested)
            header.addWidget(close)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.setSpacing(4)
        layout.addLayout(header)
        layout.addWidget(self._legend)
        layout.addWidget(self._view, 1)
        layout.addWidget(self._status)

    def show_spawns(self, title: str, spawns: list[Point], note: str, icon: QPixmap | None = None) -> None:
        """Wszystkie miejsca występowania potwora; start na piętrze i w miejscu, gdzie jest ich najwięcej."""
        self._spawn_icon = icon
        self._picking = False
        self._route = False
        self._points = []
        self._spawns = spawns
        self._spawn_note = note
        self._title.setText(title)
        self._title.setToolTip(title)
        z = floors(spawns)[0][0] if spawns else 7
        spot = busiest_spot(spawns, z)
        self._focus = MapPoint(x=spot[0], y=spot[1], z=z, label=title) if spot else None
        self._set_floor(z)

    def set_spawn_icon(self, icon: QPixmap | None) -> None:
        """Obrazek potwora doszedł później (pobrał się w tle): rysujemy mapę jeszcze raz, w tym samym miejscu."""
        self._spawn_icon = icon
        path = floor_path(self._maps_dir, self._floor)
        if self._spawns and path.exists():
            self._draw(self._floor, path, keep_view=True)

    def focus_on(self, x: int, y: int, z: int) -> None:
        """Przenosi mapę na wskazane miejsce (np. wybrane expowisko) i jego piętro."""
        self._focus = MapPoint(x=x, y=y, z=z, label=self._title.text() or tr("miejsce"))
        self._set_floor(z)

    def pick_point(self, points: list[MapPoint], start: MapPoint, route: bool = False) -> None:
        """Tryb autora: autor klika miejsce na mapie, okno wysyła point_picked."""
        self._spawns = []
        self._picking = True
        self._route = route
        self._points = list(points)
        self._focus = start
        self._title.setText("Kliknij miejsce na mapie")
        self._legend.setText("Zmień piętro strzałkami, jeśli miejsce jest wyżej albo pod ziemią.")
        self._set_floor(start.z)

    def _on_map_clicked(self, scene_x: float, scene_y: float) -> None:
        if not self._picking or self._view.scene().sceneRect().isEmpty():
            return
        x, y = MAP_X_MIN + int(scene_x), MAP_Y_MIN + int(scene_y)
        try:
            picked = MapPoint(x=x, y=y, z=self._floor, label="wybrane miejsce")
        except ValueError:
            return  # klik poza mapą Tibii
        self._focus = picked
        self._points = [p for p in self._points if p.label != "wybrane miejsce"] + [picked]
        self._legend.setText(f"Wybrano: x {x}, y {y}, piętro {floor_label(self._floor)}")
        self._draw(self._floor, floor_path(self._maps_dir, self._floor), keep_view=True)
        self.point_picked.emit(x, y, self._floor)

    def show_points(self, points: list[MapPoint], focus: MapPoint) -> None:
        """Pokazuje punkty jednego kroku i centruje mapę na klikniętym."""
        self._picking = False
        self._route = False
        self._spawns = []
        self._points = points
        self._focus = focus
        self._title.setText(focus.label)
        self._title.setToolTip(focus.label)
        self._legend.setText(f"{focus.label} · {tr(KIND_NAMES[focus.kind])} · x {focus.x}, y {focus.y}")
        self._set_floor(focus.z)

    def update_points(self, points: list[MapPoint]) -> None:
        """Nowe punkty bez ruszania widoku (edytor trasy: klikanie punkt po punkcie)."""
        self._points = list(points)
        path = floor_path(self._maps_dir, self._floor)
        if path.exists():
            self._draw(self._floor, path, keep_view=True)

    def show_route(self, title: str, points: list[MapPoint], focus: MapPoint) -> None:
        """Trasa (np. do bossa): punkty po kolei, połączone linią na każdym piętrze."""
        self._picking = False
        self._spawns = []
        self._route = True
        self._points = points
        self._focus = focus
        self._title.setText(title)
        self._title.setToolTip(title)
        self._legend.setText(focus.label or "")  # punkt drogi nie ma podpisu
        self._set_floor(focus.z)

    def recenter(self) -> None:
        """Centruje mapę na wybranym punkcie (np. po wysunięciu panelu, gdy zmienił się rozmiar)."""
        if self._focus is not None and self._focus.z == self._floor:
            self._view.centerOn(*to_pixel(self._focus.x, self._focus.y))

    def _change_floor(self, delta: int) -> None:
        self._set_floor(max(0, min(15, self._floor + delta)))

    def _set_floor(self, z: int) -> None:
        self._floor = z
        self._floor_label.setText(tr("piętro: {floor}", floor=floor_label(z)))
        if self._spawns:
            self._legend.setText(self._spawn_legend(z))
        self._view.scene().clear()
        path = floor_path(self._maps_dir, z)
        if path.exists():
            self._draw(z, path)
            return
        self._status.setText(tr("Pobieram mapę tego piętra (tylko za pierwszym razem)…"))
        self._status.show()
        if z not in self._loading:
            self._loading.add(z)
            # daemon=True: zamknięcie programu nie czeka na pobieranie.
            threading.Thread(target=self._load_floor, args=(z,), daemon=True).start()

    def _spawn_legend(self, z: int) -> str:
        counts = dict(floors(self._spawns))
        others = ", ".join(f"{floor_label(f)}: {n}" for f, n in sorted(counts.items()) if f != z)
        text = tr("Na tym piętrze: {n} miejsc", n=counts.get(z, 0))
        if others:
            text += " · " + tr("inne piętra ({floors})", floors=others)
        return f"{text}\n{self._spawn_note}"

    def _load_floor(self, z: int) -> None:
        try:
            path = ensure_floor(self._maps_dir, z)
        except (OSError, ValueError) as exc:
            self._loader.failed.emit(z, str(exc))
            return
        self._loader.loaded.emit(z, str(path))

    def _on_floor_loaded(self, z: int, path: str) -> None:
        self._loading.discard(z)
        if z == self._floor:
            self._draw(z, Path(path))

    def _on_floor_failed(self, z: int, error: str) -> None:
        self._loading.discard(z)
        log.warning("Nie udało się pobrać mapy piętra %s: %s", z, error)
        if z == self._floor:
            self._status.setText(tr("Nie udało się pobrać mapy. Sprawdź internet i otwórz mapę ponownie."))

    def _draw(self, z: int, path: Path, keep_view: bool = False) -> None:
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            # Uszkodzony plik: kasujemy, żeby przy następnym otwarciu pobrać go od nowa.
            path.unlink(missing_ok=True)
            self._status.setText(tr("Plik mapy był uszkodzony. Otwórz mapę ponownie, żeby go pobrać."))
            self._status.show()
            return
        self._status.hide()
        scene = self._view.scene()
        scene.clear()
        scene.addPixmap(pixmap)
        scene.setSceneRect(pixmap.rect())

        if self._route:
            self._draw_route_lines(scene, z)
        font = QFont()
        font.setPixelSize(3)
        for point in self._points:
            # Punkt drogi bez podpisu (trasa) to tylko zgięcie linii.
            if point.z != z or point.label is None:
                continue
            px, py = to_pixel(point.x, point.y)
            # +0.5: środek kratki, a nie jej lewy górny róg.
            center = QPointF(px + 0.5, py + 0.5)
            color = QColor(KIND_COLORS[point.kind])
            scene.addEllipse(_circle(center, RING_RADIUS), QPen(color, 0.6))
            dot = scene.addEllipse(_circle(center, DOT_RADIUS), QPen(QColor("#000000"), 0.4), QBrush(color))
            dot.setToolTip(point.label)

            # Podpis na ciemnym tle, żeby był czytelny na każdym kolorze mapy.
            label = scene.addSimpleText(point.label, font)
            label.setBrush(QBrush(QColor("#ffffff")))
            label.setPos(center.x() + RING_RADIUS + 1, center.y() - 2)
            box = label.sceneBoundingRect().adjusted(-0.8, -0.3, 0.8, 0.3)
            background = scene.addRect(box, QPen(Qt.PenStyle.NoPen), QBrush(QColor(0, 0, 0, 170)))
            # Kolejność rysowania: mapa (0) < tło podpisu (1) < podpis (2).
            background.setZValue(1)
            label.setZValue(2)

        self._draw_spawns(scene, z)

        if keep_view:
            return  # po kliknięciu w trybie wybierania mapa zostaje tam, gdzie była
        self._view.resetTransform()
        zoom = SPAWN_ZOOM if self._spawns else START_ZOOM
        self._view.scale(zoom, zoom)
        if self._focus is not None and self._focus.z == z:
            px, py = to_pixel(self._focus.x, self._focus.y)
            self._view.centerOn(px, py)


    def _draw_route_lines(self, scene: QGraphicsScene, z: int) -> None:
        # Linia tylko między sąsiednimi punktami z tego piętra; zmianę piętra pokazuje punkt „przejście”.
        # Ciemny spód pod kolorową linią: widać ją i na trawie, i na czerwonych ścianach.
        pens = (QPen(QColor(0, 0, 0, 200), 1.6), QPen(QColor(theme.ACCENT), 0.8))
        for start, end in zip(self._points, self._points[1:]):
            if start.z == end.z == z:
                # Przez zakręty drogi (Waypoint.path), jeśli są; inaczej prosto.
                tiles = [(start.x, start.y), *getattr(end, "path", []), (end.x, end.y)]
                line = QPainterPath()
                for index, (x, y) in enumerate(tiles):
                    px, py = to_pixel(x, y)
                    point = QPointF(px + 0.5, py + 0.5)
                    if index == 0:
                        line.moveTo(point)
                    else:
                        line.lineTo(point)
                # Rysowana przed kropkami, więc leży nad mapą, ale pod nimi i pod podpisami.
                for pen in pens:
                    scene.addPath(line, pen)

    def _draw_spawns(self, scene: QGraphicsScene, z: int) -> None:
        # Jedna ścieżka zamiast setek osobnych elementów: scena rysuje i przewija się szybciej.
        halo, dots = QPainterPath(), QPainterPath()
        for x, y, pz in self._spawns:
            if pz != z:
                continue
            px, py = to_pixel(x, y)
            center = QPointF(px + 0.5, py + 0.5)
            halo.addEllipse(_circle(center, SPAWN_HALO))
            dots.addEllipse(_circle(center, 0.9))
        if dots.isEmpty():
            return
        color = QColor(SPAWN_COLOR)
        halo_color = QColor(color)
        halo_color.setAlpha(90)
        halo.setFillRule(Qt.FillRule.WindingFill)  # nakładające się koła nie robią „dziur”
        scene.addPath(halo, QPen(Qt.PenStyle.NoPen), QBrush(halo_color)).setZValue(1)
        dots.setFillRule(Qt.FillRule.WindingFill)
        scene.addPath(dots, QPen(QColor("#000000"), 0.25), QBrush(color)).setZValue(2)
        if self._spawn_icon is not None:
            self._draw_spawn_icons(scene, z)

    def _draw_spawn_icons(self, scene: QGraphicsScene, z: int) -> None:
        # Jeden obrazek na kwadrat SPAWN_ICON_CELL kratek, w środku punktów z tego kwadratu.
        cells: dict[tuple[int, int], list[tuple[int, int]]] = {}
        for x, y, pz in self._spawns:
            if pz == z:
                cells.setdefault((x // SPAWN_ICON_CELL, y // SPAWN_ICON_CELL), []).append((x, y))
        for points in cells.values():
            px, py = to_pixel(sum(x for x, _ in points) // len(points), sum(y for _, y in points) // len(points))
            item = scene.addPixmap(self._spawn_icon)
            # Stały rozmiar na ekranie: obrazek nie rośnie razem z przybliżeniem mapy.
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
            item.setOffset(-SPAWN_ICON / 2, -SPAWN_ICON / 2)
            item.setPos(px + 0.5, py + 0.5)
            item.setZValue(3)


class MapWindow(QWidget):
    """MapPanel w osobnym oknie: edytor autora wskazuje w nim miejsce pinezki."""

    def __init__(self, maps_dir: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle("Mapa – TibiaHelper")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.resize(460, 420)
        self.panel = MapPanel(maps_dir)
        self.point_picked = self.panel.point_picked
        layout = QVBoxLayout(self)
        layout.addWidget(self.panel)

    def pick_point(self, points: list[MapPoint], start: MapPoint, route: bool = False) -> None:
        self.panel.pick_point(points, start, route)
        self.show()
        self.raise_()
        self.activateWindow()

    def update_points(self, points: list[MapPoint]) -> None:
        self.panel.update_points(points)
