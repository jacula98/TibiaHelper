"""Testy modelu danych i wczytywania quests.json."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from tibiahelper.core.models import SCHEMA_VERSION, Quest
from tibiahelper.core.repository import QuestFileError, load_quest_file, parse_quest_data

DATA_FILE = Path(__file__).parents[1] / "data" / "quests.json"


def make_quest(**overrides) -> dict:
    """Minimalny poprawny quest; testy nadpisują tylko to, co sprawdzają."""
    quest = {
        "id": "test-quest",
        "name": "Test Quest",
        "min_level": 10,
        "premium": False,
        "source_url": "https://tibia.fandom.com/wiki/Test_Quest",
        "wiki_revision": 123,
        "status": "reviewed",
        "reviewed_at": "2026-10-22T12:00:00Z",
        "steps": [{"text": "Porozmawiaj z NPC.", "npc": "Tom"}],
    }
    quest.update(overrides)
    return quest


def make_file(*quests: dict, **overrides) -> dict:
    data = {"schema_version": SCHEMA_VERSION, "data_version": 1, "quests": list(quests)}
    data.update(overrides)
    return data


# --- pojedynczy quest ---------------------------------------------------------


def test_valid_quest_parses_with_defaults():
    quest = Quest.model_validate(make_quest())
    assert quest.steps[0].npc == "Tom"
    assert quest.steps[0].items == []
    assert quest.rewards == []
    assert quest.needs_review is False
    assert quest.is_visible


@pytest.mark.parametrize(
    "overrides",
    [
        {"id": "Zła Nazwa"},  # id musi być slugiem
        {"min_level": -1},
        {"steps": []},  # quest bez kroków nie ma sensu
        {"steps": [{"text": "   "}]},  # pusty tekst po obcięciu spacji
        {"status": "done"},  # tylko draft/reviewed
        {"source_url": "https://example.com/quest"},  # musi prowadzić do TibiaWiki
        {"reviewed_at": None},  # reviewed bez daty przeglądu
        {"wiki_revision": None},  # reviewed bez revision id
        {"npcs": ["Tom"]},  # nieznane pole = literówka
    ],
)
def test_invalid_quest_is_rejected(overrides):
    with pytest.raises(ValidationError):
        Quest.model_validate(make_quest(**overrides))


def test_draft_may_skip_review_fields():
    quest = Quest.model_validate(make_quest(status="draft", reviewed_at=None, wiki_revision=None))
    assert not quest.is_visible


# --- cały plik ----------------------------------------------------------------


def test_invalid_quest_is_skipped_but_others_load():
    result = parse_quest_data(make_file(make_quest(id="ok"), make_quest(id="bad", min_level="x")))
    assert [q.id for q in result.quests] == ["ok"]
    assert len(result.errors) == 1
    assert "bad" in result.errors[0]


def test_non_object_quest_is_skipped():
    result = parse_quest_data(make_file(make_quest(), None, "tekst"))
    assert [q.id for q in result.quests] == ["test-quest"]
    assert len(result.errors) == 2


def test_duplicate_id_keeps_first():
    result = parse_quest_data(make_file(make_quest(name="Pierwszy"), make_quest(name="Drugi")))
    assert [q.name for q in result.quests] == ["Pierwszy"]
    assert "zduplikowane" in result.errors[0]


def test_visible_quests_only_reviewed():
    draft = make_quest(id="draft-quest", status="draft")
    result = parse_quest_data(make_file(make_quest(), draft))
    assert [q.id for q in result.visible_quests] == ["test-quest"]


def test_newer_schema_version_is_rejected():
    with pytest.raises(QuestFileError, match="schema_version"):
        parse_quest_data(make_file(schema_version=SCHEMA_VERSION + 1))


@pytest.mark.parametrize("raw", [[], {"quests": []}, {"schema_version": 1, "data_version": 1, "quests": "x"}])
def test_bad_header_raises_file_error(raw):
    with pytest.raises(QuestFileError):
        parse_quest_data(raw)


def test_broken_json_raises_file_error(tmp_path):
    path = tmp_path / "quests.json"
    path.write_text("{ to nie jest json", encoding="utf-8")
    with pytest.raises(QuestFileError):
        load_quest_file(path)


def test_missing_file_raises_file_error(tmp_path):
    with pytest.raises(QuestFileError):
        load_quest_file(tmp_path / "brak.json")


def test_load_quest_file_reads_utf8(tmp_path):
    path = tmp_path / "quests.json"
    path.write_text(json.dumps(make_file(make_quest(name="Zażółć"))), encoding="utf-8")
    assert load_quest_file(path).quests[0].name == "Zażółć"


# --- prawdziwy plik z repo ----------------------------------------------------


def test_repo_data_file_is_valid():
    """Pilnuje, żeby data/quests.json w repo zawsze przechodził walidację."""
    result = load_quest_file(DATA_FILE)
    assert result.errors == []
    assert len(result.quests) >= 3
