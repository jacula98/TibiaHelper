"""Klient MediaWiki API TibiaWiki (tibia.fandom.com/api.php).

Pobieramy wikitekst przez API zamiast scrapować HTML: format jest stabilny,
a odpowiedź od razu zawiera revision id potrzebny do wykrywania zmian.
"""

import json
import time
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass

API_URL = "https://tibia.fandom.com/api.php"
# Wiki prosi, żeby boty przedstawiały się i podawały kontakt.
USER_AGENT = "TibiaHelper-generator/0.1 (+https://github.com/jacula98/TibiaHelper)"
# MediaWiki przyjmuje do 50 tytułów w jednym zapytaniu.
BATCH_SIZE = 50

Transport = Callable[[dict[str, str]], dict]


@dataclass(frozen=True)
class WikiPage:
    title: str
    revid: int
    wikitext: str


def urllib_transport(params: dict[str, str]) -> dict:
    url = f"{API_URL}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


class WikiClient:
    def __init__(self, transport: Transport = urllib_transport, delay: float = 1.0) -> None:
        # transport da się podmienić w testach, żeby nie łączyć się z wiki.
        self._transport = transport
        self._delay = delay
        self._last_request = 0.0

    def get_pages(self, titles: Iterable[str]) -> dict[str, WikiPage | None]:
        """Pobiera wikitekst. Klucz to tytuł podany przez nas; None = strona nie istnieje."""
        return self._query(titles, with_content=True)

    def latest_revisions(self, titles: Iterable[str]) -> dict[str, int | None]:
        """Tylko numery ostatnich rewizji, bez treści: tanie sprawdzenie zmian."""
        pages = self._query(titles, with_content=False)
        return {title: page.revid if page else None for title, page in pages.items()}

    def _query(self, titles: Iterable[str], with_content: bool) -> dict[str, WikiPage | None]:
        titles = list(dict.fromkeys(titles))  # bez duplikatów, z zachowaniem kolejności
        result: dict[str, WikiPage | None] = {}
        for start in range(0, len(titles), BATCH_SIZE):
            batch = titles[start : start + BATCH_SIZE]
            data = self._request(
                {
                    "action": "query",
                    "prop": "revisions",
                    "titles": "|".join(batch),
                    "redirects": "1",
                    "rvprop": "ids|content" if with_content else "ids",
                    "rvslots": "main",
                    "format": "json",
                    "formatversion": "2",
                    # Jeśli serwery wiki są przeciążone, API każe nam poczekać.
                    "maxlag": "5",
                }
            )
            result.update(_parse_query(batch, data))
        return result

    def _request(self, params: dict[str, str]) -> dict:
        # Przerwa między zapytaniami, żeby nie zasypywać wiki (wymóg z REVIEW.md).
        wait = self._last_request + self._delay - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()
        data = self._transport(params)
        if "error" in data:
            raise RuntimeError(f"Błąd API TibiaWiki: {data['error']}")
        return data


def _parse_query(requested: list[str], data: dict) -> dict[str, WikiPage | None]:
    query = data.get("query", {})
    # API zwraca strony pod ostateczną nazwą (po normalizacji i przekierowaniach),
    # więc mapujemy je z powrotem na tytuły, o które pytaliśmy.
    renames = {item["from"]: item["to"] for item in query.get("normalized", [])}
    redirects = {item["from"]: item["to"] for item in query.get("redirects", [])}

    pages: dict[str, WikiPage | None] = {}
    for page in query.get("pages", []):
        if page.get("missing") or not page.get("revisions"):
            pages[page["title"]] = None
            continue
        revision = page["revisions"][0]
        wikitext = revision.get("slots", {}).get("main", {}).get("content", "")
        pages[page["title"]] = WikiPage(page["title"], int(revision["revid"]), wikitext)

    result = {}
    for title in requested:
        final = renames.get(title, title)
        final = redirects.get(final, final)
        result[title] = pages.get(final)
    return result
