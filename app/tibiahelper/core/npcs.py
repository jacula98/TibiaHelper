"""NPC z pozycjami (data/npcs.json) do pinezek w edytorze (tryb autora).

Plik robi generator (`python -m generator npcs`) z TibiaWiki. Gracze go nie
potrzebują, więc nie trafia do aktualizacji, tylko leży obok quests.json.
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from .models import MAP_X_MAX, MAP_X_MIN, MAP_Y_MAX, MAP_Y_MIN

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Npc:
    name: str
    x: int
    y: int
    z: int
    city: str = ""

    @property
    def title(self) -> str:
        """Tekst na liście: imię i miasto (NPC o tym samym imieniu bywa kilku)."""
        return f"{self.name} ({self.city})" if self.city else self.name


def _parse(raw: object) -> Npc | None:
    if not isinstance(raw, dict):
        return None
    name, city = raw.get("name"), raw.get("city", "")
    x, y, z = raw.get("x"), raw.get("y"), raw.get("z")
    if not isinstance(name, str) or not name or not isinstance(city, str):
        return None
    if not all(isinstance(v, int) for v in (x, y, z)):
        return None
    if not (MAP_X_MIN <= x <= MAP_X_MAX and MAP_Y_MIN <= y <= MAP_Y_MAX and 0 <= z <= 15):
        return None
    return Npc(name, x, y, z, city)


def load_npcs(path: Path) -> list[Npc]:
    """NPC z pliku; brak pliku albo zły format daje pustą listę (edytor działa wtedy jak dawniej)."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        log.warning("Nie udało się wczytać %s: %s", path, exc)
        return []
    items = raw.get("npcs") if isinstance(raw, dict) else None
    return [npc for item in items or [] if (npc := _parse(item)) is not None]


def find_npc(npcs: list[Npc], text: str) -> Npc | None:
    """NPC o imieniu takim jak zaznaczony tekst (bez względu na wielkość liter)."""
    wanted = text.strip().lower()
    return next((npc for npc in npcs if npc.name.lower() == wanted), None)
