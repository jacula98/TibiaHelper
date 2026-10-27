"""Testy dzisiejszego boosted potwora i bossa (TibiaWiki)."""

import json
import urllib.error
from datetime import datetime, timezone

import pytest

from tibiahelper.core import boosted
from tibiahelper.core.boosted import Boosted, get_boosted, parse_response, tibia_day


def _page(title, content, timestamp="2026-10-27T10:41:14Z"):
    return {"title": title, "revisions": [{"timestamp": timestamp, "slots": {"main": {"*": content}}}]}


def _response(*pages):
    return json.dumps({"query": {"pages": {str(i): page for i, page in enumerate(pages)}}}).encode("utf-8")


WIKI = _response(_page(boosted.CREATURE_PAGE, "Werelioness"), _page(boosted.BOSS_PAGE, "Razzagorn"))
NOON = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)


def _fetch(data=WIKI, calls=None):
    def fetch(url):
        assert url == boosted.API_URL
        if calls is not None:
            calls.append(url)
        if isinstance(data, Exception):
            raise data
        return data

    return fetch


def test_api_url_asks_wiki_for_both_templates():
    assert boosted.API_URL.startswith("https://tibia.fandom.com/api.php?")
    assert "Boosted+Creature%7CTemplate%3ABoosted+Boss" in boosted.API_URL


@pytest.mark.parametrize(
    ("utc", "day"),
    [
        # Zima (CET): server save o 9:00 UTC.
        ((2026, 10, 27, 8, 59), "2026-10-26"),
        ((2026, 10, 27, 9, 0), "2026-10-27"),
        # Lato (CEST): server save o 8:00 UTC.
        ((2026, 7, 1, 7, 59), "2026-06-30"),
        ((2026, 7, 1, 8, 0), "2026-07-01"),
        # Dni zmiany czasu w 2026: 29 marca i 25 października.
        ((2026, 3, 29, 8, 0), "2026-03-29"),
        ((2026, 3, 28, 8, 0), "2026-03-27"),
        ((2026, 10, 25, 8, 0), "2026-10-24"),
    ],
)
def test_tibia_day_changes_at_server_save_not_midnight(utc, day):
    assert tibia_day(datetime(*utc, tzinfo=timezone.utc)).isoformat() == day


def test_parse_response_reads_names_and_day():
    assert parse_response(WIKI) == Boosted("2026-10-27", "Werelioness", "Razzagorn")


def test_parse_response_uses_older_day_when_only_one_template_changed():
    data = _response(
        _page(boosted.CREATURE_PAGE, "Werelioness"),
        _page(boosted.BOSS_PAGE, "Razzagorn", timestamp="2026-10-26T10:00:00Z"),
    )
    assert parse_response(data).day == "2026-10-26"


def test_parse_response_drops_strange_names():
    # Szablon z kodem wiki albo HTML nie trafia do okna.
    data = _response(_page(boosted.CREATURE_PAGE, "<b>x</b>"), _page(boosted.BOSS_PAGE, "{{Razzagorn}}"))
    assert parse_response(data) == Boosted("2026-10-27", None, None)


@pytest.mark.parametrize("data", [b"not json", b"{}", b'{"query": {"pages": {"-1": {"missing": ""}}}}'])
def test_parse_response_rejects_bad_data(data):
    with pytest.raises(ValueError):
        parse_response(data)


def test_get_boosted_downloads_once_per_day(tmp_path):
    cache = tmp_path / "boosted.json"
    calls = []
    assert get_boosted(cache, NOON, _fetch(calls=calls)) == Boosted("2026-10-27", "Werelioness", "Razzagorn")
    # Drugi start tego samego dnia: z pliku, bez pytania wiki.
    assert get_boosted(cache, NOON.replace(hour=20), _fetch(calls=calls)).creature == "Werelioness"
    assert len(calls) == 1


def test_get_boosted_asks_again_on_next_day(tmp_path):
    cache = tmp_path / "boosted.json"
    get_boosted(cache, NOON, _fetch())
    tomorrow = _response(
        _page(boosted.CREATURE_PAGE, "Dragon", "2026-10-28T10:30:00Z"),
        _page(boosted.BOSS_PAGE, "Ferumbras", "2026-10-28T10:30:00Z"),
    )
    assert get_boosted(cache, NOON.replace(day=28), _fetch(tomorrow)) == Boosted("2026-10-28", "Dragon", "Ferumbras")


def test_get_boosted_without_internet_keeps_last_result(tmp_path):
    cache = tmp_path / "boosted.json"
    assert get_boosted(cache, NOON, _fetch(urllib.error.URLError("offline"))) is None
    get_boosted(cache, NOON, _fetch())
    later = NOON.replace(day=28)
    assert get_boosted(cache, later, _fetch(urllib.error.URLError("offline"))).day == "2026-10-27"


def test_broken_cache_file_is_ignored(tmp_path):
    cache = tmp_path / "boosted.json"
    cache.write_text("[1, 2", encoding="utf-8")
    assert get_boosted(cache, NOON, _fetch()).boss == "Razzagorn"
