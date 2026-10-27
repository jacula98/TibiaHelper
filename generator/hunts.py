"""Miejsca huntów z TibiaWiki (strony z {{Infobox Hunt}}) do data/quests.json („hunts”).

Z wiki bierzemy: miasto, opis miejsca, zalecany poziom dla profesji, gwiazdki exp/loot,
najlepszy loot, potwory w częściach miejsca (sekcje z {{CreatureList}}) i wejście
(pierwsze {{Mapper Coords}}). Trasę i uwagi dopisuje autor, więc przy odświeżaniu ich nie ruszamy.
"""

import re

from tibiahelper.core.models import Hunt

from . import templates
from .quests import slugify, source_url
from .wiki_api import WikiPage
from .wikitext import BLOCK, strip_markup

# Słowne oceny z wiki, gdy nie ma pola z gwiazdkami.
_RATINGS = {"very bad": 1, "bad": 2, "average": 3, "good": 4, "very good": 5}
_LEVELS = {"knight": "lvlknights", "paladin": "lvlpaladins", "mage": "lvlmages"}
_HEADING = re.compile(r"^(=+)\s*(.*?)\s*\1\s*$", re.MULTILINE)
# Nowy zapis {{Mapper Coords|128.185|127.173|7|...}} albo stary link „Mapper?coords=126.191,125.101,15”.
_MAPPER = re.compile(r"\{\{Mapper Coords\|(\d+)\.(\d+)\|(\d+)\.(\d+)\|(\d+)")
_OLD_MAPPER = re.compile(r"Mapper\?coords=(\d+)\.(\d+),(\d+)\.(\d+),(\d+)")
MAX_TEXT = 400


def _stars(stars: str, rating: str) -> int | None:
    value = stars.strip()
    if value.isdigit() and 1 <= int(value) <= 5:
        return int(value)
    return _RATINGS.get(rating.strip().lower())


def _level(value: str) -> int | None:
    match = re.match(r"\s*(\d+)", value)
    return int(match.group(1)) if match else None


def _entrance(text: str, name: str) -> dict | None:
    match = _MAPPER.search(text) or _OLD_MAPPER.search(text)
    if match is None:
        return None
    bx, ox, by, oy, z = (int(g) for g in match.groups())
    return {"x": bx * BLOCK + ox, "y": by * BLOCK + oy, "z": z, "label": name}


def _areas(wikitext: str, monster_ids: dict[str, str]) -> list[dict]:
    """Potwory z każdego {{CreatureList}}, podpisane najbliższym nagłówkiem nad nim (np. „Ground floor”)."""
    headings = [(m.start(), strip_markup(m.group(2))) for m in _HEADING.finditer(wikitext)]
    areas: dict[str | None, list[str]] = {}
    start = wikitext.find("{{CreatureList")
    while start >= 0:
        end = templates._closing(wikitext, start)
        template = templates.parse(wikitext[start:end])
        heading = next((title for pos, title in reversed(headings) if pos < start), None)
        # Nagłówek „Creatures” to po prostu cała lista, a nie część miejsca.
        name = None if heading is None or heading.lower() in ("creatures", "creature") else heading
        for arg in template.args:
            monster_id = monster_ids.get(strip_markup(arg).strip().lower())
            if monster_id is not None and monster_id not in areas.setdefault(name, []):
                areas[name].append(monster_id)
        start = wikitext.find("{{CreatureList", end)
    return [{"name": name, "monsters": ids} if name else {"monsters": ids} for name, ids in areas.items() if ids]


def _clean(text: str) -> str:
    # Po usunięciu {{Mapper Coords}} zostaje np. „in Tiquanda, .”: sprzątamy spacje i przecinki przed kropką.
    text = re.sub(r"\s+([,.])", r"\1", text)
    return re.sub(r",+\.", ".", text).rstrip(" ,")


def _short(text: str) -> str:
    text = _clean(text)
    return text if len(text) <= MAX_TEXT else text[:MAX_TEXT].rsplit(" ", 1)[0] + " …"


def make_hunt(page: WikiPage, monster_ids: dict[str, str], old: dict | None = None) -> dict | None:
    """Wpis miejsca huntu albo None, gdy strona nie ma infoboxu (np. strona zbiorcza)."""
    infobox = templates.find(page.wikitext, "Infobox Hunt")
    if infobox is None:
        return None
    info = infobox.params
    name = strip_markup(info.get("name", "")) or page.title
    hunt = {
        "id": (old or {}).get("id") or slugify(page.title),
        "name": name,
        "source_url": source_url(page.title),
        "wiki_revision": page.revid,
        "city": strip_markup(info.get("city", "")) or None,
        "location": _short(strip_markup(info.get("location", ""))) or None,
        "levels": {voc: lvl for voc, key in _LEVELS.items() if (lvl := _level(info.get(key, ""))) is not None},
        "exp_stars": _stars(info.get("expstar", ""), info.get("exp", "")),
        "loot_stars": _stars(info.get("lootstar", ""), info.get("loot", "")),
        "best_loot": [
            item for key in ("bestloot", "bestloot2", "bestloot3", "bestloot4", "bestloot5")
            if (item := strip_markup(info.get(key, "")))
        ],
        "areas": _areas(page.wikitext, monster_ids),
        "entrance": _entrance(info.get("location", "") + page.wikitext, name),
    }
    # Pracy autora nie nadpisujemy przy odświeżaniu z wiki.
    for key in ("route", "notes"):
        if (old or {}).get(key):
            hunt[key] = old[key]
    hunt = {k: v for k, v in hunt.items() if v not in (None, [], {})}
    Hunt.model_validate(hunt)
    return hunt


def build(pages: dict[str, WikiPage], data: dict) -> list[dict]:
    """Wszystkie miejsca huntów, alfabetycznie. Potwory dopasowujemy po nazwie (jak w spawns.py)."""
    monster_ids: dict[str, str] = {}
    for monster in data.get("monsters", []):
        monster_ids.setdefault(monster["name"].lower(), monster["id"])
        monster_ids.setdefault(re.sub(r"\s*\(creature\)$", "", monster["name"].lower()), monster["id"])
    old = {h["source_url"]: h for h in data.get("hunts", [])}
    hunts = []
    taken: set[str] = set()
    for title in sorted(pages):
        if title.startswith(("User:", "Template:")):
            continue  # brudnopisy edytorów wiki
        page = pages[title]
        hunt = make_hunt(page, monster_ids, old.get(source_url(page.title)))
        if hunt is None or hunt["id"] in taken:
            continue
        taken.add(hunt["id"])
        hunts.append(hunt)
    return hunts
