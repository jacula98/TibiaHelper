"""Testy miejsc huntów (Hunt/Bestiary zones): odczyt z TibiaWiki i wczytywanie z pliku."""

import json
from pathlib import Path

from generator import hunts as gen_hunts
from generator.wiki_api import WikiPage
from tibiahelper.core.repository import parse_quest_data

DATA_FILE = Path(__file__).parents[1] / "data" / "quests.json"

PAGE = """{{Infobox Hunt
| name            = Asura Palace
| city            = Port Hope
| location        = Near the [[Kha'zeel Pass]] in [[Tiquanda]], {{Mapper Coords|128.185|127.173|7|4|text=here}}.
| lvlknights      = 200
| lvlpaladins     = 150+
| lvlmages        =
| loot            = Very Good
| lootstar        =
| exp             = Good
| expstar         = 5
| bestloot        = [[Golden Mug]]
| bestloot2       =
}}
Intro.
== Creatures ==
{{CreatureList|type=List/Sorted
 |Lich
}}
=== Ground floor ===
{{CreatureList|type=List/Sorted
 |Hellspawn
 |[[Dawnfire Asura]]
 |Unknown Thing
}}
"""
MONSTERS = {"lich": "lich", "hellspawn": "hellspawn", "dawnfire asura": "dawnfire-asura"}


def test_make_hunt_reads_infobox_and_creature_lists():
    hunt = gen_hunts.make_hunt(WikiPage("Asura Palace", 5, PAGE), MONSTERS)
    assert hunt["city"] == "Port Hope"
    assert hunt["location"] == "Near the Kha'zeel Pass in Tiquanda."
    assert hunt["levels"] == {"knight": 200, "paladin": 150}
    assert (hunt["exp_stars"], hunt["loot_stars"]) == (5, 5)  # gwiazdki albo ocena słowna
    assert hunt["best_loot"] == ["Golden Mug"]
    assert hunt["areas"] == [
        {"monsters": ["lich"]},  # sekcja „Creatures” = całe miejsce
        {"name": "Ground floor", "monsters": ["hellspawn", "dawnfire-asura"]},  # nieznany potwór pominięty
    ]
    assert hunt["entrance"] == {"x": 128 * 256 + 185, "y": 127 * 256 + 173, "z": 7, "label": "Asura Palace"}


def test_refresh_keeps_author_route_and_notes():
    old = {"id": "asura", "route": [{"x": 32769, "y": 32685, "z": 7, "label": "Start"}], "notes": "Uwaga na fale."}
    hunt = gen_hunts.make_hunt(WikiPage("Asura Palace", 6, PAGE), MONSTERS, old)
    assert hunt["id"] == "asura" and hunt["notes"] == "Uwaga na fale." and hunt["route"] == old["route"]


def test_page_without_infobox_is_skipped():
    assert gen_hunts.make_hunt(WikiPage("Hunting Places", 1, "Lista miejsc."), MONSTERS) is None


def test_broken_hunt_is_skipped_not_fatal():
    raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    count = len(raw["hunts"])
    raw["hunts"].append({"id": "zle", "name": "Złe", "source_url": "https://example.com/"})
    result = parse_quest_data(raw)
    assert len(result.hunts) == count
    assert any(e.startswith("hunt") for e in result.errors)
