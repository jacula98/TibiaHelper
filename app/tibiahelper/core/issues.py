"""Link „Zgłoś błąd”: otwiera w przeglądarce nowe zgłoszenie na GitHubie.

Aplikacja niczego sama nie wysyła i nie ma żadnego tokenu. Tytuł i opis
przekazujemy w adresie URL, a użytkownik sam klika „Submit” na GitHubie.
"""

import urllib.parse

from .models import Monster, Quest

NEW_ISSUE_URL = "https://github.com/jacula98/TibiaHelper/issues/new"


def issue_url(quest: Quest, data_version: int) -> str:
    return _url(
        f"[{quest.id}] Błąd w poradniku",
        "(opisz problem, np. numer kroku i co się nie zgadza)",
        [
            f"Quest: {quest.name} (`{quest.id}`)",
            f"Wersja danych: {data_version}",
            f"Rewizja TibiaWiki: {quest.wiki_revision or 'brak'}",
            f"Źródło: {quest.source_url}",
        ],
    )


def monster_issue_url(monster: Monster, data_version: int) -> str:
    return _url(
        f"[potwór: {monster.id}] Błąd w danych potwora",
        "(opisz problem, np. złe HP, loot albo miejsce na mapie)",
        [
            f"Potwór: {monster.name} (`{monster.id}`)",
            f"Wersja danych: {data_version}",
            f"Rewizja TibiaWiki: {monster.wiki_revision or 'brak'}",
            f"Źródło: {monster.source_url}",
        ],
    )


def _url(title: str, hint: str, details: list[str]) -> str:
    body = "\n".join(["**Co jest nie tak?**", "", hint, "", "---", *details])
    # urlencode koduje znaki specjalne (np. & w nazwie), więc nie rozbiją adresu.
    query = urllib.parse.urlencode({"title": title, "body": body})
    return f"{NEW_ISSUE_URL}?{query}"
