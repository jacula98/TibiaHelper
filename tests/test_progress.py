"""Testy zapisu postępu (pliki w tmp_path, nie w prawdziwym %APPDATA%)."""

import json

import pytest

from tibiahelper.core.models import Quest
from tibiahelper.core.progress import ProgressStore


@pytest.fixture
def path(tmp_path):
    # Podkatalog, którego jeszcze nie ma: zapis musi go sam utworzyć.
    return tmp_path / "TibiaHelper" / "progress.json"


def make_quest(steps: int) -> Quest:
    return Quest.model_validate(
        {
            "id": "q",
            "name": "Q",
            "min_level": 1,
            "premium": False,
            "source_url": "https://tibia.fandom.com/wiki/Q",
            "steps": [{"text": f"krok {i}"} for i in range(steps)],
        }
    )


def test_missing_file_means_no_progress(path):
    assert ProgressStore(path).done_steps("q") == set()


def test_progress_survives_restart(path):
    store = ProgressStore(path)
    store.set_step("q", 0, True)
    store.set_step("q", 2, True)
    store.set_step("other", 1, True)

    reloaded = ProgressStore(path)
    assert reloaded.done_steps("q") == {0, 2}
    assert reloaded.done_steps("other") == {1}


def test_unchecking_step_removes_it(path):
    store = ProgressStore(path)
    store.set_step("q", 1, True)
    store.set_step("q", 1, False)
    assert ProgressStore(path).done_steps("q") == set()
    # Quest bez odhaczonych kroków znika z pliku, żeby plik nie puchł.
    assert json.loads(path.read_text(encoding="utf-8"))["quests"] == {}


def test_reset_quest_clears_only_that_quest(path):
    store = ProgressStore(path)
    store.set_step("q", 0, True)
    store.set_step("other", 0, True)
    store.reset_quest("q")
    reloaded = ProgressStore(path)
    assert reloaded.done_steps("q") == set()
    assert reloaded.done_steps("other") == {0}


def test_count_done_ignores_removed_steps(path):
    store = ProgressStore(path)
    store.set_step("q", 0, True)
    store.set_step("q", 5, True)  # krok, którego po edycji questa już nie ma
    assert store.count_done(make_quest(steps=3)) == 1


def test_done_steps_returns_copy(path):
    store = ProgressStore(path)
    store.done_steps("q").add(3)
    assert store.done_steps("q") == set()


@pytest.mark.parametrize(
    "content",
    ["{ urwany json", "[]", '{"version": 1}', '{"version": 1, "quests": {"q": "abc"}}'],
)
def test_corrupt_file_is_moved_aside(path, content):
    path.parent.mkdir(parents=True)
    path.write_text(content, encoding="utf-8")

    store = ProgressStore(path)

    assert store.done_steps("q") == set()
    assert not path.exists()
    assert path.with_suffix(".json.corrupt").read_text(encoding="utf-8") == content
    # Po odłożeniu uszkodzonego pliku zapis działa normalnie.
    store.set_step("q", 0, True)
    assert ProgressStore(path).done_steps("q") == {0}


def test_save_leaves_no_temp_file(path):
    ProgressStore(path).set_step("q", 0, True)
    assert sorted(p.name for p in path.parent.iterdir()) == ["progress.json"]


def test_save_error_does_not_crash(tmp_path):
    # Katalog o nazwie pliku: zapis się nie uda, ale wyjątek nie może polecieć do UI.
    blocker = tmp_path / "plik"
    blocker.write_text("x", encoding="utf-8")
    store = ProgressStore(blocker / "progress.json")
    store.set_step("q", 0, True)
    assert store.done_steps("q") == {0}
