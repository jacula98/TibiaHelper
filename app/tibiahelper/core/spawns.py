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

Point = tuple[int, int, int]


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
