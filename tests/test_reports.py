"""Testy linku „Wyślij raport” (formularz Google z wpisaną nazwą bossa albo miejsca)."""

import datetime
import urllib.parse
from pathlib import Path

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


def test_generator_saves_reports_only_when_changed(tmp_path):
    from datetime import UTC, datetime

    from generator import reports as gen_reports
    from tibiahelper.core.reports import load_reports

    path = tmp_path / "reports.json"
    now = datetime(2026, 10, 27, 18, 0, tzinfo=UTC)
    assert gen_reports.update(CSV, path, now) == 3
    assert gen_reports.update(CSV, path, now) is None  # bez zmian: brak zapisu, brak „nowych danych” u graczy
    version, reports = load_reports(path)
    assert version == 202610271800 and reports[0].subject == "Hunt: Asura Palace"


def test_newer_reports_come_with_data_update(tmp_path):
    import json

    from tibiahelper.core import updater
    from tibiahelper.core.reports import load_reports, parse_reports, reports_to_json

    quests = json.loads((Path(__file__).parents[1] / "data" / "quests.json").read_text(encoding="utf-8"))
    quests["data_version"] += 1
    reports_file = json.dumps(reports_to_json(5, parse_reports(CSV))).encode()
    files = {updater.DATA_URL: json.dumps(quests).encode(), updater.REPORTS_URL: reports_file}

    def fetch(url):
        if url not in files:
            raise OSError("404")
        return files[url]

    update = updater.check_for_update(quests["data_version"] - 1, fetch, reports_version=4)
    assert update is not None and update.reports_raw == reports_file
    assert updater.check_for_update(quests["data_version"] - 1, fetch, reports_version=5).reports_raw is None

    cached = tmp_path / "reports.json"
    assert updater.apply_update(update, tmp_path / "quests.json", None, cached)
    # Dołączony plik (wersja 0 albo brak) przegrywa z nowszym pobranym.
    assert load_reports(tmp_path / "brak.json", cached)[0] == 5


def test_broken_reports_file_is_ignored(tmp_path):
    from tibiahelper.core.reports import load_reports

    bad = tmp_path / "reports.json"
    bad.write_text('{"version": "x"}')
    assert load_reports(bad) == (0, [])
    bad.write_text('{"version": 3, "reports": [{"subject": "A"}, {"subject": "B", "loot": "' + "x" * 9000 + '"}]}')
    version, reports = load_reports(bad)
    assert version == 3 and [r.subject for r in reports] == ["B"] and len(reports[0].loot) < 9000


def test_reports_html_escapes_player_text():
    from tibiahelper.core.reports import Report
    from tibiahelper.ui import theme
    from tibiahelper.ui.report_list import reports_html

    theme._set_colors(theme.THEMES[theme.DEFAULT_THEME])
    html = reports_html([Report("X", "<img src=x>\nlinia 2", "2026-10-27", "<a href=evil>", "<script>")])
    for raw in ("<img", "<a href=evil>", "<script>"):
        assert raw not in html
    assert "<br>linia 2" in html and "&lt;script&gt;" in html
