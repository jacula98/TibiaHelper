"""Import całej bazy z TibiaWiki: wszystkie potwory i wszystkie questy (jako szkice).

Strony trafiają do cache (generator/raw/), więc ponowne uruchomienie pobiera
tylko brakujące. Zapytania idą porcjami po 50 tytułów z przerwą między nimi,
więc całość to ok. 150 zapytań, a nie kilka tysięcy.
"""

import logging
from collections.abc import Iterable

from tibiahelper.core import author

from . import cache, monsters, quests
from .wiki_api import WikiClient, WikiPage

log = logging.getLogger(__name__)


def load_pages(client: WikiClient, titles: Iterable[str], refresh: bool = False) -> dict[str, WikiPage]:
    """Strony z cache, a brakujące z wiki (jednym zapytaniem na 50 tytułów)."""
    titles = list(titles)
    pages: dict[str, WikiPage] = {}
    missing = []
    for title in titles:
        page = None if refresh else cache.load(title)
        if page is None:
            missing.append(title)
        else:
            pages[title] = page
    if missing:
        print(f"Pobieram {len(missing)} stron z TibiaWiki…")
        for title, page in client.get_pages(missing).items():
            if page is not None:
                cache.save(title, page)
                pages[title] = page
    return pages


def _unique_id(base: str, taken: set[str]) -> str:
    """Id bez kolizji: "monk", potem "monk-2" itd."""
    candidate, number = base, 2
    while candidate in taken:
        candidate = f"{base}-{number}"
        number += 1
    return candidate


def import_monsters(data: dict, client: WikiClient, refresh: bool = False) -> tuple[int, list[str]]:
    """Dodaje/odświeża wszystkie potwory. Zwraca (liczba potworów, pominięte strony z powodem)."""
    titles = client.embedded_in("Infobox Creature")
    pages = load_pages(client, titles, refresh)
    images = client.image_urls(monsters.sprite_file(title) for title in pages)

    # Potwory już w pliku zachowują swoje id (od nich zależą kroki questów).
    by_source = {m["source_url"]: m["id"] for m in data.get("monsters", [])}
    taken = {m["id"] for m in data.get("monsters", [])}
    skipped = []
    count = 0
    for title, page in pages.items():
        source = quests.source_url(page.title)
        monster_id = by_source.get(source) or _unique_id(quests.slugify(page.title), taken)
        try:
            entry = monsters.make_monster(page, images.get(monsters.sprite_file(title)), monster_id)
        except ValueError as exc:
            skipped.append(f"{title}: {exc}")
            continue
        taken.add(entry["id"])
        author.upsert_monster(data, entry)
        count += 1
    return count, skipped


def import_quests(data: dict, client: WikiClient, refresh: bool = False) -> int:
    """Dodaje questy, których jeszcze nie ma w pliku, jako szkice (gracze ich nie widzą).

    Istniejących questów nie zmienia: mogą mieć już kroki napisane przez autora.
    """
    titles = client.embedded_in("Infobox Quest")
    known = {quests.title_from_url(q["source_url"]) for q in data["quests"]}
    pages = load_pages(client, (t for t in titles if t not in known), refresh)
    taken = {q["id"] for q in data["quests"]}
    added = 0
    for title, page in pages.items():
        draft = quests.make_draft(quests.QuestPages(main=page, spoiler=None))
        draft["id"] = _unique_id(draft["id"], taken)
        taken.add(draft["id"])
        data["quests"].append(draft)
        added += 1
    data["quests"].sort(key=lambda q: q["name"].lower())
    return added
