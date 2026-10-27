"""Testy linku „Wyślij raport” (formularz Google z wpisaną nazwą bossa albo miejsca)."""

import datetime
import urllib.parse

from tibiahelper.core.models import Hunt, Monster
from tibiahelper.core.reports import DATE_FIELD, FORM_URL, SUBJECT_FIELD, boss_report_url, hunt_report_url

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
