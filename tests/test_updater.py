"""Testy aktualizacji danych. Sieć jest zastąpiona sztuczną funkcją fetch."""

import http.client
import json

import pytest

from tibiahelper.core import updater
from tibiahelper.core.repository import QuestFileError


def quest_file(data_version: int, schema_version: int = 1) -> dict:
    return {
        "schema_version": schema_version,
        "data_version": data_version,
        "quests": [
            {
                "id": "q",
                "name": "Q",
                "min_level": 1,
                "premium": False,
                "source_url": "https://tibia.fandom.com/wiki/Q",
                "steps": [{"text": "krok"}],
            }
        ],
    }


def write(path, data) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def fetch_returning(data):
    return lambda url: json.dumps(data).encode("utf-8")


def test_best_local_prefers_higher_data_version(tmp_path):
    bundled, cached = tmp_path / "bundled.json", tmp_path / "cached.json"
    write(bundled, quest_file(3))
    write(cached, quest_file(5))
    assert updater.load_best_local(bundled, cached).data_version == 5
    # Po instalacji nowszej wersji programu wbudowana kopia wygrywa ze starszą pobraną.
    write(bundled, quest_file(7))
    assert updater.load_best_local(bundled, cached).data_version == 7


def test_best_local_ignores_broken_cached_copy(tmp_path):
    bundled, cached = tmp_path / "bundled.json", tmp_path / "cached.json"
    write(bundled, quest_file(3))
    cached.write_text("{urwany", encoding="utf-8")
    assert updater.load_best_local(bundled, cached).data_version == 3


def test_best_local_raises_when_nothing_usable(tmp_path):
    with pytest.raises(QuestFileError):
        updater.load_best_local(tmp_path / "a.json", tmp_path / "b.json")


def test_check_finds_newer_data_without_saving(tmp_path):
    update = updater.check_for_update(3, fetch=fetch_returning(quest_file(4)))
    assert update is not None and update.data_version == 4


def test_apply_update_saves_data(tmp_path):
    cached = tmp_path / "TibiaHelper" / "quests.json"
    update = updater.check_for_update(3, fetch=fetch_returning(quest_file(4)))
    assert updater.apply_update(update, cached)
    assert updater.load_best_local(tmp_path / "brak.json", cached).data_version == 4


def test_apply_update_reports_write_error(tmp_path):
    update = updater.check_for_update(3, fetch=fetch_returning(quest_file(4)))
    blocker = tmp_path / "plik"
    blocker.write_text("", encoding="utf-8")
    # Katalog docelowy jest zwykłym plikiem, więc zapis musi się nie udać.
    assert not updater.apply_update(update, blocker / "quests.json")


def test_check_skips_same_or_older_data():
    assert updater.check_for_update(4, fetch=fetch_returning(quest_file(4))) is None


@pytest.mark.parametrize(
    "fetch",
    [
        lambda url: (_ for _ in ()).throw(OSError("brak sieci")),
        lambda url: (_ for _ in ()).throw(http.client.IncompleteRead(b"")),
        lambda url: b"<html>to nie JSON</html>",
        lambda url: b"\xff\xfe",
        fetch_returning(quest_file(9, schema_version=99)),  # za nowa wersja schematu
        fetch_returning({"cokolwiek": 1}),
    ],
)
def test_check_failures_give_no_update(fetch):
    assert updater.check_for_update(1, fetch=fetch) is None


def test_download_requires_https():
    with pytest.raises(ValueError):
        updater.download("http://example.com/quests.json")
