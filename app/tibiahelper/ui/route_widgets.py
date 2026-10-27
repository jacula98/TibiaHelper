"""Trasa na mapie (do bossa, do miejsca huntu): lista punktów dla gracza i edytor dla autora.

Autor klika na mapie kolejne punkty drogi, a linia łączy je po kolei. Punkty z podpisem
(start, schody, sala bossa) gracz widzi na numerowanej liście; punkty bez podpisu to tylko zgięcia linii.
"""

from html import escape
from pathlib import Path

from PySide6.QtWidgets import QCheckBox, QDialog, QHBoxLayout, QListWidget, QPushButton, QVBoxLayout, QWidget

from ..core.i18n import tr
from ..core.mapdata import floor_label
from ..core.models import Waypoint
from . import theme
from .map_window import KIND_NAMES, MapWindow
from .quest_editor import DEFAULT_START, MarkerDialog

ROUTE_LINK_PREFIX = "route:"


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
        self._refresh()

    def route(self) -> list[dict]:
        return [dict(point) for point in self._route]

    def _refresh(self) -> None:
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
