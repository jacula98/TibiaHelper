"""Miejsca występowania potworów (data/spawns.json, źródło: tibiaroute.com).

Za zgodą TibiaRoute (docs/zrodla-danych.md). Warunek: przy tych danych
i w ustawieniach pokazujemy „Źródło danych: tibiaroute.com”.
Plik jest osobno od quests.json, bo ma ok. 80 tys. punktów i inne źródło.
"""

import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .models import MAP_X_MAX, MAP_X_MIN, MAP_Y_MAX, MAP_Y_MIN

log = logging.getLogger(__name__)

SOURCE_NOTE = "Źródło danych: tibiaroute.com"
CLUSTER = 64  # kratki: wielkość kwadratu, w którym szukamy największego skupiska
PLACE_CELL = 32  # kratki: punkty w sąsiednich kwadratach tej wielkości to jedno miejsce (expowisko)

# Świątynie miast (x, y): podpisujemy miejsce najbliższym miastem, np. „okolice Thais”.
CITIES = {
    "Ab'Dendriel": (32732, 31634),
    "Ankrahmun": (33194, 32853),
    "Carlin": (32360, 31782),
    "Darashia": (33213, 32454),
    "Dawnport": (32064, 31894),
    "Edron": (33217, 31814),
    "Farmine": (33023, 31521),
    "Gray Beach": (33447, 31323),
    "Issavi": (33921, 31477),
    "Kazordoon": (32649, 31925),
    "Krailos": (33657, 31665),
    "Liberty Bay": (32317, 32826),
    "Marapur": (33776, 32754),
    "Port Hope": (32595, 32746),
    "Rathleton": (33594, 31899),
    "Rookgaard": (32097, 32219),
    "Roshamuul": (33513, 32363),
    "Svargrond": (32212, 31132),
    "Thais": (32369, 32241),
    "Venore": (32957, 32076),
    "Yalahar": (32787, 31276),
}

Point = tuple[int, int, int]


@dataclass(frozen=True)
class Place:
    """Jedno skupisko potworów (expowisko): środek na piętrze, gdzie jest ich najwięcej."""

    x: int
    y: int
    z: int
    count: int
    city: str


@dataclass(frozen=True)
class Spawns:
    version: int = 0
    monsters: dict[str, list[Point]] = field(default_factory=dict)

    def of(self, monster_id: str) -> list[Point]:
        return self.monsters.get(monster_id, [])


def _valid(point: object) -> bool:
    return (
        isinstance(point, list)
        and len(point) == 3
        and all(isinstance(v, int) for v in point)
        and MAP_X_MIN <= point[0] <= MAP_X_MAX
        and MAP_Y_MIN <= point[1] <= MAP_Y_MAX
        and 0 <= point[2] <= 15
    )


def parse_spawns(raw: object) -> Spawns:
    """Waliduje JSON; złe punkty pomija, zły plik daje pusty wynik (mapy wtedy po prostu nie ma)."""
    if not isinstance(raw, dict) or not isinstance(raw.get("monsters"), dict):
        raise ValueError("Plik spawns.json ma zły format")
    version = raw.get("version")
    monsters = {
        str(monster_id): [tuple(p) for p in points if _valid(p)]
        for monster_id, points in raw["monsters"].items()
        if isinstance(points, list)
    }
    return Spawns(version if isinstance(version, int) else 0, monsters)


def load_spawns(*paths: Path) -> Spawns:
    """Najnowsza poprawna kopia z podanych plików (wbudowana, pobrana)."""
    best = Spawns()
    for path in paths:
        if not path.exists():
            continue
        try:
            spawns = parse_spawns(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            log.warning("Pominięto %s: %s", path, exc)
            continue
        if spawns.version > best.version or not best.monsters:
            best = spawns
    return best


def floors(points: list[Point]) -> list[tuple[int, int]]:
    """(piętro, liczba punktów) od piętra z największą liczbą punktów."""
    return Counter(z for _, _, z in points).most_common()


def busiest_spot(points: list[Point], z: int) -> tuple[int, int] | None:
    """Środek największego skupiska na piętrze z: tam centrujemy mapę na start."""
    on_floor = [(x, y) for x, y, pz in points if pz == z]
    if not on_floor:
        return None
    cells = Counter((x // CLUSTER, y // CLUSTER) for x, y in on_floor)
    cell = cells.most_common(1)[0][0]
    inside = [(x, y) for x, y in on_floor if (x // CLUSTER, y // CLUSTER) == cell]
    return sum(x for x, _ in inside) // len(inside), sum(y for _, y in inside) // len(inside)


def nearest_city(x: int, y: int) -> str:
    return min(CITIES, key=lambda name: (CITIES[name][0] - x) ** 2 + (CITIES[name][1] - y) ** 2)


def places(points: list[Point]) -> list[Place]:
    """Skupiska punktów (od największego): sąsiednie kwadraty PLACE_CELL łączymy w jedno miejsce.

    Piętra przy łączeniu pomijamy, bo jedno expowisko często ma kilka pięter (np. jaskinia pod wejściem).
    """
    cells: dict[tuple[int, int], list[Point]] = {}
    for point in points:
        cells.setdefault((point[0] // PLACE_CELL, point[1] // PLACE_CELL), []).append(point)
    seen: set[tuple[int, int]] = set()
    result = []
    for start in cells:
        if start in seen:
            continue
        # Przeszukiwanie sąsiadów (także po skosie), aż skupisko się skończy.
        seen.add(start)
        stack, group = [start], []
        while stack:
            cx, cy = stack.pop()
            group.extend(cells[(cx, cy)])
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    neighbour = (cx + dx, cy + dy)
                    if neighbour in cells and neighbour not in seen:
                        seen.add(neighbour)
                        stack.append(neighbour)
        z = floors(group)[0][0]
        x, y = busiest_spot(group, z)
        result.append(Place(x, y, z, len(group), nearest_city(x, y)))
    return sorted(result, key=lambda p: (-p.count, p.city))
