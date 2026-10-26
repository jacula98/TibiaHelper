"""Okno mapy: mapa piętra Tibii z kropkami w miejscach z kroku questa.

Osobne okno (a nie strona w głównym), żeby można je było przesunąć obok
i powiększyć, nie zasłaniając kroków. Też jest zawsze na wierzchu.
"""

import logging
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPixmap, QWheelEvent
from PySide6.QtWidgets import (
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..core.mapdata import ensure_floor, floor_label, to_pixel
from ..core.models import MapPoint
from . import theme

log = logging.getLogger(__name__)

# Kolory kropek według rodzaju punktu.
KIND_COLORS = {
    "npc": "#4fc3f7",
    "place": theme.ACCENT,
    "passage": "#81c784",
    "use": "#ef5350",
}
KIND_NAMES = {"npc": "NPC", "place": "miejsce", "passage": "przejście", "use": "użyj"}
START_ZOOM = 4.0  # 1 kratka = 4 piksele na ekranie: widać okolicę, ale nie całą mapę
MIN_ZOOM, MAX_ZOOM = 0.5, 16.0
DOT_RADIUS = 1.6  # w kratkach mapy, więc kropka rośnie razem z przybliżeniem
RING_RADIUS = 3.5  # obwódka wokół kropki, żeby od razu rzucała się w oczy


def _circle(center: QPointF, radius: float) -> QRectF:
    return QRectF(center.x() - radius, center.y() - radius, radius * 2, radius * 2)


class _FloorLoader(QObject):
    """Pobiera piętro w tle i oddaje wynik do wątku okna sygnałem."""

    loaded = Signal(int, str)  # piętro, ścieżka do PNG
    failed = Signal(int, str)  # piętro, opis błędu


class MapView(QGraphicsView):
    """Widok mapy: kółko myszy przybliża, przeciąganie przesuwa."""

    def __init__(self) -> None:
        super().__init__()
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

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802 (nazwa z Qt)
        factor = 1.25 if event.angleDelta().y() > 0 else 0.8
        zoom = self.transform().m11() * factor
        if MIN_ZOOM <= zoom <= MAX_ZOOM:
            self.scale(factor, factor)


class MapWindow(QWidget):
    def __init__(self, maps_dir: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle("Mapa – TibiaHelper")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.resize(460, 420)

        self._maps_dir = maps_dir
        self._points: list[MapPoint] = []
        self._focus: MapPoint | None = None
        self._floor = 7
        self._loading: set[int] = set()

        self._loader = _FloorLoader()
        self._loader.loaded.connect(self._on_floor_loaded)
        self._loader.failed.connect(self._on_floor_failed)

        self._title = QLabel()
        self._title.setObjectName("title")
        self._title.setWordWrap(True)
        self._legend = QLabel()
        self._legend.setObjectName("muted")
        self._legend.setWordWrap(True)

        up = QToolButton(text="▲")
        up.setToolTip("Piętro wyżej")
        up.clicked.connect(lambda: self._change_floor(-1))
        down = QToolButton(text="▼")
        down.setToolTip("Piętro niżej")
        down.clicked.connect(lambda: self._change_floor(+1))
        self._floor_label = QLabel()

        self._view = MapView()
        hint = QLabel("Kółko myszy: przybliżenie · przeciągnij: przesuwanie")
        hint.setObjectName("muted")
        self._status = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self._status.setObjectName("muted")
        self._status.setWordWrap(True)

        floors = QHBoxLayout()
        floors.addWidget(QLabel("Piętro:"))
        floors.addWidget(self._floor_label)
        floors.addStretch(1)
        floors.addWidget(up)
        floors.addWidget(down)

        layout = QVBoxLayout(self)
        layout.addWidget(self._title)
        layout.addWidget(self._legend)
        layout.addLayout(floors)
        layout.addWidget(self._view, 1)
        layout.addWidget(self._status)
        layout.addWidget(hint)

    def show_points(self, points: list[MapPoint], focus: MapPoint) -> None:
        """Pokazuje punkty jednego kroku i centruje mapę na klikniętym."""
        self._points = points
        self._focus = focus
        self._title.setText(focus.label)
        self._legend.setText(f"{KIND_NAMES[focus.kind]} · x {focus.x}, y {focus.y}")
        self._set_floor(focus.z)
        self.show()
        self.raise_()
        self.activateWindow()

    def _change_floor(self, delta: int) -> None:
        self._set_floor(max(0, min(15, self._floor + delta)))

    def _set_floor(self, z: int) -> None:
        self._floor = z
        self._floor_label.setText(f"{floor_label(z)}  (z={z})")
        self._view.scene().clear()
        path = self._maps_dir / f"floor-{z:02d}-map.png"
        if path.exists():
            self._draw(z, path)
            return
        self._status.setText("Pobieram mapę tego piętra (tylko za pierwszym razem)…")
        self._status.show()
        if z not in self._loading:
            self._loading.add(z)
            # daemon=True: zamknięcie programu nie czeka na pobieranie.
            threading.Thread(target=self._load_floor, args=(z,), daemon=True).start()

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
            self._status.setText("Nie udało się pobrać mapy. Sprawdź internet i otwórz mapę ponownie.")

    def _draw(self, z: int, path: Path) -> None:
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            # Uszkodzony plik: kasujemy, żeby przy następnym otwarciu pobrać go od nowa.
            path.unlink(missing_ok=True)
            self._status.setText("Plik mapy był uszkodzony. Otwórz mapę ponownie, żeby go pobrać.")
            return
        self._status.hide()
        scene = self._view.scene()
        scene.clear()
        scene.addPixmap(pixmap)
        scene.setSceneRect(pixmap.rect())

        font = QFont()
        font.setPixelSize(3)
        for point in self._points:
            if point.z != z:
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

        self._view.resetTransform()
        self._view.scale(START_ZOOM, START_ZOOM)
        if self._focus is not None and self._focus.z == z:
            px, py = to_pixel(self._focus.x, self._focus.y)
            self._view.centerOn(px, py)
