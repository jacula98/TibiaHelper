"""Trasa na mapie (do bossa, do miejsca huntu): lista punktów dla gracza i edytor dla autora.

Autor klika na mapie kolejne punkty drogi, a linia łączy je po kolei. Punkty z podpisem
(start, schody, sala bossa) gracz widzi na numerowanej liście; punkty bez podpisu to tylko zgięcia linii.

Między punktami na tym samym piętrze edytor sam liczy drogę po kratkach, którymi da się przejść
(obrazek „path” z tibiamaps), i zapisuje jej zakręty w Waypoint.path. Gracz dostaje gotową linię,
bez pobierania obrazka i bez liczenia.
"""

import logging
import threading
from html import escape
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QCheckBox, QDialog, QHBoxLayout, QLabel, QListWidget, QPushButton, QVBoxLayout, QWidget

from ..core.i18n import tr
from ..core.mapdata import ensure_floor, floor_label, to_pixel
from ..core.models import Waypoint
from ..core.pathfinding import Cost, corners, find_path, nearest_walkable
from . import theme
from .map_window import KIND_NAMES, MapWindow
from .quest_editor import DEFAULT_START, MarkerDialog

log = logging.getLogger(__name__)

ROUTE_LINK_PREFIX = "route:"
# Obrazek „path” z tibiamaps: żółty = nie da się przejść, odcienie szarości = jak wolno się idzie.
UNWALKABLE = 0xFFFF00
Segment = tuple[int, int, int, int, int]  # x1, y1, x2, y2, z: odcinek drogi na jednym piętrze


def walk_cost(image: QImage) -> Cost:
    """Koszt kratki z obrazka „path” (współrzędne z gry). Szary 100 (zwykła droga) = 1.0."""

    def cost(x: int, y: int) -> float | None:
        px, py = to_pixel(x, y)
        if not (0 <= px < image.width() and 0 <= py < image.height()):
            return None
        rgb = image.pixel(px, py) & 0xFFFFFF
        red, green, blue = rgb >> 16, (rgb >> 8) & 0xFF, rgb & 0xFF
        # Tylko odcienie szarości to znane przejścia; żółty i inne kolory (np. nieodkryte) omijamy.
        if rgb == UNWALKABLE or not red == green == blue:
            return None
        return max(1.0, red / 100)

    return cost


def segment_path(maps_dir: Path, segment: Segment) -> list[tuple[int, int]] | None:
    """Zakręty drogi na odcinku ([] = droga jest prosta) albo None, gdy drogi nie znaleziono."""
    x1, y1, x2, y2, z = segment
    try:
        image = QImage(str(ensure_floor(maps_dir, z, layer="path")))
    except (OSError, ValueError) as exc:
        log.info("Bez obrazka przejść piętra %s: %s", z, exc)
        return None
    if image.isNull():
        return None
    cost = walk_cost(image)
    start, end = nearest_walkable((x1, y1), cost), nearest_walkable((x2, y2), cost)
    if start is None or end is None:
        return None
    path = find_path(start, end, cost)
    if path is None:
        return None
    # Punkty mogły trafić obok drogi: linia i tak zaczyna się i kończy w klikniętych miejscach.
    tiles = [(x1, y1), *path, (x2, y2)]
    return corners([t for i, t in enumerate(tiles) if i == 0 or t != tiles[i - 1]])


def _segment(start: dict, end: dict) -> Segment | None:
    if start["z"] != end["z"]:
        return None  # zmiana piętra: linii i tak nie rysujemy
    return (start["x"], start["y"], end["x"], end["y"], end["z"])


class _PathWorker(QObject):
    """Liczy drogi w jednym wątku w tle (A* trwa do 1-2 s), po kolei, żeby nie obciążać komputera."""

    done = Signal(object, object)  # Segment, zakręty

    def __init__(self, maps_dir: Path, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._maps_dir = maps_dir
        self._queue: list[Segment] = []
        self._lock = threading.Lock()
        self._running = False

    def add(self, segment: Segment) -> None:
        with self._lock:
            if segment in self._queue:
                return
            self._queue.append(segment)
            if self._running:
                return
            self._running = True
        threading.Thread(target=self._work, daemon=True, name="route-path").start()

    def _work(self) -> None:
        while True:
            with self._lock:
                if not self._queue:
                    self._running = False
                    return
                segment = self._queue[0]
            path = segment_path(self._maps_dir, segment)
            with self._lock:
                self._queue.remove(segment)
            self.done.emit(segment, path)  # sygnał przenosi wynik do wątku okna


def numbered(route: list[Waypoint]) -> list[Waypoint]:
    """Numery w podpisach („1. Start”), żeby na mapie było widać kolejność. Punkty drogi bez podpisu zostają bez."""
    result, number = [], 0
    for point in route:
        if point.label:
            number += 1
            point = point.model_copy(update={"label": f"{number}. {point.label}"})
        result.append(point)
    return result


def route_html(route: list[Waypoint]) -> str:
    """Podpisane punkty trasy po kolei; klik przenosi mapę pod spodem na miejsce i piętro punktu.

    Link ma indeks z całej trasy (z punktami drogi), bo tak szuka go strona z mapą.
    """
    rows = []
    for index, point in enumerate(route):
        if not point.label:
            continue
        rows.append(
            f'{len(rows) + 1}. <a href="{ROUTE_LINK_PREFIX}{index}" style="color: {theme.ACCENT};">{escape(point.label)}</a>'
            f' <span style="color: {theme.MUTED};">({escape(tr(KIND_NAMES[point.kind]))}, '
            f'{escape(tr("piętro: {floor}", floor=floor_label(point.z)))})</span>'
        )
    return "<br>".join(rows)


class RouteEditor(QWidget):
    """Tryb autora: lista punktów trasy, przyciski i mapa do klikania. route() zwraca punkty jak w quests.json."""

    def __init__(self, route: list[dict], maps_dir: Path, hint: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._route = [dict(point) for point in route]
        self._maps_dir = maps_dir
        # Policzone drogi: przy przesuwaniu punktów nie liczymy tego samego odcinka drugi raz.
        # None = drogi nie znaleziono (np. zamknięte przejście): zostaje prosta linia.
        self._paths: dict[Segment, list | None] = {}
        for start, end in zip(self._route, self._route[1:]):
            segment = _segment(start, end)
            if segment is not None and end.get("path"):
                self._paths[segment] = end["path"]
        self._worker = _PathWorker(maps_dir, self)
        self._worker.done.connect(self._on_path)
        self._pending = 0
        self._status = QLabel()
        self._status.setObjectName("muted")
        self._map: MapWindow | None = None
        self._list = QListWidget()
        self._list.setMinimumHeight(110)
        buttons = QHBoxLayout()
        for text, slot in (
            ("📍 Dodaj punkt", self._add_point),
            ("↑", lambda: self._move_point(-1)),
            ("↓", lambda: self._move_point(+1)),
            ("Usuń", self._remove_point),
        ):
            button = QPushButton(text)
            button.clicked.connect(slot)
            buttons.addWidget(button)
        buttons.addStretch(1)
        # Szybkie klikanie: każdy klik na mapie to punkt drogi (bez okienka); mapa zostaje otwarta.
        self._quick = QCheckBox("Szybkie klikanie drogi (bez podpisów)")
        self._quick.setChecked(True)
        self._quick.setToolTip(
            "Włączone: klikasz po mapie kolejne punkty drogi, linia je łączy.\n"
            f"Wyłączone: po kliknięciu podajesz podpis i rodzaj ({hint})."
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._list)
        layout.addLayout(buttons)
        layout.addWidget(self._quick)
        layout.addWidget(self._status)
        self._refresh()

    def route(self) -> list[dict]:
        return [dict(point) for point in self._route]

    def _apply_paths(self) -> None:
        """Wpisuje policzone drogi do punktów, a brakujące odcinki zleca do policzenia w tle."""
        waiting, failed = 0, []
        for index, point in enumerate(self._route):
            segment = _segment(self._route[index - 1], point) if index else None
            path: list | None = []
            if segment is not None and segment not in self._paths:
                waiting += 1
                self._worker.add(segment)  # do czasu policzenia: prosta linia
            elif segment is not None:
                path = self._paths[segment]
                if path is None:
                    failed.append(str(index + 1))
            if path:
                point["path"] = [list(p) for p in path]
            else:
                point.pop("path", None)
        self._pending = waiting
        if waiting:
            self._status.setText(f"Liczę drogę po mapie… (odcinki: {waiting})")
        elif failed:
            self._status.setText(
                f"Nie znalazłem przejścia do punktów: {', '.join(failed)} (linia prosta). Dodaj punkt pośredni."
            )
        else:
            self._status.setText("")

    def _on_path(self, segment: Segment, path: list | None) -> None:
        self._paths[segment] = path
        self._refresh()

    def is_busy(self) -> bool:
        """True, gdy jakaś droga jeszcze się liczy (zapis teraz da na tym odcinku prostą linię)."""
        return self._pending > 0

    def _refresh(self) -> None:
        self._apply_paths()
        if self._map is not None and self._map.isVisible():
            self._map.update_points(self._waypoints())
        self._list.clear()
        for number, point in enumerate(self._route, start=1):
            floor = f"piętro {floor_label(point['z'])}"
            if point.get("label"):
                kind = KIND_NAMES[point.get("kind", "place")]
                self._list.addItem(f"{number}. {point['label']} ({kind}, {floor})")
            else:
                self._list.addItem(f"{number}. · droga ({floor})")

    def _waypoints(self) -> list[Waypoint]:
        return [Waypoint.model_validate(p) for p in self._route]

    def _add_point(self) -> None:
        points = self._waypoints()
        start = points[-1] if points else DEFAULT_START
        if self._map is None:
            self._map = MapWindow(self._maps_dir, self)
            self._map.point_picked.connect(self._on_point_picked)
        self._map.pick_point(points, start, route=True)

    def _on_point_picked(self, x: int, y: int, z: int) -> None:
        point = {"x": x, "y": y, "z": z}
        if not self._quick.isChecked():
            # To samo okienko co przy pinezce w queście: podpis i rodzaj punktu.
            dialog = MarkerDialog("", self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            point.update(label=dialog.label(), kind=dialog.kind())
        self._route.append(point)
        # Mapa zostaje otwarta i w tym samym miejscu (_refresh ją odświeża): następny klik to następny punkt.
        self._refresh()
        self._list.setCurrentRow(len(self._route) - 1)

    def _move_point(self, delta: int) -> None:
        row = self._list.currentRow()
        target = row + delta
        if 0 <= row < len(self._route) and 0 <= target < len(self._route):
            self._route[row], self._route[target] = self._route[target], self._route[row]
            self._refresh()
            self._list.setCurrentRow(target)

    def _remove_point(self) -> None:
        row = self._list.currentRow()
        if 0 <= row < len(self._route):
            del self._route[row]
            self._refresh()
