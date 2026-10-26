"""Testy etapu 10: import bazy z TibiaWiki, spawny z TibiaRoute, gzip w aktualizacji, strona potwora."""

import gzip
import json

import pytest

from generator import bulk, spawns as gen_spawns, templates
from generator.monsters import make_monster
from generator.wiki_api import WikiClient, WikiPage
from tibiahelper.core import updater
from tibiahelper.core.models import Monster
from tibiahelper.core.spawns import busiest_spot, floors, load_spawns, parse_spawns
from tibiahelper.ui.monster_pages import header_html, loot_html, monster_html
from tibiahelper.ui.monster_widgets import element_verdict

DEMON = """{{Infobox Creature|List={{{1|}}}
| name           = Demon
| hp             = 8200
| exp            = 6000
| isboss         = no
| abilities      = {{Ability List
 |{{Melee|0-500}}
 |{{Ability|Great Fireball|150-250|fire
  |scene={{Scene|spell=5sqmballtarget|caster=Demon}}}}
 |{{Summon|Fire Elemental|1}}
}}
| location       = [[Hero Cave]], ask {{KW|permission}}.
| loot           = {{Loot Table
 |{{Loot Item|1-200|Gold Coin|common}}
 |{{Loot Item|Demon Horn|uncommon}}
}}
| fireDmgMod     = 0%
}}"""
IMAGE = "https://static.wikia.nocookie.net/tibia/images/7/75/Demon.gif/revision/latest"


# --- szablony i potwór z wiki ---------------------------------------------------


def test_template_parser_handles_nesting_and_multiline_params():
    infobox = templates.find(DEMON, "Infobox Creature")
    assert infobox.params["hp"] == "8200"
    assert "Fire Elemental" in infobox.params["abilities"]  # wartość wieloliniowa w całości
    assert templates.find(DEMON, "Infobox Quest") is None


def test_make_monster_reads_details():
    monster = make_monster(WikiPage("Demon", 5, DEMON), IMAGE)
    assert monster["abilities"] == ["Melee: 0-500", "Great Fireball: 150-250 (fire)", "Summon Fire Elemental: 1"]
    assert monster["loot"] == [
        {"amount": "1-200", "name": "Gold Coin", "rarity": "common"},
        {"name": "Demon Horn", "rarity": "uncommon"},
    ]
    assert monster["location"] == "Hero Cave, ask permission."
    assert monster["elements"] == {"fire": 0}
    assert "boss" not in monster  # puste/False pola nie trafiają do pliku


# --- import całej bazy ----------------------------------------------------------


class FakeWiki:
    def __init__(self, pages: dict[str, str], embedded: dict[str, list[str]]):
        self.pages, self.embedded = pages, embedded

    def __call__(self, params: dict) -> dict:
        if params.get("list") == "embeddedin":
            return {"query": {"embeddedin": [{"title": t} for t in self.embedded[params["eititle"]]]}}
        if params.get("prop") == "imageinfo":
            titles = params["titles"].split("|")
            return {"query": {"pages": [{"title": t.replace("_", " "), "imageinfo": [{"url": IMAGE}]} for t in titles]}}
        titles = params["titles"].split("|")
        return {
            "query": {
                "pages": [
                    {"title": t, "revisions": [{"revid": 1, "slots": {"main": {"content": self.pages[t]}}}]}
                    for t in titles
                ]
            }
        }


def test_import_keeps_existing_ids_and_skips_non_creatures(tmp_path, monkeypatch):
    monkeypatch.setattr(bulk.cache, "RAW_DIR", tmp_path)
    monkeypatch.setattr(bulk.cache, "load", lambda title: None)
    monkeypatch.setattr(bulk.cache, "save", lambda title, page: None)
    fake = FakeWiki(
        {"Demon": DEMON, "Hero Cave": "{{Infobox Hunt}}"},
        {"Template:Infobox Creature": ["Demon", "Hero Cave"]},
    )
    data = {"monsters": [{"id": "stary-demon", "source_url": "https://tibia.fandom.com/wiki/Demon"}], "quests": []}
    count, skipped = bulk.import_monsters(data, WikiClient(transport=fake, delay=0))
    assert count == 1 and len(skipped) == 1
    assert [m["id"] for m in data["monsters"]] == ["stary-demon"]  # kroki questów dalej pasują
    assert data["monsters"][0]["hp"] == 8200


def test_unique_id():
    assert bulk._unique_id("monk", {"monk", "monk-2"}) == "monk-3"


# --- spawny -------------------------------------------------------------------------


def test_spawns_build_matches_names_and_drops_bad_points():
    raw = [
        {"monster": {"name": "Monk"}, "spawns": [{"x": 32000, "y": 32000, "z": 7}, {"x": 1, "y": 1, "z": 7}]},
        {"monster": {"name": "Nieznany"}, "spawns": [{"x": 32000, "y": 32000, "z": 7}]},
    ]
    monsters = [{"id": "monk-creature", "name": "Monk", "source_url": "https://tibia.fandom.com/wiki/Monk_(Creature)"}]
    data, unmatched = gen_spawns.build(raw, monsters)
    assert data["monsters"] == {"monk-creature": [[32000, 32000, 7]]}
    assert unmatched == ["Nieznany"]


def test_parse_spawns_skips_invalid_points_and_load_picks_newer(tmp_path):
    good = {"version": 2, "monsters": {"a": [[32000, 32000, 7], [32000, 32000, 99], "x"]}}
    assert parse_spawns(good).of("a") == [(32000, 32000, 7)]
    with pytest.raises(ValueError):
        parse_spawns([])
    (tmp_path / "old.json").write_text(json.dumps({**good, "version": 1}))
    (tmp_path / "new.json").write_text(json.dumps(good))
    (tmp_path / "bad.json").write_text("{")
    assert load_spawns(tmp_path / "old.json", tmp_path / "bad.json", tmp_path / "new.json").version == 2


def test_busiest_spot_and_floors():
    points = [(32000, 32000, 7), (32001, 32001, 7), (32500, 32500, 7), (32000, 32000, 8)]
    assert floors(points)[0] == (7, 3)
    assert busiest_spot(points, 7) == (32000, 32000)
    assert busiest_spot(points, 3) is None


# --- aktualizacja ------------------------------------------------------------------


def test_gunzip_limits_size(monkeypatch):
    assert updater.gunzip(gzip.compress(b"abc")) == b"abc"
    monkeypatch.setattr(updater, "MAX_UNPACKED", 10)
    with pytest.raises(ValueError, match="za duży"):
        updater.gunzip(gzip.compress(b"x" * 1000))
    with pytest.raises(ValueError, match="gzip"):
        updater.gunzip(b"to nie gzip")


def test_update_includes_newer_spawns_only(tmp_path):
    quests = {"schema_version": 1, "data_version": 5, "quests": []}
    spawns = {"version": 3, "monsters": {}}

    def fetch(url):
        return json.dumps(spawns if url == updater.SPAWNS_URL else quests).encode()

    assert updater.check_for_update(4, fetch, spawns_version=2).spawns_raw == spawns
    update = updater.check_for_update(4, fetch, spawns_version=3)
    assert update.spawns_raw is None
    assert updater.apply_update(update, tmp_path / "q.json", tmp_path / "s.json")
    assert not (tmp_path / "s.json").exists()


# --- strona potwora --------------------------------------------------------------------


def test_monster_page_escapes_wiki_text():
    monster = Monster.model_validate(
        {
            **make_monster(WikiPage("Demon", 5, DEMON), IMAGE),
            "location": "<script>x</script>",
            "loot": [{"name": "<b>Horn</b>", "rarity": "rare"}],
        }
    )
    top, bottom = monster_html(monster), loot_html(monster)
    assert "<script>" not in top and "&lt;script&gt;" in top
    assert "&lt;b&gt;Horn&lt;/b&gt;" in bottom and "rzadki" in bottom
    assert "HP <b>8 200</b>" in header_html(monster)


@pytest.mark.parametrize(
    ("percent", "text"),
    [(125, "+25%"), (100, "0%"), (80, "−20%"), (0, "−100%")],
)
def test_element_verdict(percent, text):
    assert element_verdict(percent)[0] == text


def _monster(name, hp, exp):
    return Monster(id=name.lower(), name=name, hp=hp, exp=exp, source_url="https://tibia.fandom.com/wiki/" + name)


def test_sort_monsters():
    from tibiahelper.core.monsters import sort_monsters

    rat, troll, demon = _monster("Rat", 20, 5), _monster("Troll", 50, 20), _monster("Demon", 8200, 6000)
    monsters = [troll, demon, rat]
    assert sort_monsters(monsters, "A–Z") == [demon, rat, troll]
    assert sort_monsters(monsters, "HP malejąco") == [demon, troll, rat]
    assert sort_monsters(monsters, "Exp rosnąco") == [rat, troll, demon]
    assert sort_monsters(monsters, "Exp / HP (najlepsze)") == [demon, troll, rat]


def test_places_groups_nearby_points_and_names_city():
    from tibiahelper.core.spawns import places

    near_thais = [(32370 + i, 32250, 7) for i in range(5)] + [(32372, 32252, 8)]
    near_carlin = [(32360, 31790, 7), (32361, 31790, 7)]
    found = places(near_carlin + near_thais)
    assert [(p.city, p.count, p.z) for p in found] == [("Thais", 6, 7), ("Carlin", 2, 7)]


@pytest.mark.parametrize(("value", "text"), [(950, "950"), (8200, "8.2k"), (1000, "1k"), (82000, "82k"), (1500000, "1.5M")])
def test_short_number(value, text):
    from tibiahelper.ui.monster_grid import short_number

    assert short_number(value) == text


# --- loot z obrazkami i NPC do pinezek --------------------------------------------


def test_loot_amount_with_unknown_upper_limit():
    monster = make_monster(WikiPage("X", 1, DEMON.replace("|1-200|Gold Coin", "|0-24?|Gold Coin")), IMAGE)
    assert monster["loot"][0] == {"amount": "0-24?", "name": "Gold Coin", "rarity": "common"}


def test_item_images_only_from_wiki(tmp_path):
    from tibiahelper.core.repository import parse_quest_data

    raw = {
        "schema_version": 5,
        "data_version": 1,
        "quests": [],
        "items": {"Gold Coin": IMAGE, "Evil": "https://evil.example/x.gif"},
    }
    result = parse_quest_data(raw)
    assert result.item_images == {"Gold Coin": IMAGE}
    assert any("Evil" in e for e in result.errors)


def test_download_items_saves_by_key(tmp_path):
    from tibiahelper.core.monsters import download_items, image_path, item_key

    assert item_key("Dragon's Tail") == "dragon-s-tail"
    done = download_items(tmp_path, {"Dragon's Tail": IMAGE}, fetch=lambda url: b"GIF89a....")
    assert done == ["Dragon's Tail"]
    assert image_path(tmp_path, "dragon-s-tail").name == "dragon-s-tail.gif"


def test_make_npc_and_load(tmp_path):
    from generator import npcs as gen_npcs
    from tibiahelper.core.npcs import find_npc, load_npcs

    page = WikiPage("Sven", 1, "{{Infobox NPC\n| name = Sven\n| city = [[Svargrond]]\n| posx = 125.202\n"
                    "| posy = 121.177\n| posz = 7\n}}")
    npc = gen_npcs.make_npc(page)
    assert npc == {"name": "Sven", "x": 32202, "y": 31153, "z": 7, "city": "Svargrond"}
    assert gen_npcs.make_npc(WikiPage("Ghostlands", 1, "{{Infobox Geography}}")) is None

    path = tmp_path / "npcs.json"
    gen_npcs.save(gen_npcs.build({"Sven": page}), path)
    loaded = load_npcs(path)
    assert find_npc(loaded, " sven ").title == "Sven (Svargrond)"
    assert load_npcs(tmp_path / "brak.json") == []
