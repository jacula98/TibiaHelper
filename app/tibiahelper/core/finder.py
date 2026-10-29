"""Exiva finder: gdzie może być potwór (np. fiendish) albo gracz z odczytów czaru exiva. Bez Qt, żeby łatwo testować.

Find Person („exiva "nick"”) i Find Fiend („exiva moe res”) mówią tylko kierunek i przybliżoną
odległość. Zasady (TibiaWiki, strona Find Person, CC BY-SA), dx i dy to różnica w kratkach:

- odległość to większa z |dx| i |dy|: 0-4 „next to you”, 5-100 „to the north”,
  101-250 „far to the north”, 251 i więcej „very far to the north”,
- piętro mówi tylko przy 0-100 kratkach („above you”, „on a higher level to the north”),
- kierunek to jeden z 8 wycinków po 45° (granice co 22,5° od osi).

Jeden odczyt to więc „kawałek pierścienia” wokół gracza. Kilka odczytów z różnych miejsc
zawęża obszar: potwór musi być w części wspólnej wszystkich kawałków.

Kawałki trzymamy jako wielokąty wypukłe (łatwo je przecinać i rysować) we współrzędnych gry,
gdzie kratka (x, y) to kwadrat od x do x+1 i od y do y+1. Dzięki temu obszar jest dokładny
i nie trzeba sprawdzać milionów kratek mapy po kolei.
"""

import math
from dataclasses import dataclass
from typing import Literal

from .models import MAP_X_MAX, MAP_X_MIN, MAP_Y_MAX, MAP_Y_MIN

Direction = Literal["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
Distance = Literal["beside", "close", "far", "very_far"]
FloorHint = Literal["same", "up", "down"]  # „up” = potwór jest wyżej (mniejsze z)

DIRECTIONS: tuple[Direction, ...] = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
BESIDE_MAX, CLOSE_MAX, FAR_MAX = 4, 100, 250
FLOORS = range(16)
# Kąt środka wycinka (w stopniach, 0 = wschód, przeciwnie do zegara). Na mapie północ to mniejsze y.
_ANGLES = {"E": 0, "NE": 45, "N": 90, "NW": 135, "W": 180, "SW": 225, "S": 270, "SE": 315}
_TAN_22 = math.tan(math.pi / 8)  # granica między „wschód” a „północny wschód”
_FAR_AWAY = 10_000.0  # dalej niż cała mapa: „very far” i ramiona wycinka nie mają końca

Point = tuple[float, float]
Polygon = list[Point]


@dataclass(frozen=True)
class Reading:
    """Jeden odczyt: gdzie stał gracz i co powiedział czar."""

    x: int
    y: int
    z: int
    distance: Distance
    direction: Direction | None = None  # przy „beside” czar nie mówi kierunku
    floor: FloorHint = "same"


@dataclass(frozen=True)
class Area:
    """Gdzie może być cel: wielokąty na mapie (te same na każdym piętrze) i możliwe piętra."""

    polygons: tuple[Polygon, ...]
    floors: frozenset[int]

    @property
    def empty(self) -> bool:
        return not self.polygons or not self.floors

    @property
    def tiles(self) -> int:
        """Przybliżona liczba kratek na jednym piętrze."""
        return round(sum(_area(p) for p in self.polygons))

    def contains(self, x: int, y: int, z: int) -> bool:
        """Czy kratka (x, y, z) jest w obszarze (sprawdzamy jej środek)."""
        return z in self.floors and any(_inside(p, (x + 0.5, y + 0.5)) for p in self.polygons)

    def bounds(self) -> tuple[float, float, float, float] | None:
        """Prostokąt (x_min, y_min, x_max, y_max) wokół całego obszaru albo None, gdy pusty."""
        points = [point for polygon in self.polygons for point in polygon]
        if not points:
            return None
        xs, ys = [x for x, _ in points], [y for _, y in points]
        return min(xs), min(ys), max(xs), max(ys)


def distance_of(dx: int, dy: int) -> Distance:
    steps = max(abs(dx), abs(dy))
    if steps <= BESIDE_MAX:
        return "beside"
    if steps <= CLOSE_MAX:
        return "close"
    return "far" if steps <= FAR_MAX else "very_far"


def direction_of(dx: int, dy: int) -> Direction | None:
    """Kierunek z różnicy kratek (dy > 0 to południe, jak na mapie Tibii)."""
    if dx == 0 and dy == 0:
        return None
    if abs(dy) < _TAN_22 * abs(dx):
        return "E" if dx > 0 else "W"
    if abs(dx) < _TAN_22 * abs(dy):
        return "S" if dy > 0 else "N"
    return ("S" if dy > 0 else "N") + ("E" if dx > 0 else "W")  # type: ignore[return-value]


def floors_of(reading: Reading) -> frozenset[int]:
    """Piętra, na których może być cel. Daleko czar nie mówi o piętrze, więc może być każde."""
    if reading.distance in ("far", "very_far"):
        return frozenset(FLOORS)
    if reading.floor == "up":
        return frozenset(range(reading.z))
    if reading.floor == "down":
        return frozenset(range(reading.z + 1, 16))
    return frozenset({reading.z})


def matches(reading: Reading, x: int, y: int, z: int) -> bool:
    """Czy cel na kratce (x, y, z) dałby taki odczyt. Wzorzec, z którym testy porównują wielokąty."""
    dx, dy = x - reading.x, y - reading.y
    if z not in floors_of(reading) or distance_of(dx, dy) != reading.distance:
        return False
    return reading.distance == "beside" or direction_of(dx, dy) == reading.direction


def reading_polygons(reading: Reading) -> list[Polygon]:
    """Kawałek mapy z jednego odczytu jako wielokąty wypukłe (pierścień przycięty do wycinka i mapy)."""
    cx, cy = reading.x + 0.5, reading.y + 0.5  # środek kratki gracza
    # Pierścień między kwadratami: kratki od inner+1 do outer od gracza (krawędź kratki to +-0,5).
    inner, outer = {
        "beside": (-1.0, BESIDE_MAX + 0.5),
        "close": (BESIDE_MAX + 0.5, CLOSE_MAX + 0.5),
        "far": (CLOSE_MAX + 0.5, FAR_MAX + 0.5),
        "very_far": (FAR_MAX + 0.5, _FAR_AWAY),
    }[reading.distance]
    pieces = _ring(cx, cy, inner, outer)
    if reading.distance != "beside":
        if reading.direction not in _ANGLES:
            return []
        cone = _cone(cx, cy, _ANGLES[reading.direction])
        pieces = [_clip(piece, cone) for piece in pieces]
    world = _rect(MAP_X_MIN, MAP_Y_MIN, MAP_X_MAX + 1, MAP_Y_MAX + 1)
    return [p for p in (_clip(piece, world) for piece in pieces) if _area(p) > 1e-6]


def possible_area(readings: list[Reading]) -> Area | None:
    """Część wspólna wszystkich odczytów. None, gdy nie ma jeszcze żadnego."""
    if not readings:
        return None
    polygons = reading_polygons(readings[0])
    floors = floors_of(readings[0])
    for reading in readings[1:]:
        # Kawałki jednego odczytu na siebie nie zachodzą, więc przecięcia par też nie.
        others = reading_polygons(reading)
        polygons = [p for a in polygons for b in others if _area(p := _clip(a, b)) > 1e-6]
        floors &= floors_of(reading)
    return Area(tuple(polygons), floors)


def floor_ranges(floors: frozenset[int]) -> list[tuple[int, int]]:
    """Piętra jako ciągłe przedziały, np. {5, 6, 7, 10} -> [(5, 7), (10, 10)]."""
    ranges: list[tuple[int, int]] = []
    for z in sorted(floors):
        if ranges and ranges[-1][1] == z - 1:
            ranges[-1] = (ranges[-1][0], z)
        else:
            ranges.append((z, z))
    return ranges


# --- geometria --------------------------------------------------------------


def _rect(x0: float, y0: float, x1: float, y1: float) -> Polygon:
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def _ring(cx: float, cy: float, inner: float, outer: float) -> list[Polygon]:
    if inner < 0:  # pełny kwadrat bez dziury
        return [_rect(cx - outer, cy - outer, cx + outer, cy + outer)]
    return [
        _rect(cx - outer, cy - outer, cx + outer, cy - inner),  # góra
        _rect(cx - outer, cy + inner, cx + outer, cy + outer),  # dół
        _rect(cx - outer, cy - inner, cx - inner, cy + inner),  # lewo
        _rect(cx + inner, cy - inner, cx + outer, cy + inner),  # prawo
    ]


def _cone(cx: float, cy: float, angle: float) -> Polygon:
    """Wycinek 45° wokół kąta jako czworokąt wypukły. Minus przy y: na mapie północ jest w górę."""
    def ray(degrees: float, length: float) -> Point:
        radians = math.radians(degrees)
        return cx + length * math.cos(radians), cy - length * math.sin(radians)

    # Środek, dwa ramiona i punkt dalej na osi: wycinek „bez końca” w granicach mapy.
    return [(cx, cy), ray(angle - 22.5, _FAR_AWAY), ray(angle, _FAR_AWAY * 2), ray(angle + 22.5, _FAR_AWAY)]


def _signed_area(polygon: Polygon) -> float:
    return sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(polygon, polygon[1:] + polygon[:1])) / 2


def _area(polygon: Polygon) -> float:
    return abs(_signed_area(polygon)) if len(polygon) >= 3 else 0.0


def _cross(a: Point, b: Point, p: Point) -> float:
    return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])


def _inside(polygon: Polygon, point: Point) -> bool:
    # W wielokącie wypukłym punkt leży po tej samej stronie każdej krawędzi.
    sign = 1 if _signed_area(polygon) > 0 else -1
    return all(sign * _cross(a, b, point) > 0 for a, b in zip(polygon, polygon[1:] + polygon[:1]))


def _clip(subject: Polygon, clip: Polygon) -> Polygon:
    """Część wspólna dwóch wielokątów wypukłych (algorytm Sutherlanda-Hodgmana)."""
    if len(subject) < 3 or len(clip) < 3:
        return []
    sign = 1 if _signed_area(clip) > 0 else -1
    output = subject
    for a, b in zip(clip, clip[1:] + clip[:1]):
        if not output:
            break
        points, output = output, []
        for p, q in zip(points, points[1:] + points[:1]):
            p_in, q_in = sign * _cross(a, b, p) >= 0, sign * _cross(a, b, q) >= 0
            if p_in:
                output.append(p)
            if p_in != q_in:
                # Punkt, w którym bok p-q przecina krawędź a-b.
                cp, cq = _cross(a, b, p), _cross(a, b, q)
                t = cp / (cp - cq)
                output.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
    return output
