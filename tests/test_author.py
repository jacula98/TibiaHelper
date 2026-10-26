"""Testy trybu autora (zapis bez okna edytora)."""

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tibiahelper.core import author

DATA_FILE = Path(__file__).parents[1] / "data" / "quests.json"


@pytest.fixture
def data_file(tmp_path):
    # Kopia prawdziwych danych: testy nie mogą zmieniać pliku w repo.
    path = tmp_path / "quests.json"
    shutil.copy(DATA_FILE, path)
    return path


def test_save_replaces_quest_and_bumps_version(data_file):
    data = author.load_data(data_file)
    version = data["data_version"]
    quest = author.find_quest(data, "katana-quest")
    quest = {**quest, "steps": [{"text": "Jeden nowy krok."}]}

    author.replace_quest(data, quest)
    author.save_data(data, data_file)

    saved = json.loads(data_file.read_text(encoding="utf-8"))
    assert saved["data_version"] == version + 1
    assert author.find_quest(saved, "katana-quest")["steps"] == [{"text": "Jeden nowy krok."}]


def test_invalid_quest_is_not_saved(data_file):
    before = data_file.read_text(encoding="utf-8")
    data = author.load_data(data_file)
    quest = {**author.find_quest(data, "katana-quest"), "steps": []}
    author.replace_quest(data, quest)
    with pytest.raises(author.AuthorError, match="steps"):
        author.save_data(data, data_file)
    assert data_file.read_text(encoding="utf-8") == before


def test_english_gate_name_is_rejected(data_file):
    data = author.load_data(data_file)
    quest = author.find_quest(data, "katana-quest")
    quest = {**quest, "steps": [{"text": "Przejdź przez Gate of Expertise."}]}
    author.replace_quest(data, quest)
    with pytest.raises(author.AuthorError, match="bramka lvl-owa"):
        author.save_data(data, data_file)


def test_replace_unknown_quest():
    with pytest.raises(author.AuthorError):
        author.replace_quest({"quests": []}, {"id": "nie-ma"})


def test_mark_reviewed():
    quest = author.find_quest(author.load_data(DATA_FILE), "katana-quest")
    now = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)
    reviewed = author.mark_reviewed(quest, now)
    assert reviewed["status"] == "reviewed"
    assert reviewed["reviewed_at"] == "2026-10-26T12:00:00+00:00"
    assert quest["status"] == "draft"  # oryginał bez zmian
    author.check_quest(reviewed)


@pytest.mark.parametrize(
    "change, message",
    [
        ({"steps": [{"text": "TODO: kroki"}]}, "TODO"),
        ({"wiki_revision": None}, "rewizji"),
    ],
)
def test_mark_reviewed_refuses(change, message):
    quest = {**author.find_quest(author.load_data(DATA_FILE), "katana-quest"), **change}
    with pytest.raises(author.AuthorError, match=message):
        author.mark_reviewed(quest)
