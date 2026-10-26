"""Testy potworów: model, wczytywanie, obrazki w tekście, pobieranie obrazków i generator (bez sieci)."""

import pytest
from pydantic import ValidationError

from generator import monsters as gen_monsters
from generator.wiki_api import WikiClient, WikiPage
from tibiahelper.core import author, monsters
from tibiahelper.core.models import SCHEMA_VERSION, Monster, Quest, Step
from tibiahelper.core.repository import parse_quest_data
from tibiahelper.ui.rich_text import monster_tooltip, parse_monster_link, step_html

IMAGE = "https://static.wikia.nocookie.net/tibia/images/7/72/Skeleton.gif/revision/latest"
SKELETON = {
    "id": "skeleton",
    "name": "Skeleton",
    "hp": 50,
    "exp": 35,
    "elements": {"holy": 125, "death": 0},
    "image_url": IMAGE,
    "source_url": "https://tibia.fandom.com/wiki/Skeleton",
    "wiki_revision": 1,
}
GIF = b"GIF89a" + b"reszta"


def quest_with(*steps: dict) -> dict:
    return {
        "id": "q",
        "name": "Q",
        "min_level": 0,
        "premium": False,
        "source_url": "https://tibia.fandom.com/wiki/Q",
        "steps": list(steps),
    }


# --- model ------------------------------------------------------------------


@pytest.mark.parametrize(
    "change",
    [
        {"image_url": "https://example.com/skeleton.gif"},  # obrazki tylko z serwera wiki
        {"image_url": "http://static.wikia.nocookie.net/tibia/images/x.gif"},  # bez https
        {"elements": {"wind": 50}},  # nie ma takiego żywiołu
        {"hp": -1},
    ],
)
def test_invalid_monster_rejected(change):
    with pytest.raises(ValidationError):
        Monster.model_validate({**SKELETON, **change})


def test_step_monster_anchor_must_be_in_text():
    with pytest.raises(ValidationError):
        Step.model_validate({"text": "Zabij.", "monsters": [{"id": "skeleton", "anchor": "szkielety"}]})


def test_monster_counts_sum_and_unknown():
    quest = Quest.model_validate(
        quest_with(
            {"text": "2 szkielety", "monsters": [{"id": "skeleton", "count": 2}]},
            {"text": "3 szkielety i rotworm", "monsters": [{"id": "skeleton", "count": 3}, {"id": "rotworm"}]},
        )
    )
    # Brak liczby choć w jednym kroku = nie podajemy sumy.
    assert quest.monster_counts() == [("skeleton", 5), ("rotworm", None)]


def test_file_with_bad_monster_keeps_quests():
    data = {
        "schema_version": SCHEMA_VERSION,
        "data_version": 1,
        "monsters": [SKELETON, {**SKELETON, "id": "zly", "image_url": "https://zly.example/x.gif"}],
        "quests": [quest_with({"text": "Zabij szkielety", "monsters": [{"id": "skeleton"}, {"id": "nieznany"}]})],
    }
    result = parse_quest_data(data)
    assert list(result.monsters) == ["skeleton"]
    assert len(result.quests) == 1  # nieznany potwór to tylko brak obrazka
    assert any("zly" in e or "potwór #1" in e for e in result.errors)
    assert any("nieznany" in e for e in result.errors)


# --- tryb autora --------------------------------------------------------------


def test_save_rejects_unknown_monster(tmp_path):
    data = {"schema_version": 2, "data_version": 1, "quests": [quest_with({"text": "x", "monsters": [{"id": "skeleton"}]})]}
    with pytest.raises(author.AuthorError, match="nieznane potwory"):
        author.save_data(data, tmp_path / "q.json")
    author.upsert_monster(data, SKELETON)
    author.save_data(data, tmp_path / "q.json")
    assert data["schema_version"] == SCHEMA_VERSION


def test_save_rejects_duplicate_or_broken_monster(tmp_path):
    data = {"schema_version": 3, "data_version": 1, "monsters": [SKELETON, SKELETON], "quests": []}
    with pytest.raises(author.AuthorError, match="dwa razy"):
        author.save_data(data, tmp_path / "q.json")
    data["monsters"] = ["to nie obiekt"]
    with pytest.raises(author.AuthorError, match="#0"):
        author.save_data(data, tmp_path / "q.json")


def test_upsert_monster_replaces_same_id():
    data = {"monsters": [SKELETON]}
    author.upsert_monster(data, {**SKELETON, "hp": 60})
    author.upsert_monster(data, {**SKELETON, "id": "rotworm"})
    assert [(m["id"], m["hp"]) for m in data["monsters"]] == [("rotworm", 50), ("skeleton", 60)]


# --- obrazki w tekście i dymek ------------------------------------------------------


def test_monster_and_pin_inserted_in_text_order():
    step = Step.model_validate(
        {
            "text": "Idź do Thais i zabij 2 szkielety.",
            "markers": [{"x": 32369, "y": 32241, "z": 7, "label": "Thais", "anchor": "Thais"}],
            "monsters": [{"id": "skeleton", "count": 2, "anchor": "2 szkielety"}],
        }
    )
    html = step_html(1, step, "<pin>", lambda i: f"<mon{i}>")
    assert html == (
        '1. Idź do Thais&nbsp;<a href="pin:0" title="Thais"><pin></a>'
        ' i zabij 2 szkielety&nbsp;<a href="mon:0"><mon0></a>.'
    )
    assert parse_monster_link("mon:0") == 0
    assert parse_monster_link("pin:0") is None


def test_tooltip_lists_weaknesses_and_escapes_name():
    monster = Monster.model_validate({**SKELETON, "name": "<b>Skel</b>", "hp": 1500})
    html = monster_tooltip(monster)
    assert "&lt;b&gt;Skel&lt;/b&gt;" in html
    assert "HP 1 500 · exp 35" in html
    assert "Słaby na: święte 125%" in html
    assert "Odporny na: śmierć 0%" in html


# --- pobieranie obrazków ------------------------------------------------------


def test_ensure_sprite_downloads_once(tmp_path):
    calls = []

    def fetch(url):
        calls.append(url)
        return GIF

    monster = Monster.model_validate(SKELETON)
    path = monsters.ensure_sprite(tmp_path, monster, fetch)
    assert path == tmp_path / "skeleton.gif" and path.read_bytes() == GIF
    assert monsters.ensure_sprite(tmp_path, monster, fetch) == path
    assert calls == [IMAGE + "?format=original"]


def test_download_missing_skips_non_images(tmp_path):
    good = Monster.model_validate(SKELETON)
    bad = Monster.model_validate({**SKELETON, "id": "rotworm", "image_url": IMAGE + "?rotworm"})

    def fetch(url):
        # Serwer zwrócił stronę błędu zamiast obrazka: nie zapisujemy jej.
        return b"<html>error</html>" if "rotworm" in url else GIF

    assert monsters.download_missing(tmp_path, [good, bad], fetch) == ["skeleton"]
    assert monsters.sprite_path(tmp_path, "rotworm") is None


# --- generator ------------------------------------------------------------------


CREATURE = """{{Infobox Creature|List={{{1|}}}|GetValue={{{GetValue|}}}
| name           = Skeleton
| hp             = 1,050
| exp            = ?
| physicalDmgMod = 100%
| holyDmgMod     = 125%
| deathDmgMod    = 0%
| loot           = {{Loot Table
 |{{Loot Item|0-10|Gold Coin}}
}}
}}"""


def test_make_monster_from_infobox():
    entry = gen_monsters.make_monster(WikiPage("Skeleton", 7, CREATURE), IMAGE)
    assert entry["id"] == "skeleton"
    assert entry["hp"] == 1050
    assert entry["exp"] == 0  # "?" na wiki
    assert entry["elements"] == {"holy": 125, "death": 0}
    assert entry["wiki_revision"] == 7


def test_make_monster_rejects_non_creature():
    with pytest.raises(ValueError, match="Infobox Creature"):
        gen_monsters.make_monster(WikiPage("Thais", 1, "{{Infobox City}}"), IMAGE)


def test_image_urls_maps_file_names():
    def transport(params):
        assert params["prop"] == "imageinfo"
        return {
            "query": {
                "pages": [
                    {"title": "File:Poison Spider.gif", "imageinfo": [{"url": IMAGE}]},
                    {"title": "File:Nope.gif", "missing": True},
                ]
            }
        }

    client = WikiClient(transport=transport, delay=0)
    assert client.image_urls(["Poison_Spider.gif", "Nope.gif"]) == {"Poison_Spider.gif": IMAGE, "Nope.gif": None}
