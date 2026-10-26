"""Test linku „Zgłoś błąd”."""

import urllib.parse

from tibiahelper.core.issues import NEW_ISSUE_URL, issue_url
from tibiahelper.core.models import Quest


def test_issue_url_prefills_title_and_body():
    quest = Quest.model_validate(
        {
            "id": "katana-quest",
            "name": "Katana Quest & co",
            "min_level": 0,
            "premium": False,
            "source_url": "https://tibia.fandom.com/wiki/Katana_Quest",
            "wiki_revision": 123,
            "steps": [{"text": "krok"}],
        }
    )
    url = issue_url(quest, data_version=4)
    base, query = url.split("?", 1)
    params = urllib.parse.parse_qs(query)

    assert base == NEW_ISSUE_URL
    assert params["title"] == ["[katana-quest] Błąd w poradniku"]
    body = params["body"][0]
    # Znak & w nazwie nie może rozbić adresu na dodatkowe parametry.
    assert "Katana Quest & co" in body
    assert "Wersja danych: 4" in body
    assert "Rewizja TibiaWiki: 123" in body
    assert set(params) == {"title", "body"}
