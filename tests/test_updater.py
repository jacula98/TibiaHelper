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


def test_update_saves_newer_data(tmp_path):
    cached = tmp_path / "TibiaHelper" / "quests.json"
    result = updater.update_from_github(3, cached, fetch=fetch_returning(quest_file(4)))
    assert result is not None and result.data_version == 4
    assert json.loads(cached.read_text(encoding="utf-8"))["data_version"] == 4


def test_update_skips_same_or_older_data(tmp_path):
    cached = tmp_path / "quests.json"
    assert updater.update_from_github(4, cached, fetch=fetch_returning(quest_file(4))) is None
    assert not cached.exists()


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
def test_update_failures_keep_local_data(tmp_path, fetch):
    cached = tmp_path / "quests.json"
    assert updater.update_from_github(1, cached, fetch=fetch) is None
    assert not cached.exists()


def test_download_requires_https():
    with pytest.raises(ValueError):
        updater.download("http://example.com/quests.json")
