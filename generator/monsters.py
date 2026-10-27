"""Potwory z TibiaWiki do listy "monsters" w data/quests.json.

Z {{Infobox Creature}} bierzemy dane do dymka (HP, exp, żywioły) i do strony
potwora w zakładce „Potwory” (umiejętności, loot, gdzie występuje).
Obrazek to plik "<Nazwa>.gif" z wiki; zapisujemy tylko jego adres, bo grafika
należy do CipSoft i nie trafia do repo.
"""

import re

from tibiahelper.core.models import ELEMENTS, Monster

from . import cache, templates
from .quests import slugify, source_url
from .wiki_api import WikiClient, WikiPage
from .wikitext import strip_markup

_NUMBER = re.compile(r"\d+")
RARITIES = ("always", "common", "uncommon", "semi-rare", "rare", "very rare")
_AMOUNT = re.compile(r"^\d+(?:-(?:\d+|\?))?[+?]?$")  # „0-10+” albo „0-24?” (wiki nie zna górnej granicy)
MAX_LOCATION = 600  # znaków: opis miejsc bywa bardzo długi, a to ma być ściąga
# Szablony w tekście, z których zostawiamy treść zamiast je usuwać, np. {{KW|permission}}.
_KEEP_TEXT = re.compile(r"\{\{(?:KW|Link|Hover)\|([^{}|]*)[^{}]*\}\}")


def _number(value: str) -> int | None:
    # Na wiki bywa "100%", "1,500" albo "?" (nieznane).
    match = _NUMBER.search(value.replace(",", ""))
    return int(match.group()) if match else None


def _text(value: str) -> str:
    return strip_markup(_KEEP_TEXT.sub(r"\1", value))


def sprite_file(name: str) -> str:
    return name.replace(" ", "_") + ".gif"


def _ability(item: templates.Template) -> str | None:
    """Jedna umiejętność jako krótki tekst, np. "Great Fireball: 150-250 (fire)"."""
    args = [_text(a) for a in item.args if _text(a)]
    element = item.params.get("element")
    if item.name == "Melee":
        text = f"Melee: {args[0]}" if args else "Melee"
        return text + (f" ({_text(element)})" if element else "")
    if item.name in ("Ability", "Debuff", "Healing", "Haste", "Summon"):
        if not args and not item.params:
            return item.name
        label = args[0] if args else item.name
        rest = args[1:]
        if item.name == "Healing" and "range" in item.params:
            rest = [_text(item.params["range"])]
        if item.name == "Summon":
            label = f"Summon {label}"
        details = " ".join(rest[:1])
        kind = _text(element) if element else (rest[1] if len(rest) > 1 else "")
        text = f"{label}: {details}" if details else label
        return text + (f" ({kind})" if kind else "")
    return None  # nieznane szablony (np. sceny, opisy) pomijamy


def _abilities(value: str) -> list[str]:
    ability_list = templates.find(value, "Ability List")
    if ability_list is None:
        text = _text(value)
        return [text] if text and text != "--" else []
    found = []
    for arg in ability_list.args:
        for item in templates.children(arg):
            text = _ability(item)
            if text:
                found.append(text)
    return found


def _loot(value: str) -> list[dict]:
    table = templates.find(value, "Loot Table")
    if table is None:
        return []
    loot = []
    for arg in table.args:
        for item in templates.children(arg):
            if item.name != "Loot Item":
                continue
            entry: dict = {}
            for raw in item.args:
                part = _text(raw)
                if _AMOUNT.match(part):
                    entry["amount"] = part
                elif part.lower() in RARITIES:
                    entry["rarity"] = part.lower()
                elif part and "name" not in entry:
                    entry["name"] = part
            if "name" in entry:
                loot.append(entry)
    return loot


# Statusy z wiki dla potworów, których nie ma już w grze (albo są tylko na serwerach testowych).
UNAVAILABLE_STATUSES = {"unavailable", "deprecated", "ts-only"}
# Sposoby pojawiania się, które nie oznaczają zwykłego spawnu.
_NON_REGULAR_SPAWNS = {"event", "triggered", "unblockable", "unique"}


def _is_event(info: dict[str, str]) -> bool:
    """Potwór eventowy: typ „Event Creatures”, status „event” albo spawn tylko na evencie."""
    types = {info.get("primarytype", "").strip(), info.get("secondarytype", "").strip()}
    if "Event Creatures" in types or info.get("status", "").strip().lower() == "event":
        return True
    spawns = {part.strip().lower() for part in info.get("spawntype", "").split(",") if part.strip()}
    return "event" in spawns and spawns <= _NON_REGULAR_SPAWNS


def _bosstiary_class(info: dict[str, str]) -> str | None:
    # Na wiki bywa „archfoe” albo z dopiskiem; bierzemy tylko trzy znane kategorie.
    value = _text(info.get("bosstiaryclass", "")).strip().lower()
    return next((name for name in ("Bane", "Archfoe", "Nemesis") if value.startswith(name.lower())), None)


_COOLDOWN = re.compile(r"^(\d+(?:\.\d+)?)\s*(seconds?|minutes?|hours?|days?)?$")
_UNIT_HOURS = {"second": 1 / 3600, "minute": 1 / 60, "hour": 1, "day": 24}


def cooldown_hours(value: str) -> float | None:
    """Cooldown bossa w godzinach. Wiki pisze zwykle samą liczbę godzin („20”), czasem „10 minutes”."""
    match = _COOLDOWN.match(_text(value).strip().lower())
    if match is None:
        return None
    number, unit = float(match.group(1)), (match.group(2) or "hour").rstrip("s")
    hours = round(number * _UNIT_HOURS[unit], 3)
    # 0 na wiki to brak cooldownu albo brak danych; i tak nic graczowi nie mówi.
    return hours or None


def make_monster(page: WikiPage, image_url: str | None, monster_id: str | None = None) -> dict:
    """Wpis potwora z wikitekstu strony. Rzuca ValueError, gdy strona nie jest potworem."""
    infobox = templates.find(page.wikitext, "Infobox Creature")
    if infobox is None:
        raise ValueError(f"{page.title!r} nie ma {{{{Infobox Creature}}}}: to nie jest potwór?")
    info = infobox.params
    elements = {}
    for element in ELEMENTS:
        percent = _number(info.get(f"{element}dmgmod", ""))
        # 100% = zwykłe obrażenia, więc zapisujemy tylko wyjątki.
        if percent is not None and percent != 100:
            elements[element] = percent
    location = _text(info.get("location", ""))
    if len(location) > MAX_LOCATION:
        location = location[:MAX_LOCATION].rsplit(" ", 1)[0] + " …"
    monster = {
        "id": monster_id or slugify(page.title),
        "name": _text(info.get("name", "")) or page.title,
        "hp": _number(info.get("hp", "")) or 0,
        "exp": _number(info.get("exp", "")) or 0,
        "elements": elements,
        "image_url": image_url,
        "source_url": source_url(page.title),
        "wiki_revision": page.revid,
        "armor": _number(info.get("armor", "")),
        "speed": _number(info.get("speed", "")),
        "boss": info.get("isboss", "").strip().lower() == "yes",
        "event": _is_event(info),
        "unavailable": info.get("status", "").strip().lower() in UNAVAILABLE_STATUSES,
        "bestiary_class": _text(info.get("bestiaryclass", "")) or None,
        "bestiary_level": _text(info.get("bestiarylevel", "")) or None,
        "bosstiary_class": _bosstiary_class(info),
        "cooldown_hours": cooldown_hours(info.get("cooldown", "")),
        "abilities": _abilities(info.get("abilities", "")),
        "loot": _loot(info.get("loot", "")),
        "location": location or None,
    }
    # Puste pola wyrzucamy, żeby plik był mniejszy (model ma dla nich wartości domyślne).
    # „is”, a nie „in (…False)”: w Pythonie 0 == False, a armor 0 to prawdziwa wartość.
    monster = {k: v for k, v in monster.items() if not (v is None or v is False or v == [] or v == {})}
    # Ta sama walidacja co w aplikacji, zanim cokolwiek trafi do pliku.
    Monster.model_validate(monster)
    return monster


def fetch_page(client: WikiClient, title: str, refresh: bool = False) -> WikiPage:
    page = None if refresh else cache.load(title)
    if page is None:
        page = client.get_pages([title])[title]
        if page is None:
            raise LookupError(f"Na TibiaWiki nie ma strony {title!r}")
        cache.save(title, page)
    return page


def fetch_monster(client: WikiClient, title: str, monster_id: str | None = None, refresh: bool = False) -> dict:
    page = fetch_page(client, title, refresh)
    file_name = sprite_file(page.title)
    url = client.image_urls([file_name])[file_name]
    if url is None:
        raise LookupError(f"Na TibiaWiki nie ma obrazka {file_name!r}")
    return make_monster(page, url, monster_id)
