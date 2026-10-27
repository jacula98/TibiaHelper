"""Hunt/Bestiary zones: filtry listy miejsc huntów i ile killi trzeba do Bestiary. Bez Qt."""

from collections.abc import Callable

from .i18n import N_
from .models import Hunt, Monster

# Z TibiaWiki (Bestiary): killi do 1., 2. i ostatniego etapu oraz charm pointy za całość.
BESTIARY_KILLS = {
    "Harmless": (5, 10, 25),
    "Trivial": (10, 100, 250),
    "Easy": (25, 250, 500),
    "Medium": (50, 500, 1000),
    "Hard": (100, 1000, 2500),
    "Challenging": (200, 2000, 5000),
}
VERY_RARE_KILLS = (2, 3, 5)
CHARM_POINTS = {"Harmless": 1, "Trivial": 5, "Easy": 15, "Medium": 25, "Hard": 50, "Challenging": 100}
VERY_RARE_CHARM_POINTS = {"Harmless": 5, "Trivial": 10, "Easy": 30, "Medium": 50, "Hard": 100, "Challenging": 200}

# Polska nazwa jest kluczem (zapis w danych listy), w menu tr(nazwa).
ANY_VOCATION = N_("Każda profesja")
VOCATIONS = {"knight": "Knight", "paladin": "Paladin", "mage": "Druid / Sorcerer"}
ALL_CITIES = N_("Wszystkie miasta")


def bestiary(monster: Monster) -> tuple[tuple[int, int, int], int] | None:
    """(killi do kolejnych etapów, charm pointy) albo None, gdy potwora nie ma w Bestiary."""
    level = monster.bestiary_level
    if level not in BESTIARY_KILLS:
        return None
    if monster.very_rare:
        return VERY_RARE_KILLS, VERY_RARE_CHARM_POINTS[level]
    return BESTIARY_KILLS[level], CHARM_POINTS[level]


def hunt_level(hunt: Hunt, vocation: str | None) -> int | None:
    """Zalecany poziom dla profesji; bez profesji najniższy z podanych."""
    if vocation is not None:
        return hunt.levels.get(vocation)
    return min(hunt.levels.values()) if hunt.levels else None


def filter_hunts(
    hunts: list[Hunt],
    text: str = "",
    level: int | None = None,
    vocation: str | None = None,
    city: str | None = None,
    monster_names: dict[str, str] | None = None,
) -> list[Hunt]:
    """Wyszukiwanie po nazwie, mieście i potworach (monster_names: id -> nazwa);
    poziom: tylko miejsca na mój lvl (bez nieznanego lvl)."""
    text = text.strip().lower()
    names = monster_names or {}
    result = []
    for hunt in hunts:
        searchable = [hunt.name, hunt.city or "", *(names.get(m, "") for m in hunt.monster_ids())]
        if text and not any(text in value.lower() for value in searchable):
            continue
        if city is not None and hunt.city != city:
            continue
        if level is not None:
            needed = hunt_level(hunt, vocation)
            if needed is None or needed > level:
                continue
        result.append(hunt)
    return result


def _stars(value: int | None) -> int:
    return value or 0


# Sortowanie: nazwa -> klucz (malejąco = minus). Przy remisie alfabetycznie (sorted jest stabilne).
SORTS: dict[str, Callable[[Hunt, str | None], object]] = {
    # Najpierw miejsca z najwyższym poziomem, który już mam: zwykle najlepszy exp.
    N_("Poziom malejąco"): lambda h, voc: -(hunt_level(h, voc) or 0),
    N_("Poziom rosnąco"): lambda h, voc: hunt_level(h, voc) or 0,
    N_("Exp (gwiazdki)"): lambda h, voc: -_stars(h.exp_stars),
    N_("Loot (gwiazdki)"): lambda h, voc: -_stars(h.loot_stars),
    "A–Z": lambda h, voc: 0,
}


def sort_hunts(hunts: list[Hunt], sort: str, vocation: str | None = None) -> list[Hunt]:
    by_name = sorted(hunts, key=lambda h: h.name.lower())
    return sorted(by_name, key=lambda h: SORTS[sort](h, vocation))


def stars(value: int | None) -> str:
    """4 -> „★★★★☆”; brak oceny -> „?”."""
    return "?" if value is None else "★" * value + "☆" * (5 - value)
