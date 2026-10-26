"""NPC z TibiaWiki do data/npcs.json: imię, miasto i pozycja na mapie.

Plik jest tylko dla edytora (tryb autora): autor wpisuje „Sven” i od razu
dostaje pinezkę w miejscu, gdzie Sven stoi. Gracze go nie potrzebują.
"""

import json
from pathlib import Path

from tibiahelper.core.models import MAP_X_MAX, MAP_X_MIN, MAP_Y_MAX, MAP_Y_MIN
from tibiahelper.core.storage import write_bytes_atomic

from . import templates
from .wiki_api import WikiPage
from .wikitext import infobox_position, strip_markup

NPCS_FILE = Path(__file__).resolve().parents[1] / "data" / "npcs.json"
SOURCE = "TibiaWiki (tibia.fandom.com), CC BY-SA 4.0"


def make_npc(page: WikiPage) -> dict | None:
    """NPC ze strony albo None (strona bez infoboksu NPC albo bez pozycji na mapie)."""
    infobox = templates.find(page.wikitext, "Infobox NPC")
    if infobox is None:
        return None
    position = infobox_position(page.wikitext)
    if position is None:
        return None
    if not (MAP_X_MIN <= position["x"] <= MAP_X_MAX and MAP_Y_MIN <= position["y"] <= MAP_Y_MAX):
        return None
    if not 0 <= position["z"] <= 15:
        return None
    name = strip_markup(infobox.params.get("name", "")).strip() or page.title
    city = strip_markup(infobox.params.get("city", "")).strip()
    npc = {"name": name, **position}
    if city:
        npc["city"] = city
    return npc


def build(pages: dict[str, WikiPage]) -> dict:
    npcs = [npc for page in pages.values() if (npc := make_npc(page)) is not None]
    npcs.sort(key=lambda n: (n["name"].lower(), n.get("city", "")))
    return {"source": SOURCE, "npcs": npcs}


def save(data: dict, path: Path = NPCS_FILE) -> None:
    # Jeden NPC w linii: plik jest czytelny i zmiany w git są małe.
    lines = [json.dumps(npc, ensure_ascii=False) for npc in data["npcs"]]
    text = '{"source": ' + json.dumps(data["source"]) + ', "npcs": [\n' + ",\n".join(lines) + "\n]}\n"
    write_bytes_atomic(path, text.encode("utf-8"))
