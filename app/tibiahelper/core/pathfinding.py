"""Trasa po kratkach, którymi da się przejść (A*), żeby linia na mapie szła drogami, a nie na skos.

Bez Qt: koszt kratki podaje funkcja `cost` (w aplikacji czyta ją z obrazka „path” z tibiamaps).
Szukamy tylko w prostokącie wokół dwóch punktów (z zapasem), żeby nie przeszukiwać całej mapy.
"""

import heapq
import math
from collections.abc import Callable

# None = nie da się przejść; liczba = jak wolno się idzie (1.0 = zwykła droga).
Cost = Callable[[int, int], float | None]

MARGIN = 80  # kratki zapasu wokół prostokąta start-cel (droga bywa naokoło)
MAX_NODES = 400_000  # ok. 1-2 s w Pythonie; dalej szukanie przerywamy
DIAGONAL = 1.5  # krok na skos jest dłuższy (w grze też trwa dłużej)
_STEPS = [(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy]


def find_path(start: tuple[int, int], end: tuple[int, int], cost: Cost, margin: int = MARGIN) -> list[tuple[int, int]] | None:
    """Kratki od start do end (włącznie z oboma) albo None, gdy nie ma przejścia w okolicy."""
    if start == end:
        return [start]
    left, right = min(start[0], end[0]) - margin, max(start[0], end[0]) + margin
    top, bottom = min(start[1], end[1]) - margin, max(start[1], end[1]) + margin

    def heuristic(node: tuple[int, int]) -> float:
        # Odległość bez przeszkód; najtańsza kratka kosztuje 1, więc nie przeszacowujemy.
        dx, dy = abs(node[0] - end[0]), abs(node[1] - end[1])
        return max(dx, dy) + (DIAGONAL - 1) * min(dx, dy)

    best = {start: 0.0}
    came: dict[tuple[int, int], tuple[int, int]] = {}
    queue = [(heuristic(start), 0.0, start)]
    visited = 0
    while queue:
        _, distance, node = heapq.heappop(queue)
        if node == end:
            return _walk_back(came, end)
        if distance > best.get(node, math.inf):
            continue  # stary wpis w kolejce, mamy już krótszą drogę
        visited += 1
        if visited > MAX_NODES:
            return None
        for dx, dy in _STEPS:
            nx, ny = node[0] + dx, node[1] + dy
            if not (left <= nx <= right and top <= ny <= bottom):
                continue
            step = cost(nx, ny)
            if step is None:
                continue
            if dx and dy:
                # Bez ścinania rogów: na skos tylko wtedy, gdy obie kratki obok też są wolne.
                if cost(node[0] + dx, node[1]) is None or cost(node[0], node[1] + dy) is None:
                    continue
                step *= DIAGONAL
            new = distance + step
            if new < best.get((nx, ny), math.inf):
                best[(nx, ny)] = new
                came[(nx, ny)] = node
                heapq.heappush(queue, (new + heuristic((nx, ny)), new, (nx, ny)))
    return None


def nearest_walkable(point: tuple[int, int], cost: Cost, radius: int = 3) -> tuple[int, int] | None:
    """Ta sama kratka albo najbliższa wolna (klik na mapie trafia czasem w ścianę obok drogi)."""
    for distance in range(radius + 1):
        ring = [
            (point[0] + dx, point[1] + dy)
            for dx in range(-distance, distance + 1)
            for dy in range(-distance, distance + 1)
            if max(abs(dx), abs(dy)) == distance
        ]
        for tile in ring:
            if cost(*tile) is not None:
                return tile
    return None


def _walk_back(came: dict, end: tuple[int, int]) -> list[tuple[int, int]]:
    path = [end]
    while path[-1] in came:
        path.append(came[path[-1]])
    return path[::-1]


def corners(path: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Tylko kratki, w których droga skręca (bez początku i końca): mniej danych w pliku, ta sama linia."""
    result = []
    for before, here, after in zip(path, path[1:], path[2:]):
        if (here[0] - before[0], here[1] - before[1]) != (after[0] - here[0], after[1] - here[1]):
            result.append(here)
    return result
