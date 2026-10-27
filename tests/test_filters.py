"""Testy wyszukiwania i filtra po levelu."""

import pytest

from tibiahelper.core.filters import filter_quests
from tibiahelper.core.models import Quest


def quest(name: str, min_level: int, quest_id: str) -> Quest:
    return Quest.model_validate(
        {
            "id": quest_id,
            "name": name,
            "min_level": min_level,
            "premium": False,
            "source_url": "https://tibia.fandom.com/wiki/X",
            "steps": [{"text": "krok"}],
        }
    )


QUESTS = [
    quest("Annihilator Quest", 100, "annihilator"),
    quest("Katana Quest", 1, "katana"),
    quest("Desert Dungeon Quest", 20, "desert"),
    quest("Żółwia Wyspa", 30, "zolwia-wyspa"),
]


def names(quests):
    return [q.name for q in quests]


def test_no_filters_returns_all_sorted_by_level():
    assert names(filter_quests(QUESTS)) == [
        "Katana Quest",
        "Desert Dungeon Quest",
        "Żółwia Wyspa",
        "Annihilator Quest",
    ]


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("katana", ["Katana Quest"]),
        ("KATANA", ["Katana Quest"]),  # wielkość liter bez znaczenia
        ("  dungeon  ", ["Desert Dungeon Quest"]),  # spacje na brzegach ignorowane
        ("quest desert", ["Desert Dungeon Quest"]),  # słowa w dowolnej kolejności
        ("zolw", ["Żółwia Wyspa"]),  # bez polskich znaków
        ("żółw", ["Żółwia Wyspa"]),
        ("nie ma takiego", []),
    ],
)
def test_search_by_name(query, expected):
    assert names(filter_quests(QUESTS, query=query)) == expected


def test_level_filter_includes_equal_level():
    assert names(filter_quests(QUESTS, player_level=20)) == ["Katana Quest", "Desert Dungeon Quest"]


def test_level_and_query_combined():
    assert names(filter_quests(QUESTS, query="quest", player_level=50)) == [
        "Katana Quest",
        "Desert Dungeon Quest",
    ]


def test_search_finds_mission_inside_bigger_quest():
    # Na wiki „The Curse Spreads” to misja w „Grimvale Quest”, nie osobna strona.
    grimvale = Quest.model_validate(
        {
            "id": "grimvale-quest",
            "name": "Grimvale Quest",
            "min_level": 0,
            "premium": True,
            "source_url": "https://tibia.fandom.com/wiki/Grimvale_Quest",
            "steps": [{"text": "[The Curse of the Full Moon] Start"}, {"text": "[The Curse Spreads] Go to Vengoth."}],
        }
    )
    assert names(filter_quests([*QUESTS, grimvale], query="curse spreads")) == ["Grimvale Quest"]
    # Słowa muszą być w jednej misji, a nie rozrzucone po różnych.
    assert filter_quests([grimvale], query="spreads moon") == []
