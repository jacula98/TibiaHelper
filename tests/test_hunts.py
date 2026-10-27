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


def _hunt(hunt_id, **extra):
    from tibiahelper.core.models import Hunt

    return Hunt(id=hunt_id, name=hunt_id.title(), source_url="https://tibia.fandom.com/wiki/" + hunt_id, **extra)


def test_filters_by_level_vocation_city_and_sorts():
    from tibiahelper.core.hunts import filter_hunts, sort_hunts

    rats = _hunt("rats", city="Thais", levels={"knight": 8, "paladin": 8, "mage": 8}, exp_stars=1)
    dragons = _hunt("dragons", city="Thais", levels={"knight": 80, "paladin": 50, "mage": 60}, exp_stars=4)
    asura = _hunt("asura", city="Port Hope", levels={"knight": 200}, exp_stars=5)
    unknown = _hunt("unknown", city="Thais")
    hunts = [rats, dragons, asura, unknown]

    assert filter_hunts(hunts, level=60, vocation="paladin") == [rats, dragons]
    assert filter_hunts(hunts, level=60, vocation="knight") == [rats]
    assert filter_hunts(hunts, level=60) == [rats, dragons]  # bez profesji: najniższy poziom
    assert filter_hunts(hunts, city="Port Hope") == [asura]
    assert filter_hunts(hunts, text="thais") == [rats, dragons, unknown]
    with_dragon = _hunt("cave", areas=[{"monsters": ["dragon"]}])
    assert filter_hunts([*hunts, with_dragon], text="drag", monster_names={"dragon": "Dragon"}) == [dragons, with_dragon]
    assert sort_hunts([rats, dragons], "Poziom malejąco", "paladin") == [dragons, rats]
    assert sort_hunts(hunts, "Exp (gwiazdki)")[0] == asura


def test_bestiary_kills_and_charm_points():
    from tibiahelper.core.hunts import bestiary
    from tibiahelper.core.models import Monster

    def monster(**extra):
        return Monster(id="m", name="M", hp=1, exp=1, source_url="https://tibia.fandom.com/wiki/M", **extra)

    assert bestiary(monster(bestiary_level="Medium")) == ((50, 500, 1000), 25)
    assert bestiary(monster(bestiary_level="Medium", very_rare=True)) == ((2, 3, 5), 50)
    assert bestiary(monster()) is None


def test_hunt_page_html_escapes_wiki_text():
    from tibiahelper.core.models import Monster
    from tibiahelper.ui import theme
    from tibiahelper.ui.hunt_pages import hunt_footer_html, hunt_header_html, hunt_monsters_html

    theme._set_colors(next(iter(theme.THEMES.values())))  # kolory bez uruchamiania Qt
    hunt = _hunt("x", city="<c1>", location="a <script>", areas=[{"name": "Floor <1>", "monsters": ["m"]}], best_loot=["<i1>"])
    monster = Monster(id="m", name="<m>", hp=1, exp=1, source_url="https://tibia.fandom.com/wiki/M", bestiary_level="Easy")
    html = hunt_header_html(hunt) + hunt_monsters_html(hunt, {"m": monster}) + hunt_footer_html(hunt, {})
    for raw in ("<c1>", "<script>", "<1>", "<m>", "<i1>"):
        assert raw not in html
    assert "25/250/500" in html and 'href="monster:m"' in html
