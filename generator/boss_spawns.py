"""Bossy ze spawnem na świecie -> data/boss_spawns.json (do powiadomień „boss na serwerze”).

Bierzemy bossy z data/quests.json, których pole `spawntype` na TibiaWiki ma „Raid”
albo „Unique” bez „Triggered”. Bossy z questów i instancji („Triggered”) giną codziennie,
więc w powiadomieniach tylko by przeszkadzały.

Okno respawnu (`respawn_days`, np. [3, 7]) wiki podaje tylko na wykresach, więc wpisuje je
autor ręcznie w pliku. Ta komenda go nie kasuje przy odświeżeniu.
"""

import json
import urllib.parse
from pathlib import Path

from tibiahelper.core.storage import write_bytes_atomic

from . import bulk, templates
from .quests_file import DATA_FILE
from .wiki_api import WikiClient

BOSS_SPAWNS_FILE = DATA_FILE.with_name("boss_spawns.json")


def is_world_spawn(spawntype: str) -> bool:
    """„Raid, Unique” -> True, „Triggered, Unique” -> False, „Regular” -> False."""
    types = {part.strip().lower() for part in spawntype.split(",") if part.strip()}
    return "raid" in types or ("unique" in types and "triggered" not in types)


def _title(monster: dict) -> str:
    return urllib.parse.unquote(monster["source_url"].rsplit("/wiki/", 1)[1]).replace("_", " ")


def build(monsters: list[dict], pages: dict[str, str], old: dict | None = None) -> dict:
    """Plik z listą bossów. pages: {tytuł strony: wikitekst}. old: obecny plik (okna respawnu autora)."""
    respawn = {
        entry["monster"]: entry["respawn_days"]
        for entry in (old or {}).get("bosses", [])
        if isinstance(entry, dict) and entry.get("respawn_days")
    }
    bosses = []
    for monster in monsters:
        if not monster.get("boss") or monster.get("event") or monster.get("unavailable"):
            continue
        infobox = templates.find(pages.get(_title(monster), ""), "Infobox Creature")
        if infobox is None or not is_world_spawn(infobox.params.get("spawntype", "")):
            continue
        entry: dict = {"monster": monster["id"]}
        if monster["id"] in respawn:
            entry["respawn_days"] = respawn[monster["id"]]
        bosses.append(entry)
    bosses.sort(key=lambda e: e["monster"])
    return {
        "version": 1,
        "source": "TibiaWiki (spawntype), CC BY-SA 4.0",
        "bosses": bosses,
    }


def update(data: dict, client: WikiClient, refresh: bool = False, path: Path = BOSS_SPAWNS_FILE) -> int:
    """Pobiera strony bossów (z cache generatora) i zapisuje plik. Zwraca liczbę bossów."""
    monsters = [m for m in data.get("monsters", []) if m.get("boss")]
    loaded = bulk.load_pages(client, [_title(m) for m in monsters], refresh)
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    result = build(monsters, {title: page.wikitext for title, page in loaded.items()}, old)
    text = json.dumps(result, ensure_ascii=False, indent=1) + "\n"
    write_bytes_atomic(path, text.encode("utf-8"))
    return len(result["bosses"])
