"""Testy zakładki „Bossy”: dane bossa, Bosstiary, cooldown i zapis w trybie autora."""

import json
import shutil
from pathlib import Path

import pytest

from generator.monsters import _bosstiary_class, cooldown_hours
from tibiahelper.core import author
from tibiahelper.core.bosses import ALL_CLASSES, NO_CLASS, boss_entries, filter_entries, format_cooldown
from tibiahelper.core.models import Boss, Monster
from tibiahelper.core.repository import load_quest_file, parse_quest_data

DATA_FILE = Path(__file__).parents[1] / "data" / "quests.json"
WIKI = "https://tibia.fandom.com/wiki/"


def monster(monster_id: str, **extra) -> Monster:
    fields = {"id": monster_id, "name": monster_id.title(), "hp": 100, "exp": 10, "source_url": WIKI + monster_id}
    fields.update(extra)
    return Monster(**fields)


@pytest.fixture
def data_file(tmp_path):
    # Kopia prawdziwych danych: testy nie mogą zmieniać pliku w repo.
    path = tmp_path / "quests.json"
    shutil.copy(DATA_FILE, path)
    return path


def test_wiki_fields_for_bosses():
    assert cooldown_hours("20") == 20
    assert cooldown_hours("24 hours") == 24
    assert cooldown_hours("10 minutes") == pytest.approx(0.1667, abs=0.0001)
    assert cooldown_hours("14 days") == 336
    assert cooldown_hours("0") is None
    assert cooldown_hours("") is None
    assert cooldown_hours("zależy od eventu") is None
    assert _bosstiary_class({"bosstiaryclass": "Archfoe"}) == "Archfoe"
    assert _bosstiary_class({"bosstiaryclass": "nemesis"}) == "Nemesis"
    assert _bosstiary_class({"bosstiaryclass": ""}) is None


def test_format_cooldown():
    assert format_cooldown(20) == "20 h"
    assert format_cooldown(0.5) == "30 min"
    assert format_cooldown(336) == "14 dni"
    assert format_cooldown(68) == "68 h"
    assert format_cooldown(cooldown_hours("15 seconds")) == "15 s"


def test_player_sees_only_reviewed_bosses_author_sees_all():
    monsters = {
        "drume": monster("drume", boss=True, bosstiary_class="Archfoe"),
        "ferumbras": monster("ferumbras", boss=True, bosstiary_class="Nemesis"),
        "orshabaal": monster("orshabaal", boss=True),
        "rat": monster("rat"),
    }
    bosses = [
        Boss(monster="drume", status="reviewed", reviewed_at="2026-10-27T10:00:00+00:00"),
        Boss(monster="ferumbras"),  # szkic
    ]
    player = boss_entries(monsters, bosses, author_mode=False)
    assert [e.monster.id for e in player] == ["drume"]

    everything = boss_entries(monsters, bosses, author_mode=True)
    assert [e.monster.id for e in everything] == ["drume", "ferumbras", "orshabaal"]
    assert everything[2].boss is None  # jeszcze nie dodany

    assert [e.monster.id for e in filter_entries(everything, "", "Nemesis")] == ["ferumbras"]
    assert [e.monster.id for e in filter_entries(everything, "", NO_CLASS)] == ["orshabaal"]
    assert [e.monster.id for e in filter_entries(everything, "DRU", ALL_CLASSES)] == ["drume"]


def test_reviewed_boss_needs_date():
    with pytest.raises(ValueError, match="reviewed_at"):
        Boss(monster="drume", status="reviewed")


def test_bad_or_unknown_boss_is_skipped_not_fatal():
    raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    raw["bosses"] = [{"monster": "nie-ma-takiego"}, {"monster": "drume", "typo": 1}, {"monster": "drume"}]
    result = parse_quest_data(raw)
    assert [b.monster for b in result.bosses] == ["drume"]
    assert len([e for e in result.errors if e.startswith("boss")]) == 2


def test_author_adds_boss_and_app_reads_it(data_file):
    data = author.load_data(data_file)
    author.upsert_boss(data, {"monster": "drume", "requirements": "Zrób quest.", "quests": ["katana-quest"]})
    author.save_data(data, data_file)
    author.upsert_boss(data, {"monster": "drume", "access": "Idź na wschód."})  # podmiana, nie duplikat
    author.save_data(data, data_file)

    result = load_quest_file(data_file)
    assert [(b.monster, b.access, b.requirements) for b in result.bosses] == [("drume", "Idź na wschód.", None)]
    assert result.visible_bosses == []  # szkic


@pytest.mark.parametrize(
    "boss, message",
    [
        ({"monster": "nie-ma-takiego"}, "nie ma takiego potwora"),
        ({"monster": "drume", "quests": ["zly-quest"]}, "nieznane questy"),
        ({"monster": "drume", "access": "Przez Gate of Expertise."}, "bramka lvl-owa"),
        ({"monster": "drume", "status": "reviewed"}, "reviewed_at"),
    ],
)
def test_author_cannot_save_broken_boss(data_file, boss, message):
    before = data_file.read_text(encoding="utf-8")
    data = author.load_data(data_file)
    author.upsert_boss(data, boss)
    with pytest.raises(author.AuthorError, match=message):
        author.save_data(data, data_file)
    assert data_file.read_text(encoding="utf-8") == before


def test_route_is_saved_in_order_and_shown_escaped(data_file):
    from tibiahelper.ui.boss_pages import route_html

    route = [
        {"x": 32369, "y": 32241, "z": 7, "label": "Start <depot>"},
        {"x": 32370, "y": 32245, "z": 8, "label": "Dziura", "kind": "passage"},
    ]
    data = author.load_data(data_file)
    author.upsert_boss(data, {"monster": "drume", "route": route})
    author.save_data(data, data_file)
    boss = load_quest_file(data_file).bosses[0]
    assert [p.label for p in boss.route] == ["Start <depot>", "Dziura"]

    html = route_html(boss.route)
    assert "Start &lt;depot&gt;" in html and "<depot>" not in html
    assert 'href="route:1"' in html  # numer punktu w linku, klik przenosi mapę


def test_road_points_without_label_are_only_line_bends():
    from tibiahelper.core.models import Waypoint
    from tibiahelper.ui.boss_pages import numbered, route_html

    route = [
        Waypoint(x=32369, y=32241, z=7, label="Start"),
        Waypoint(x=32372, y=32241, z=7),  # punkt drogi
        Waypoint(x=32375, y=32244, z=7, label="Schody", kind="passage"),
    ]
    assert [p.label for p in numbered(route)] == ["1. Start", None, "2. Schody"]
    html = route_html(route)
    assert html.count("<a ") == 2
    assert 'href="route:2"' in html and "2. <a" in html  # link z indeksem w całej trasie, numer bez punktu drogi


def test_route_point_outside_map_is_rejected(data_file):
    data = author.load_data(data_file)
    author.upsert_boss(data, {"monster": "drume", "route": [{"x": 1, "y": 1, "z": 7, "label": "X"}]})
    with pytest.raises(author.AuthorError, match="route"):
        author.save_data(data, data_file)
