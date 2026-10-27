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
    assert cooldown_hours("10 minutes") == pytest.approx(0.167, abs=0.001)
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
    assert format_cooldown(cooldown_hours("15 seconds")) == "14 s"  # 0.004 h po zaokrągleniu w generatorze


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
