"""Import całej bazy z TibiaWiki: wszystkie potwory i wszystkie questy (jako szkice).

Strony trafiają do cache (generator/raw/), więc ponowne uruchomienie pobiera
tylko brakujące. Zapytania idą porcjami po 50 tytułów z przerwą między nimi,
więc całość to ok. 150 zapytań, a nie kilka tysięcy.
"""

import logging
from collections.abc import Iterable

from tibiahelper.core import author

from . import cache, monsters, quests
from .quests import TODO_MARK
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


def _is_untouched_draft(quest: dict) -> bool:
    """Szkic, którego autor jeszcze nie ruszał (sam krok „TODO” z importu)."""
    steps = quest.get("steps", [])
    return quest.get("status") == "draft" and len(steps) == 1 and steps[0].get("text", "").startswith(TODO_MARK)


def import_quests(data: dict, client: WikiClient, refresh: bool = False) -> tuple[int, int]:
    """Dodaje brakujące questy jako szkice z materiałem z /Spoiler. Zwraca (nowe, odświeżone).

    Szkice, których autor nie ruszał, wypełniamy na nowo; questów z pracą autora nie zmieniamy.
    Podstrony (np. „…/Spoiler”) też mają ramkę questa na wiki, ale to nie są osobne questy.
    """
    titles = [t for t in client.embedded_in("Infobox Quest") if "/" not in t]
    # Usuwamy tylko nieruszone szkice podstron: pracy autora nie kasujemy.
    data["quests"] = [
        q
        for q in data["quests"]
        if "/" not in quests.title_from_url(q["source_url"]) or not _is_untouched_draft(q)
    ]
    existing = {quests.title_from_url(q["source_url"]): q for q in data["quests"]}
    todo = [t for t in titles if t not in existing or _is_untouched_draft(existing[t])]
    pages = load_pages(client, [t for title in todo for t in (title, title + quests.SPOILER_SUFFIX)], refresh)
    taken = {q["id"] for q in data["quests"]}
    added = refreshed = 0
    for title in todo:
        if title not in pages:
            continue
        draft = quests.make_draft(quests.QuestPages(main=pages[title], spoiler=pages.get(title + quests.SPOILER_SUFFIX)))
        old = existing.get(title)
        if old is not None:
            # id zostaje: od niego zależy zapis postępu graczy.
            draft["id"] = old["id"]
            data["quests"][data["quests"].index(old)] = draft
            refreshed += 1
        else:
            draft["id"] = _unique_id(draft["id"], taken)
            taken.add(draft["id"])
            data["quests"].append(draft)
            added += 1
    data["quests"].sort(key=lambda q: q["name"].lower())
    return added, refreshed
