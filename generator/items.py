"""Przedmioty z TibiaWiki ({{Infobox Object}}) do listy "items" w data/quests.json.

Bierzemy przedmioty, które da się podnieść, i wszystko, co jest w loocie potworów:
nazwę, rodzaj, wagę, ceny u NPC i listy NPC, którzy kupują albo sprzedają.
Obrazki zapisujemy tylko jako adresy (grafiki © CipSoft); aplikacja pobiera je sama.
"""

import re

from tibiahelper.core.models import SPRITE_URL_PREFIX

from . import templates
from .monsters import sprite_file
from .quests import source_url
from .wiki_api import WikiPage
from .wikitext import strip_markup

_PRICE = re.compile(r"\d+")


def loot_names(data: dict) -> set[str]:
    return {item["name"].lower() for monster in data.get("monsters", []) for item in monster.get("loot", [])}


def _number(value: str) -> int | None:
    # Na wiki bywa "150", "5 - 15" (zakres: bierzemy dolną granicę), "?" albo "--".
    match = _PRICE.search(value.replace(",", ""))
    return int(match.group()) if match else None


def _weight(value: str) -> float | None:
    try:
        return float(value.strip())
    except ValueError:
        return None


def parse_trades(value: str) -> list[dict]:
    """„Fiona, Yasir: 160;premium” -> [{"npc": "Fiona"}, {"npc": "Yasir", "price": 160}].

    Każdy wpis to „Imię[: cena][;uwagi]”; bez ceny NPC płaci tyle, ile podaje pole przedmiotu.
    """
    value = strip_markup(value).strip()
    if value in ("", "--", "-", "?"):
        return []
    trades = []
    for part in value.split(","):
        name, _, rest = part.partition(";")[0].partition(":")
        name = name.strip()
        if not name or name in ("--", "?"):
            continue
        trade: dict = {"npc": name}
        price = _number(rest)
        if price is not None:
            trade["price"] = price
        trades.append(trade)
    return trades


def make_item(page: WikiPage, image_url: str | None, wanted: set[str]) -> dict | None:
    """Przedmiot ze strony albo None (nie przedmiot, nie do podniesienia i nie z lootu)."""
    infobox = templates.find(page.wikitext, "Infobox Object")
    if infobox is None:
        return None
    info = infobox.params
    name = strip_markup(info.get("name", "")).strip() or page.title
    pickupable = info.get("pickupable", "").strip().lower() == "yes"
    if not pickupable and name.lower() not in wanted:
        return None
    item: dict = {"name": name, "source_url": source_url(page.title)}
    if image_url and image_url.startswith(SPRITE_URL_PREFIX):
        item["image_url"] = image_url
    category = strip_markup(info.get("primarytype", "")).strip()
    if category:
        item["category"] = category
    weight = _weight(info.get("weight", ""))
    if weight is not None:
        item["weight"] = weight
    # 0 na wiki znaczy „NPC tego nie kupuje/nie sprzedaje”, więc zapisujemy tylko ceny > 0.
    for field, key in (("value", "npcvalue"), ("price", "npcprice")):
        number = _number(info.get(key, ""))
        if number:
            item[field] = number
    for field, key in (("sell_to", "sellto"), ("buy_from", "buyfrom")):
        trades = parse_trades(info.get(key, ""))
        if trades:
            item[field] = trades
    return item


def build(pages: dict[str, WikiPage], images: dict[str, str | None], data: dict) -> list[dict]:
    wanted = loot_names(data)
    items = {}
    for title, page in pages.items():
        item = make_item(page, images.get(sprite_file(title)), wanted)
        if item is not None:
            items.setdefault(item["name"].lower(), item)
    return sorted(items.values(), key=lambda i: i["name"].lower())
