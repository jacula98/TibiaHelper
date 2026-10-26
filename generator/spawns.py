"""Miejsca występowania potworów z TibiaRoute (tibiaroute.com) do data/spawns.json.

Mamy pisemną zgodę TibiaRoute (docs/zrodla-danych.md). Warunek: w programie
widoczny napis „Źródło danych: tibiaroute.com”. Dane trzymamy w osobnym pliku,
żeby po ewentualnym odwołaniu zgody dało się je usunąć jednym ruchem.
"""

import json
import re
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from tibiahelper.core.models import MAP_X_MAX, MAP_X_MIN, MAP_Y_MAX, MAP_Y_MIN
from tibiahelper.core.storage import write_bytes_atomic

from .quests import title_from_url
from .wiki_api import USER_AGENT

SPAWNS_URL = "https://tibiaroute.com/api/monsters-map-spawn"
SOURCE = "https://tibiaroute.com"
SPAWNS_FILE = Path(__file__).resolve().parents[1] / "data" / "spawns.json"


def download() -> list:
    request = urllib.request.Request(SPAWNS_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
        return json.load(response)


def _key(name: str) -> str:
    # „Monk (Creature)” na wiki to „Monk” w TibiaRoute.
    return re.sub(r"\s*\(creature\)$", "", name.strip().lower())


def build(raw: list, monsters: list[dict]) -> tuple[dict, list[str]]:
    """{"source", "version", "monsters": {id: [[x, y, z], ...]}} i nazwy bez pary w naszych danych."""
    ids = {}
    for monster in monsters:
        ids.setdefault(_key(monster["name"]), monster["id"])
        ids.setdefault(_key(title_from_url(monster["source_url"])), monster["id"])
    result: dict[str, list] = {}
    unmatched = []
    for entry in raw:
        name = entry.get("monster", {}).get("name", "")
        monster_id = ids.get(_key(name))
        if monster_id is None:
            unmatched.append(name)
            continue
        points = result.setdefault(monster_id, [])
        for spawn in entry.get("spawns", []):
            x, y, z = spawn.get("x"), spawn.get("y"), spawn.get("z")
            # Tylko punkty, które da się pokazać na naszej mapie.
            if (
                isinstance(x, int) and isinstance(y, int) and isinstance(z, int)
                and MAP_X_MIN <= x <= MAP_X_MAX and MAP_Y_MIN <= y <= MAP_Y_MAX and 0 <= z <= 15
            ):
                points.append([x, y, z])
    data = {
        "source": SOURCE,
        # Wersja jako data RRRRMMDD: aplikacja bierze nowszą kopię (wbudowaną albo pobraną).
        "version": int(datetime.now(UTC).strftime("%Y%m%d")),
        "monsters": {k: sorted(v) for k, v in sorted(result.items()) if v},
    }
    return data, unmatched


def save(data: dict, path: Path = SPAWNS_FILE) -> None:
    # Bez wcięć: ok. 80 tys. punktów z wcięciami zajęłoby kilka razy więcej miejsca.
    text = json.dumps(data, separators=(",", ":")) + "\n"
    write_bytes_atomic(path, text.encode("utf-8"))
