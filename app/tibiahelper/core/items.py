"""Przedmioty: sortowanie listy, ceny u NPC i „z jakich potworów wypada”. Bez Qt, żeby łatwo testować."""

from collections.abc import Callable
from dataclasses import dataclass

from .i18n import N_
from .models import Item, Monster, Rarity, Trade

# Kolejność od najczęstszego dropu: tak gracz czyta „skąd najłatwiej to zdobyć”.
RARITY_ORDER = ("always", "common", "uncommon", "semi-rare", "rare", "very rare")


@dataclass(frozen=True)
class Drop:
    monster: Monster
    rarity: Rarity | None


def effective_price(trade: Trade, default: int | None) -> int | None:
    """Cena u tego NPC: własna, jeśli wiki ją podaje, inaczej zwykła cena przedmiotu."""
    return trade.price if trade.price is not None else default


def best_sell_price(item: Item) -> int:
    """Najwięcej, ile da za to któryś NPC (0, gdy nikt tego nie kupuje)."""
    return max((effective_price(t, item.value) or 0 for t in item.sell_to), default=0)


def cheapest_buy_price(item: Item) -> int | None:
    """Najtaniej, za ile któryś NPC to sprzedaje (None, gdy nikt tego nie sprzedaje)."""
    prices = [p for t in item.buy_from if (p := effective_price(t, item.price))]
    return min(prices, default=None)


# Nazwa -> (filtr, klucz sortowania, malejąco?). Kolejność tu = kolejność w menu.
# Polska nazwa jest kluczem; w menu pokazujemy tr(nazwa).
ITEM_SORTS: dict[str, tuple[Callable[[Item], bool], Callable[[Item], object], bool]] = {
    "A–Z": (lambda i: True, lambda i: i.name.lower(), False),
    N_("Najdroższe u NPC"): (lambda i: bool(i.sell_to), best_sell_price, True),
    N_("Do kupienia u NPC"): (lambda i: bool(i.buy_from), lambda i: i.name.lower(), False),
    N_("Najlżejsze"): (lambda i: i.weight is not None, lambda i: i.weight, False),
}


# Filtry listy: nazwa -> „czy przedmiot należy do tej grupy”. Grupy są domyślnie ukryte,
# a gracz może je pokazać w menu „Filtry”. Kolejność tu = kolejność w menu.
ITEM_FILTERS: dict[str, Callable[[Item], bool]] = {
    N_("Quest itemy"): lambda i: i.category == "Quest Items",
    N_("Soul core"): lambda i: i.category == "Soul Cores",
    N_("Pojemniki"): lambda i: i.category == "Containers",
    N_("Bez handlu z NPC"): lambda i: not i.sell_to and not i.buy_from,
}


def sort_items(items: list[Item], sort: str) -> list[Item]:
    keep, key, reverse = ITEM_SORTS[sort]
    # Najpierw alfabetycznie, potem stabilne sortowanie po kluczu: remisy zostają w kolejności A–Z.
    by_name = sorted((i for i in items if keep(i)), key=lambda i: i.name.lower())
    return sorted(by_name, key=key, reverse=reverse)


def build_drops(monsters: dict[str, Monster]) -> dict[str, list[Drop]]:
    """Nazwa przedmiotu (małymi literami) -> potwory, z których wypada, od najczęstszego dropu."""
    drops: dict[str, list[Drop]] = {}
    for monster in monsters.values():
        for loot in monster.loot:
            drops.setdefault(loot.name.lower(), []).append(Drop(monster, loot.rarity))
    for entries in drops.values():
        entries.sort(
            key=lambda d: (RARITY_ORDER.index(d.rarity) if d.rarity else len(RARITY_ORDER), d.monster.name.lower())
        )
    return drops
