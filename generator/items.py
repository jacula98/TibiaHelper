"""Obrazki przedmiotów z lootu potworów (adresy plików z TibiaWiki).

Zapisujemy tylko adresy (słownik "items": nazwa -> adres w data/quests.json),
bo grafiki należą do CipSoft. Aplikacja pobiera obrazek przy pierwszym użyciu.
"""

from tibiahelper.core.models import SPRITE_URL_PREFIX

from .monsters import sprite_file
from .wiki_api import WikiClient


def loot_names(data: dict) -> list[str]:
    names = {item["name"] for monster in data.get("monsters", []) for item in monster.get("loot", [])}
    return sorted(names)


def import_images(data: dict, client: WikiClient) -> tuple[int, int]:
    """Uzupełnia data["items"]. Zwraca (z obrazkiem, bez obrazka)."""
    names = loot_names(data)
    # Plik obrazka na wiki nazywa się jak przedmiot, np. "Gold Coin" -> "Gold_Coin.gif".
    urls = client.image_urls(sprite_file(_capitalized(name)) for name in names)
    images = {}
    for name in names:
        url = urls.get(sprite_file(_capitalized(name)))
        if url and url.startswith(SPRITE_URL_PREFIX):
            images[name] = url
    data["items"] = images
    return len(images), len(names) - len(images)


def _capitalized(name: str) -> str:
    # MediaWiki zawsze ma wielką pierwszą literę tytułu; reszta zostaje jak jest.
    return name[:1].upper() + name[1:]
