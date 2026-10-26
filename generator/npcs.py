"""NPC z TibiaWiki do listy "npcs" w data/quests.json: imię, miasto, pozycja i obrazek.

Z tej listy korzysta edytor (pinezka NPC po imieniu) i aplikacja: postać NPC
przy kroku oraz „komu sprzedać” w zakładce „Przedmioty”.
"""

from tibiahelper.core.models import MAP_X_MAX, MAP_X_MIN, MAP_Y_MAX, MAP_Y_MIN, SPRITE_URL_PREFIX

from . import templates
from .monsters import sprite_file
from .wiki_api import WikiPage
from .wikitext import infobox_position, strip_markup


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


def build(pages: dict[str, WikiPage], images: dict[str, str | None] | None = None) -> list[dict]:
    images = images or {}
    npcs = [
        npc for title, page in pages.items() if (npc := make_npc(page, images.get(sprite_file(title)))) is not None
    ]
    return sorted(npcs, key=lambda n: (n["name"].lower(), n.get("city", "")))
