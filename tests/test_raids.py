"""Testy pomocnika raidów i world change: generator (wikitekst -> raids.json) i rozpoznawanie wklejonego tekstu."""

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from generator import raids as gen
from generator.wiki_api import WikiPage
from tibiahelper.core.raids import (
    format_countdown,
    load_raid_data,
    next_wave,
    parse_raid_data,
    recognize,
    split_lines,
)

DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "raids.json"

THAIS = """== Announced Raids ==

=== Rat Plague in Thais ===
Around 400~ [[Cave Rat]]s will spawn in each wave.

Subarea: Thais City

Events:
{{Raid Message
|00:00:00|Rat plague in Thais!|00:00:15||00:30:00|Rat plague in Thais!|00:32:00}}
{{CreatureList|type=CompactBox2
 |Rat
 |Cave Rat
}}

=== Orc Raid on Thais ===
Subarea: Thais Surroundings (not announced)

{{Raid Message|00:00|Orc activity near Thais reported! Beware!|00:04||00:07|Thais is under attack!|<!--00:11?-->00:09}}

== Unannounced Raids ==

=== Insectoid Scout on Greenshore Farms ===
{{Raid Message|00:00}}

== Historic Raids ==

=== Historic: Primitive Raid ===
{{Raid Message|00:00|Primitives are attacking Thais!|00:??|Primitives are everywhere!}}
"""

TOWNCRYER = """{| class="wikitable"
|-
|{{Message|type=chat|Hear ye! Hear ye! Ankrahmun's desert is the nomads' land.}}
| [[Nomads Mini World Change]]
|-
|{{Message|type=chat|Beware of Tiquanda's dworcs!}} (when [[Dworcs]] dominate)<br />
{{Message|type=chat|Hunters in the Tiquanda jungle have made camp!}} (when [[Hunter]]s dominate)
| [[Jungle Camp Mini World Change]]
|}"""

WORLD_BOARD = """| notes2 = Possible messages are:
* {{Server Message|Nomads travel the eternal sands of Ankrahmun's desert.}} &mdash; [[Nomads Mini World Change|Nomads]] is active.
}}"""

NOMADS = """{{Infobox Quest|List={{{1|}}}
| name           = Nomads Mini World Change
| location       = [[Kha'labal]] (north of [[Ankrahmun]])
| dangers        = [[Sandcrawler]], [[Hyaena]].
| legend         = Nomads travel through the desert.
}}"""

THORNFIRE = """{{Infobox Quest|List={{{1|}}}
| name           = Thornfire World Change
| location       = [[Shadowthorn]]
| reward         = None
}}"""


def page(title: str, text: str) -> WikiPage:
    return WikiPage(title, 1, text)


@pytest.mark.parametrize(
    ("value", "seconds"),
    [
        ("00:00:15", 15),
        ("04:00:00", 4 * 3600),
        ("00:04", 4 * 60),  # strony miast: „00:mm” to minuty
        ("10:00", 10 * 60),  # Vandura Raids: mm:ss
        ("00:??", None),
        ("abc", None),
    ],
)
def test_parse_time(value, seconds):
    assert gen.parse_time(value) == seconds


def test_build_raids_reads_waves_creatures_and_subarea():
    raids = {r["id"]: r for r in gen.build_raids({"Thais Raids": page("Thais Raids", THAIS)})}
    rat = raids["rat-plague-in-thais"]
    assert rat["area"] == "Thais"
    assert rat["subarea"] == "Thais City"
    assert rat["creatures"] == ["Rat", "Cave Rat"]
    assert [(w["at"], w["message"]) for w in rat["waves"]] == [
        (0, "Rat plague in Thais!"),
        (15, ""),
        (1800, "Rat plague in Thais!"),
        (1920, ""),
    ]
    assert "Cave Rats" in rat["description"]
    orc = raids["orc-raid-on-thais"]
    assert orc["subarea"] == "Thais Surroundings"  # bez „(not announced)”
    assert [w["at"] for w in orc["waves"]] == [0, 240, 420, 540]  # komentarz <!-- --> usunięty


def test_build_raids_skips_unannounced_and_marks_historic():
    raids = {r["id"]: r for r in gen.build_raids({"Thais Raids": page("Thais Raids", THAIS)})}
    assert "insectoid-scout-on-greenshore-farms" not in raids
    primitive = raids["historic-primitive-raid"]
    assert primitive["historic"] is True
    assert primitive["name"] == "Primitive Raid"
    assert len(primitive["waves"]) == 1  # fala z czasem „00:??” pominięta


def test_build_raids_drops_duplicate_from_second_page():
    pages = {"Thais Raids": page("Thais Raids", THAIS), "Thais Region Raids": page("Thais Region Raids", THAIS)}
    names = [r["name"] for r in gen.build_raids(pages)]
    assert names.count("Rat Plague in Thais") == 1


def test_build_world_changes_collects_messages_and_infobox():
    pages = {
        gen.TOWNCRYER: page(gen.TOWNCRYER, TOWNCRYER),
        gen.WORLD_BOARD: page(gen.WORLD_BOARD, WORLD_BOARD),
        "Nomads Mini World Change": page("Nomads Mini World Change", NOMADS),
        "Jungle Camp Mini World Change": page("Jungle Camp Mini World Change", "{{Infobox Quest|name=x}}"),
        "Thornfire World Change": page("Thornfire World Change", THORNFIRE),
    }
    mini = {"Nomads Mini World Change", "Jungle Camp Mini World Change"}
    changes = {c["id"]: c for c in gen.build_world_changes(pages, mini)}
    nomads = changes["nomads-mini-world-change"]
    assert nomads["kind"] == "mini"
    assert [m["text"] for m in nomads["messages"]] == [
        "Hear ye! Hear ye! Ankrahmun's desert is the nomads' land.",
        "Nomads travel the eternal sands of Ankrahmun's desert.",
    ]
    assert nomads["location"] == "Kha'labal (north of Ankrahmun)"
    assert nomads["dangers"] == "Sandcrawler, Hyaena"
    jungle = changes["jungle-camp-mini-world-change"]["messages"]
    assert [m["note"] for m in jungle] == ["when Dworcs dominate", "when Hunters dominate"]
    thornfire = changes["thornfire-world-change"]
    assert thornfire["kind"] == "world"
    assert thornfire["keywords"] == ["Thornfire"]
    assert "reward" not in thornfire  # „None” z wiki pomijamy


# --- rozpoznawanie -------------------------------------------------------------

DATA = parse_raid_data(
    {
        "raids": [
            {
                "id": "rat-plague",
                "name": "Rat Plague in Thais",
                "area": "Thais",
                "waves": [
                    {"at": 0, "message": "Rat plague in Thais!"},
                    {"at": 15, "message": ""},
                    {"at": 1800, "message": "Rat plague in Thais!"},
                ],
            },
            {
                "id": "wasps",
                "name": "Wasp Raid in Thais",
                "area": "Thais",
                "waves": [
                    {"at": 0, "message": "Buzzing and humming! Wasps south of Thais. Be careful there!"},
                    {"at": 250, "message": "Even more Wasps south of Thais. Be careful there!"},
                ],
            },
        ],
        "world_changes": [
            {
                "id": "hive-outpost",
                "name": "Hive Outpost",
                "kind": "mini",
                "keywords": ["Hive Outpost"],
                "messages": [{"text": "A hive infestation has been sighted south-west of Liberty Bay!"}],
            },
            {"id": "hive-born", "name": "Hive Born", "kind": "world", "keywords": ["Hive Born", "Hive"]},
            {"id": "thornfire", "name": "Thornfire", "kind": "world", "keywords": ["Thornfire"]},
        ],
    }
)
NOW = datetime(2026, 10, 29, 10, 33, 0)


def test_split_lines_reads_clock():
    lines = split_lines("10:31 Rat plague in Thais!\n\n10:31:05 Wasps\nbez godziny")
    assert [(line.clock, line.text) for line in lines] == [
        ((10, 31, 0), "Rat plague in Thais!"),
        ((10, 31, 5), "Wasps"),
        (None, "bez godziny"),
    ]


def test_raid_timer_counts_from_message_time():
    found = recognize("10:31 Rat plague in Thais!", DATA, NOW)
    [match] = found.raids
    assert match.raid.id == "rat-plague"
    assert match.started_at == datetime(2026, 10, 29, 10, 31, 0)
    assert match.wave_time(2) == datetime(2026, 10, 29, 11, 1, 0)
    assert next_wave(match, NOW) == 2  # fala po 15 s już była


def test_later_wave_message_moves_start_back():
    # Drugi komunikat os (po 250 s) o 10:35:10 -> raid zaczął się o 10:31:00.
    found = recognize("10:35:10 Even more Wasps south of Thais. Be careful there!", DATA, NOW + timedelta(minutes=3))
    [match] = found.raids
    assert match.wave == 1
    assert match.started_at == datetime(2026, 10, 29, 10, 31, 0)


def test_repeated_message_is_matched_to_later_wave_in_order():
    text = "10:31 Rat plague in Thais!\n11:01 Rat plague in Thais!"
    [match] = recognize(text, DATA, datetime(2026, 10, 29, 11, 2)).raids
    assert match.wave == 2
    assert match.started_at == datetime(2026, 10, 29, 10, 31, 0)


def test_message_from_before_midnight_is_yesterday():
    [match] = recognize("23:58 Rat plague in Thais!", DATA, datetime(2026, 10, 29, 0, 5)).raids
    assert match.started_at == datetime(2026, 10, 28, 23, 58)


def test_message_without_clock_starts_now():
    [match] = recognize("Rat plague in Thais!", DATA, NOW).raids
    assert match.from_clock is False
    assert match.started_at == NOW


def test_world_change_by_message_is_not_also_matched_by_keyword():
    found = recognize("10:00 A hive infestation has been sighted south-west of Liberty Bay!", DATA, NOW)
    assert [m.change.id for m in found.changes] == ["hive-outpost"]
    assert found.changes[0].message is not None


def test_world_change_by_keyword():
    found = recognize("Guide: Thornfire is a problem in Shadowthorn.", DATA, NOW)
    assert [(m.change.id, m.message) for m in found.changes] == [("thornfire", None)]


def test_unknown_text_matches_nothing():
    found = recognize("10:31 Hello there", DATA, NOW)
    assert not found.raids and not found.changes


def test_format_countdown():
    assert format_countdown(65) == "1:05"
    assert format_countdown(3723) == "1:02:03"
    assert format_countdown(-5) == "0:00"


def test_bad_entries_are_skipped(tmp_path):
    data = parse_raid_data({"raids": [{"id": "x"}, {"id": "y", "name": "Y", "waves": []}], "world_changes": "zle"})
    assert data.raids == () and data.world_changes == ()
    broken = tmp_path / "raids.json"
    broken.write_text("{nie json", encoding="utf-8")
    assert load_raid_data(broken).raids == ()


def test_bundled_data_file_loads():
    data = load_raid_data(DATA_FILE)
    assert len(data.raids) > 50
    assert len(data.world_changes) > 30
    found = recognize("10:31 Rat plague in Thais!", data, NOW)
    assert any(m.raid.name == "Rat Plague in Thais" for m in found.raids)


def test_category_members_follows_continue():
    from generator.wiki_api import WikiClient

    answers = [
        {"query": {"categorymembers": [{"title": "Thais Raids"}]}, "continue": {"cmcontinue": "x"}},
        {"query": {"categorymembers": [{"title": "Zao Raids"}]}},
    ]
    seen = []

    def transport(params):
        seen.append(params.get("cmcontinue"))
        return answers.pop(0)

    assert WikiClient(transport, delay=0).category_members("Raids") == ["Thais Raids", "Zao Raids"]
    assert seen == [None, "x"]
