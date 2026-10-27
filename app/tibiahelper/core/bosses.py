"""Bossy: ile killi trzeba w Bosstiary i lista do zakładki „Bossy”. Bez Qt, żeby łatwo testować."""

from dataclasses import dataclass

from .i18n import N_, tr
from .models import Boss, Monster

# Z TibiaWiki (Bosstiary): killi do poziomów Prowess / Expertise / Mastery i punkty za każdy poziom.
BOSSTIARY_KILLS = {"Bane": (25, 100, 300), "Archfoe": (5, 20, 60), "Nemesis": (1, 3, 5)}
BOSSTIARY_POINTS = {"Bane": (5, 15, 30), "Archfoe": (10, 30, 60), "Nemesis": (10, 30, 60)}
BOSSTIARY_STAGES = ("Prowess", "Expertise", "Mastery")
# Pierwsza pozycja filtra listy: wszystkie klasy. Polska nazwa jest kluczem, w menu tr(nazwa).
ALL_CLASSES = N_("Wszystkie klasy")
NO_CLASS = N_("Poza Bosstiary")


@dataclass(frozen=True)
class BossEntry:
    """Wiersz listy: potwór (dane podstawowe) i opis autora (None = boss jeszcze nie dodany)."""

    monster: Monster
    boss: Boss | None = None


def boss_entries(monsters: dict[str, Monster], bosses: list[Boss], author_mode: bool) -> list[BossEntry]:
    """Bossy do listy, alfabetycznie.

    Gracz widzi tylko bossy dodane i przejrzane przez autora. Autor widzi wszystkie bossy
    z bazy potworów (także niedodane), żeby móc dodać każdego.
    """
    added = {boss.monster: boss for boss in bosses if author_mode or boss.is_visible}
    if author_mode:
        chosen = [m for m in monsters.values() if m.boss or m.id in added]
    else:
        chosen = [monsters[monster_id] for monster_id in added if monster_id in monsters]
    entries = [BossEntry(m, added.get(m.id)) for m in chosen]
    return sorted(entries, key=lambda e: e.monster.name.lower())


def filter_entries(entries: list[BossEntry], text: str, boss_class: str) -> list[BossEntry]:
    """Wyszukiwanie po nazwie i filtr klasy (ALL_CLASSES = bez filtra, NO_CLASS = bez klasy)."""
    text = text.strip().lower()
    found = [e for e in entries if text in e.monster.name.lower()]
    if boss_class == ALL_CLASSES:
        return found
    wanted = None if boss_class == NO_CLASS else boss_class
    return [e for e in found if e.monster.bosstiary_class == wanted]


def format_cooldown(hours: float) -> str:
    """20 -> "20 h", 0.5 -> "30 min", 336 -> "14 dni"."""
    if hours < 1:
        return f"{round(hours * 60)} min"
    if hours >= 48 and hours % 24 == 0:
        return tr("{n} dni", n=int(hours // 24))
    return f"{hours:g} h"
