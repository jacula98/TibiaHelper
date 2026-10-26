"""NPC z data/quests.json (lista "npcs") dla edytora: wybór NPC do pinezki.

Listę robi generator (`python -m generator npcs`) z TibiaWiki.
"""

from pydantic import ValidationError

from .models import Npc


def npcs_from_data(data: dict) -> list[Npc]:
    """Wszyscy poprawni NPC z surowego pliku (także kilku o tym samym imieniu)."""
    result = []
    for raw in data.get("npcs", []):
        try:
            result.append(Npc.model_validate(raw))
        except ValidationError:
            continue  # błędny wpis: edytor po prostu go nie pokaże
    return result


def find_npc(npcs: list[Npc], text: str) -> Npc | None:
    """NPC o imieniu takim jak zaznaczony tekst (bez względu na wielkość liter)."""
    wanted = text.strip().lower()
    return next((npc for npc in npcs if npc.name.lower() == wanted), None)
