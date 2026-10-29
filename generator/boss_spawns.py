"""Bossy ze spawnem na świecie -> data/boss_spawns.json (do powiadomień „boss na serwerze”).

Bierzemy bossy z data/quests.json, których pole `spawntype` na TibiaWiki ma „Raid”
albo „Unique” bez „Triggered”. Bossy z questów i instancji („Triggered”) giną codziennie,
więc w powiadomieniach tylko by przeszkadzały.

Dochodzą też bossy z wykresami „Spawn Frequency” na TibiaWiki (np. Ghazbaran: wiki nie ma
u niego `spawntype`). Okna respawnu (`respawn_days`) odczytaliśmy z tych wykresów (dane GuildStats.eu):
od–do dni, w których boss pojawia się najczęściej. Bossy bez wyraźnego okna (np. White Pale,
który ma kilka miejsc) nie mają go wcale. Okno wpisane ręcznie w pliku ma pierwszeństwo.

Lista światów do ustawień: strony z {{Infobox World}} bez daty zamknięcia.
"""

import json
import re
import urllib.parse
from pathlib import Path

from tibiahelper.core.storage import write_bytes_atomic

from . import bulk, templates
from .quests_file import DATA_FILE
from .wiki_api import WikiClient

BOSS_SPAWNS_FILE = DATA_FILE.with_name("boss_spawns.json")
SPAWN_FREQUENCY_PAGE = "TibiaWiki:Bosses Spawn Frequency"

# Z wykresów na stronie SPAWN_FREQUENCY_PAGE (nazwa z wiki -> dni od, do), stan na 2026-10-29.
RESPAWN_DAYS: dict[str, tuple[int, int]] = {
    "Ferumbras": (162, 176),
    "Ghazbaran": (162, 176),
    "Morgaroth": (169, 177),
    "Orshabaal": (161, 177),
    "Gaz'haragoth": (13, 28),
    "Zevelon Duskbringer": (6, 10),
    "Sir Valorcrest": (5, 9),
    "Diblis the Fair": (10, 16),
    "Arachir the Ancient One": (6, 9),
    "Zushuka": (19, 29),
    "Ocyakao": (16, 26),
    "Man in the Cave": (12, 16),
    "Captain Jones": (6, 10),
    "Countess Sorrow": (14, 21),
    "The Handmaiden": (14, 21),
    "Massacre": (14, 21),
    "The Imperor": (14, 21),
    "Dracola": (14, 21),
    "Mr. Punish": (14, 21),
    "The Plasmother": (14, 21),
    "Dharalion": (5, 8),
    "Fernfang": (20, 27),
    "Munster": (1, 7),
    "The Frog Prince": (12, 18),
    "The Pale Count": (16, 30),
    "The Welter": (16, 29),
    "Hatebreeder": (6, 9),
    "General Murius": (6, 9),
    "Zulazza the Corruptor": (7, 20),
    "Gravelord Oshuran": (7, 11),
    "Hairman the Huge": (5, 10),
    "Smuggler Baron Silvertoe": (9, 14),
    "The Big Bad One": (6, 11),
    "Omrafir": (14, 28),
    "Weakened Shlorg": (13, 29),
}


def is_world_spawn(spawntype: str) -> bool:
    """„Raid, Unique” -> True, „Triggered, Unique” -> False, „Regular” -> False."""
    types = {part.strip().lower() for part in spawntype.split(",") if part.strip()}
    return "raid" in types or ("unique" in types and "triggered" not in types)


def _title(monster: dict) -> str:
    return urllib.parse.unquote(monster["source_url"].rsplit("/wiki/", 1)[1]).replace("_", " ")


def plotted_bosses(wikitext: str) -> set[str]:
    """Nazwy bossów z galerii wykresów: „Spawn Frequency - Ferumbras.png|Ferumbras” -> „Ferumbras”."""
    return {m.group(1).strip() for m in re.finditer(r"^Spawn Frequency - [^|\n]+\|([^\n]+)$", wikitext, re.M)}


def active_worlds(pages: dict[str, str]) -> list[str]:
    """Światy, które dziś działają: {{Infobox World}} bez `offline` i bez statusu „deprecated”."""
    worlds = []
    for title, wikitext in pages.items():
        infobox = templates.find(wikitext, "Infobox World")
        if infobox is None or infobox.params.get("offline", "").strip():
            continue
        if infobox.params.get("ingamestatus", "").strip().lower() == "deprecated":
            continue
        name = infobox.params.get("name", "").strip() or title
        if re.fullmatch(r"[A-Za-z]{3,30}", name):
            worlds.append(name)
    return sorted(set(worlds))


def build(
    monsters: list[dict],
    pages: dict[str, str],
    old: dict | None = None,
    plotted: set[str] | None = None,
    worlds: list[str] | None = None,
) -> dict:
    """Plik z listą bossów. pages: {tytuł strony: wikitekst}. old: obecny plik (okna respawnu autora)."""
    manual = {
        entry["monster"]: entry["respawn_days"]
        for entry in (old or {}).get("bosses", [])
        if isinstance(entry, dict) and entry.get("respawn_days")
    }
    plotted = {name.lower() for name in plotted or set()}
    respawn = {name.lower(): days for name, days in RESPAWN_DAYS.items()}
    bosses = []
    for monster in monsters:
        if not monster.get("boss") or monster.get("event") or monster.get("unavailable"):
            continue
        infobox = templates.find(pages.get(_title(monster), ""), "Infobox Creature")
        world_spawn = infobox is not None and is_world_spawn(infobox.params.get("spawntype", ""))
        name = monster.get("name", "").lower()
        if not world_spawn and name not in plotted:
            continue
        entry: dict = {"monster": monster["id"]}
        days = manual.get(monster["id"]) or respawn.get(name)
        if days:
            entry["respawn_days"] = list(days)
        bosses.append(entry)
    bosses.sort(key=lambda e: e["monster"])
    return {
        "version": 1,
        "source": "TibiaWiki (spawntype, wykresy Spawn Frequency z danymi GuildStats.eu), CC BY-SA 4.0",
        "bosses": bosses,
        "worlds": worlds if worlds is not None else (old or {}).get("worlds", []),
    }


def update(data: dict, client: WikiClient, refresh: bool = False, path: Path = BOSS_SPAWNS_FILE) -> int:
    """Pobiera strony bossów (z cache generatora) i zapisuje plik. Zwraca liczbę bossów."""
    monsters = [m for m in data.get("monsters", []) if m.get("boss")]
    loaded = bulk.load_pages(client, [_title(m) for m in monsters], refresh)
    # Wykresy i światy zmieniają się częściej niż strony bossów, więc zawsze świeże (refresh=True).
    plots = bulk.load_pages(client, [SPAWN_FREQUENCY_PAGE], True)
    world_pages = bulk.load_pages(client, client.embedded_in("Infobox World"), True)
    worlds = active_worlds({title: page.wikitext for title, page in world_pages.items()})
    # Bez wykresów albo światów plik straciłby część bossów albo listę w ustawieniach: lepiej nic nie zapisać.
    if SPAWN_FREQUENCY_PAGE not in plots or not worlds:
        raise RuntimeError("Wiki nie zwróciła wykresów albo listy światów; spróbuj później")
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    result = build(
        monsters,
        {title: page.wikitext for title, page in loaded.items()},
        old,
        plotted_bosses(plots[SPAWN_FREQUENCY_PAGE].wikitext),
        worlds,
    )
    text = json.dumps(result, ensure_ascii=False, indent=1) + "\n"
    write_bytes_atomic(path, text.encode("utf-8"))
    return len(result["bosses"])
