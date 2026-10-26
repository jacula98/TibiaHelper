"""Link „Zgłoś błąd”: otwiera w przeglądarce nowe zgłoszenie na GitHubie.

Aplikacja niczego sama nie wysyła i nie ma żadnego tokenu. Tytuł i opis
przekazujemy w adresie URL, a użytkownik sam klika „Submit” na GitHubie.
"""

import urllib.parse

from .models import Quest

NEW_ISSUE_URL = "https://github.com/jacula98/TibiaHelper/issues/new"


def issue_url(quest: Quest, data_version: int) -> str:
    body = "\n".join(
        [
            "**Co jest nie tak?**",
            "",
            "(opisz problem, np. numer kroku i co się nie zgadza)",
            "",
            "---",
            f"Quest: {quest.name} (`{quest.id}`)",
            f"Wersja danych: {data_version}",
            f"Rewizja TibiaWiki: {quest.wiki_revision or 'brak'}",
            f"Źródło: {quest.source_url}",
        ]
    )
    query = urllib.parse.urlencode({"title": f"[{quest.id}] Błąd w poradniku", "body": body})
    return f"{NEW_ISSUE_URL}?{query}"
