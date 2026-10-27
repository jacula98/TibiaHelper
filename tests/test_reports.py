"""Testy linku „Wyślij raport” (formularz Google z wpisaną nazwą bossa albo miejsca)."""

import datetime
import urllib.parse

from tibiahelper.core.models import Hunt, Monster
from tibiahelper.core.reports import (
    DATE_FIELD,
    FORM_URL,
    SUBJECT_FIELD,
    boss_report_url,
    hunt_report_url,
)

DAY = datetime.date(2026, 10, 27)


def _fields(url: str) -> dict[str, str]:
    base, query = url.split("?", 1)
    assert base == FORM_URL
    return dict(urllib.parse.parse_qsl(query))


def test_boss_link_has_name_and_date():
    boss = Monster(id="drume", name="Drume & Co", hp=1, exp=1, source_url="https://tibia.fandom.com/wiki/Drume")
    fields = _fields(boss_report_url(boss, DAY))
    # & w nazwie nie rozbija adresu (urlencode), loot i autor zostają dla gracza.
    assert fields == {"usp": "pp_url", SUBJECT_FIELD: "Drume & Co", DATE_FIELD: "2026-10-27"}


def test_hunt_link_is_marked_as_hunt():
    hunt = Hunt(id="asura", name="Asura Palace", source_url="https://tibia.fandom.com/wiki/Asura_Palace")
    assert _fields(hunt_report_url(hunt, DAY))[SUBJECT_FIELD] == "Hunt: Asura Palace"


CSV = (
    "Sygnatura czasowa,Pytanie bez tytułu,Boss/Hunt place,Loot/Hunt Analyzer,Data,Komentarz:,Autor:\n"
    '2026-10-26 10:00:00,,Ferumbras,"1x Gold Coin, 2x Platinum Coin",2026-10-26,,Ala\n'
    '2026-10-27 18:30:23,,  ferumbras ,"Session data\n Loot: 100",2026-10-27,<b>uwaga</b>,\n'
    "2026-10-27 18:31:00,,Hunt: Asura Palace,Balance: 5k,2026-10-27,,\n"
    "2026-10-27 18:32:00,,Ferumbras,,2026-10-27,pusty loot,\n"
).encode()


def test_parse_reports_newest_first_by_header_names():
    from tibiahelper.core.reports import parse_reports, reports_for

    reports = parse_reports(CSV)
    ferumbras = reports_for(reports, "Ferumbras")
    # Najnowszy pierwszy, wielkość liter i spacje bez znaczenia, raport bez lootu pominięty.
    assert [r.date for r in ferumbras] == ["2026-10-27", "2026-10-26"]
    assert ferumbras[0].loot == "Session data\n Loot: 100" and ferumbras[1].author == "Ala"
    assert [r.loot for r in reports_for(reports, "Hunt: Asura Palace")] == ["Balance: 5k"]


def test_parse_reports_rejects_sheet_without_columns_and_clips_long_text():
    import pytest
    from tibiahelper.core.reports import MAX_LOOT, parse_reports

    with pytest.raises(ValueError):
        parse_reports(b"a,b\n1,2\n")
    long = parse_reports(("Boss,Loot\nX," + "a" * 5000 + "\n").encode())[0]
    assert len(long.loot) == MAX_LOOT


def test_reports_are_cached_and_offline_keeps_last(tmp_path):
    from tibiahelper.core.reports import REFRESH_SECONDS, get_reports

    cache = tmp_path / "reports.json"
    calls = []

    def fetch(url):
        calls.append(url)
        return CSV

    assert len(get_reports(cache, 1000.0, fetch)) == 3
    assert len(get_reports(cache, 1000.0 + 60, fetch)) == 3 and len(calls) == 1  # z pliku, bez sieci

    def offline(url):
        raise OSError("brak sieci")

    assert len(get_reports(cache, 1000.0 + REFRESH_SECONDS + 1, offline)) == 3  # ostatnie znane


def test_reports_html_escapes_player_text():
    from tibiahelper.core.reports import Report
    from tibiahelper.ui import theme
    from tibiahelper.ui.report_list import reports_html

    theme._set_colors(theme.THEMES[theme.DEFAULT_THEME])
    html = reports_html([Report("X", "<img src=x>\nlinia 2", "2026-10-27", "<a href=evil>", "<script>")])
    for raw in ("<img", "<a href=evil>", "<script>"):
        assert raw not in html
    assert "<br>linia 2" in html and "&lt;script&gt;" in html
