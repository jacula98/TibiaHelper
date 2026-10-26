"""NPC z TibiaWiki do data/npcs.json: imię, miasto i pozycja na mapie.

Plik jest tylko dla edytora (tryb autora): autor wpisuje „Sven” i od razu
dostaje pinezkę w miejscu, gdzie Sven stoi. Gracze dostają tylko adresy obrazków
NPC (w data/quests.json), żeby przy kroku było widać postać.
"""

import json
from pathlib import Path

from tibiahelper.core.models import MAP_X_MAX, MAP_X_MIN, MAP_Y_MAX, MAP_Y_MIN, SPRITE_URL_PREFIX
from tibiahelper.core.storage import write_bytes_atomic

from . import templates
from .monsters import sprite_file
from .wiki_api import WikiPage
from .wikitext import infobox_position, strip_markup

NPCS_FILE = Path(__file__).resolve().parents[1] / "data" / "npcs.json"
SOURCE = "TibiaWiki (tibia.fandom.com), CC BY-SA 4.0"


def make_npc(page: WikiPage, image_url: str | None = None) -> dict | None:
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
    # Tylko adres obrazka (grafika © CipSoft); aplikacja pobiera go przy pierwszym użyciu.
    if image_url and image_url.startswith(SPRITE_URL_PREFIX):
        npc["image_url"] = image_url
    return npc


def build(pages: dict[str, WikiPage], images: dict[str, str | None] | None = None) -> dict:
    images = images or {}
    npcs = [
        npc for title, page in pages.items() if (npc := make_npc(page, images.get(sprite_file(title)))) is not None
    ]
    npcs.sort(key=lambda n: (n["name"].lower(), n.get("city", "")))
    return {"source": SOURCE, "npcs": npcs}


def images_by_name(data: dict) -> dict[str, str]:
    """Obrazki NPC po imieniu do data/quests.json: aplikacja pokazuje postać NPC przy kroku."""
    return {npc["name"]: npc["image_url"] for npc in data["npcs"] if "image_url" in npc}


def save(data: dict, path: Path = NPCS_FILE) -> None:
    # Jeden NPC w linii: plik jest czytelny i zmiany w git są małe.
    lines = [json.dumps(npc, ensure_ascii=False) for npc in data["npcs"]]
    text = '{"source": ' + json.dumps(data["source"]) + ', "npcs": [\n' + ",\n".join(lines) + "\n]}\n"
    write_bytes_atomic(path, text.encode("utf-8"))
