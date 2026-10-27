"""Testy drogi po mapie (A*): linia trasy omija ściany zamiast iść na przestrzał."""

import pytest

from tibiahelper.core.models import Waypoint
from tibiahelper.core.pathfinding import corners, find_path, nearest_walkable

# Mała mapa: # = ściana, . = droga. Z lewej na prawą trzeba przejść dziurą na dole.
MAP = [
    ".....#.....",
    ".....#.....",
    ".....#.....",
    "...........",
]


def cost(x: int, y: int) -> float | None:
    if 0 <= y < len(MAP) and 0 <= x < len(MAP[0]):
        return None if MAP[y][x] == "#" else 1.0
    return None


def test_path_goes_around_the_wall():
    path = find_path((0, 0), (10, 0), cost)
    assert path is not None and path[0] == (0, 0) and path[-1] == (10, 0)
    assert all(cost(x, y) is not None for x, y in path)
    assert (5, 3) in path  # jedyne przejście przez ścianę
    assert corners(path)  # zakręty do zapisania w danych


def test_no_path_and_click_next_to_the_road():
    walled = lambda x, y: None if x == 5 else cost(x, y)  # noqa: E731 (ściana na całej wysokości)
    assert find_path((0, 0), (10, 0), walled) is None
    assert nearest_walkable((5, 1), cost) in {(4, 0), (4, 1), (4, 2), (6, 0), (6, 1), (6, 2)}
    assert nearest_walkable((5, 1), lambda x, y: None) is None


def test_waypoint_path_must_be_on_map():
    point = Waypoint(x=32369, y=32241, z=7, path=[(32370, 32241)])
    assert point.path == [(32370, 32241)]
    with pytest.raises(ValueError, match="poza mapą"):
        Waypoint(x=32369, y=32241, z=7, path=[(1, 1)])
