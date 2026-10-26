"""Potwory z TibiaWiki do listy "monsters" w data/quests.json.

Z {{Infobox Creature}} bierzemy tylko to, co pokazuje dymek w aplikacji:
HP, exp i obrażenia od żywiołów. Obrazek to plik "<Nazwa>.gif" z wiki;
zapisujemy tylko jego adres, bo grafika należy do CipSoft i nie trafia do repo.
"""

import re

from tibiahelper.core.models import ELEMENTS, Monster

from . import cache
from .quests import slugify, source_url
from .wiki_api import WikiClient, WikiPage
from .wikitext import parse_infobox

_NUMBER = re.compile(r"\d+")


def _number(value: str) -> int | None:
    # Na wiki bywa "100%", "1,500" albo "?" (nieznane).
    match = _NUMBER.search(value.replace(",", ""))
    return int(match.group()) if match else None


def sprite_file(title: str) -> str:
    return title.replace(" ", "_") + ".gif"


def fetch_page(client: WikiClient, title: str, refresh: bool = False) -> WikiPage:
    page = None if refresh else cache.load(title)
    if page is None:
        page = client.get_pages([title])[title]
        if page is None:
            raise LookupError(f"Na TibiaWiki nie ma strony {title!r}")
        cache.save(title, page)
    return page


def make_monster(page: WikiPage, image_url: str, monster_id: str | None = None) -> dict:
    """Wpis potwora z wikitekstu strony. Rzuca ValueError, gdy strona nie jest potworem."""
    info = parse_infobox(page.wikitext, "Infobox Creature")
    if not info:
        raise ValueError(f"{page.title!r} nie ma {{{{Infobox Creature}}}}: to nie jest potwór?")
    elements = {}
    for element in ELEMENTS:
        percent = _number(info.get(f"{element}dmgmod", ""))
        # 100% = zwykłe obrażenia, więc zapisujemy tylko wyjątki.
        if percent is not None and percent != 100:
            elements[element] = percent
    monster = {
        "id": monster_id or slugify(page.title),
        "name": info.get("name") or page.title,
        "hp": _number(info.get("hp", "")) or 0,
        "exp": _number(info.get("exp", "")) or 0,
        "elements": elements,
        "image_url": image_url,
        "source_url": source_url(page.title),
        "wiki_revision": page.revid,
    }
    # Ta sama walidacja co w aplikacji, zanim cokolwiek trafi do pliku.
    Monster.model_validate(monster)
    return monster


def fetch_monster(client: WikiClient, title: str, monster_id: str | None = None, refresh: bool = False) -> dict:
    page = fetch_page(client, title, refresh)
    file_name = sprite_file(page.title)
    url = client.image_urls([file_name])[file_name]
    if url is None:
        raise LookupError(f"Na TibiaWiki nie ma obrazka {file_name!r}")
    return make_monster(page, url, monster_id)
