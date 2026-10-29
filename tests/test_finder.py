"""Testy Exiva findera: zasady odległości i kierunków oraz zawężanie obszaru kolejnymi odczytami."""

import random

import pytest

from tibiahelper.core.finder import (
    Reading,
    direction_of,
    distance_of,
    floor_ranges,
    candidates,
    floors_of,
    matches,
    message,
    possible_area,
)
from tibiahelper.core.models import MAP_X_MAX, MAP_X_MIN, MAP_Y_MAX, MAP_Y_MIN, Monster
from tibiahelper.core.spawns import Spawns

THAIS = (32369, 32241, 7)


@pytest.mark.parametrize(
    ("dx", "dy", "expected"),
    [(0, 0, "beside"), (4, -4, "beside"), (5, 0, "close"), (-100, 30, "close"),
     (0, 101, "far"), (250, 250, "far"), (251, 0, "very_far")],
)
def test_distance(dx, dy, expected):
    assert distance_of(dx, dy) == expected


@pytest.mark.parametrize(
    ("dx", "dy", "expected"),
    [(10, 0, "E"), (0, -10, "N"), (0, 10, "S"), (-10, 0, "W"), (10, -10, "NE"), (-10, 10, "SW"),
     (10, 4, "E"), (10, 5, "SE"), (4, -10, "N"), (5, -10, "NE")],
)
def test_direction(dx, dy, expected):
    # Granica co 22,5°: tan(22,5°) ≈ 0,414, więc 4/10 to jeszcze wschód, a 5/10 już skos.
    assert direction_of(dx, dy) == expected


def test_floors():
    x, y, z = THAIS
    assert floors_of(Reading(x, y, z, "close", "N", "up")) == frozenset(range(7))
    assert floors_of(Reading(x, y, z, "beside", None, "down")) == frozenset(range(8, 16))
    assert floors_of(Reading(x, y, z, "close", "N")) == {7}
    # Daleko czar nie mówi o piętrze.
    assert len(floors_of(Reading(x, y, z, "far", "N", "up"))) == 16


@pytest.mark.parametrize(
    "reading",
    [
        Reading(*THAIS, "beside"),
        Reading(*THAIS, "close", "NE"),
        Reading(*THAIS, "close", "W"),
        Reading(*THAIS, "far", "S"),
        Reading(*THAIS, "very_far", "SE"),
    ],
)
def test_polygons_match_rules(reading):
    # Wielokąty muszą dawać dokładnie te same kratki co reguła z TibiaWiki (matches).
    area = possible_area([reading])
    rng = random.Random(1)
    reach = {"beside": 8, "close": 130, "far": 300, "very_far": 1500}[reading.distance]
    for _ in range(3000):
        x = reading.x + rng.randint(-reach, reach)
        y = reading.y + rng.randint(-reach, reach)
        if not (MAP_X_MIN <= x <= MAP_X_MAX and MAP_Y_MIN <= y <= MAP_Y_MAX):
            continue  # poza mapą obszar jest celowo ucięty
        assert area.contains(x, y, 7) == matches(reading, x, y, 7), (x - reading.x, y - reading.y)


def test_tiles_count_of_close_ring_sector():
    # Cały pierścień „blisko” ma 201² - 9² kratek; 8 kierunków dzieli go mniej więcej po równo.
    total = sum(possible_area([Reading(*THAIS, "close", d)]).tiles for d in ("N", "NE", "E", "SE", "S", "SW", "W", "NW"))
    assert total == 201 * 201 - 9 * 9


def test_second_reading_narrows_area():
    x, y, z = THAIS
    first = possible_area([Reading(x, y, z, "far", "N")])
    # Monster 150 kratek na północ. Drugi odczyt 120 kratek dalej na północ: „blisko, północ”.
    readings = [Reading(x, y, z, "far", "N"), Reading(x, y - 120, z, "close", "N")]
    both = possible_area(readings)
    assert 0 < both.tiles < first.tiles
    assert both.contains(x, y - 150, 7)
    assert not both.contains(x, y - 300, 7)
    assert both.floors == {7}


def test_contradicting_readings_give_empty_area():
    x, y, z = THAIS
    area = possible_area([Reading(x, y, z, "close", "N"), Reading(x, y, z, "close", "S")])
    assert area.empty


def test_no_readings():
    assert possible_area([]) is None


def test_area_is_clipped_to_map():
    # Przy krawędzi mapy nie rysujemy niczego poza nią.
    area = possible_area([Reading(31750, 30980, 7, "very_far", "NW")])
    assert area.empty


def test_floor_ranges():
    assert floor_ranges(frozenset({5, 6, 7, 10})) == [(5, 7), (10, 10)]
    assert floor_ranges(frozenset()) == []


# --- komunikaty i podpowiedzi „co to może być” -----------------------------


@pytest.mark.parametrize(
    ("distance", "direction", "floor", "expected"),
    [
        ("beside", None, "same", "is standing next to you"),
        ("beside", None, "up", "is above you"),
        ("close", "NE", "same", "is to the north-east"),
        ("close", "S", "down", "is on a lower level to the south"),
        ("far", "W", "same", "is far to the west"),
        ("very_far", "NW", "same", "is very far to the north-west"),
    ],
)
def test_message(distance, direction, floor, expected):
    # Teksty jak na TibiaWiki (Find Person); gracz wybiera ten, który pokazała gra.
    assert message(distance, direction, floor) == expected


def _monster(monster_id, level, **extra):
    return Monster(id=monster_id, name=monster_id.title(), hp=100, exp=10, bestiary_level=level,
                   source_url="https://tibia.fandom.com/wiki/X", **extra)


def test_candidates_filter_and_sort():
    x, y, z = THAIS
    area = possible_area([Reading(x, y, z, "close", "N")])
    inside = [(x, y - 50, 7), (x + 5, y - 60, 7)]
    monsters = {m.id: m for m in (
        _monster("rotworm", "Easy"),
        _monster("dragon", "Medium"),
        _monster("rat", "Harmless"),  # bez lootu: nie bywa fiendish
        _monster("ferumbras", "Challenging", boss=True),
        _monster("far-away", "Easy"),
    )}
    spawns = Spawns(monsters={
        "rotworm": inside,
        "dragon": inside[:1],
        "rat": inside,
        "ferumbras": inside,
        "far-away": [(x, y + 50, 7)],  # na południe, poza obszarem
        "unknown": inside,  # nie ma go w danych potworów
    })
    assert [(m.id, n) for m, n in candidates(area, spawns, monsters)] == [("rotworm", 2), ("dragon", 1)]
    assert [m.id for m, _ in candidates(area, spawns, monsters, "Medium")] == ["dragon"]
