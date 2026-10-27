"""Wyszukiwanie i filtrowanie questów oraz list (potwory, przedmioty). Czysta logika, bez Qt."""

import re
import unicodedata
from collections.abc import Callable, Iterable
from typing import TypeVar

from .models import Quest

# Szkice z importu zaczynają sekcję od „[Nazwa misji] …”, np. „[The Curse Spreads] …”.
_SECTION = re.compile(r"^\[([^\]]+)\]")


def _normalize(text: str) -> str:
    # casefold zamiast lower: poprawnie porównuje też np. niemieckie "ß".
    # Usuwamy akcenty, żeby "zolw" znalazło "żółw".
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).replace("ł", "l")


def filter_quests(
    quests: Iterable[Quest],
    query: str = "",
    player_level: int | None = None,
) -> list[Quest]:
    """Zwraca questy pasujące do wyszukiwania, posortowane po levelu i nazwie.

    query: fragment nazwy; każde słowo musi wystąpić w nazwie (kolejność dowolna).
        Pasuje też nazwa misji z kroków, bo wiki trzyma misje (np. „The Curse Spreads”)
        wewnątrz większego questa („Grimvale Quest”), a gracze szukają po nazwie misji.
    player_level: pokazuje tylko questy z min_level <= player_level; None = bez filtra.
    """
    words = _normalize(query).split()
    result = []
    for quest in quests:
        name = _normalize(quest.name)
        if not all(word in name for word in words) and not any(
            all(word in section for word in words) for section in _sections(quest)
        ):
            continue
        if player_level is not None and quest.min_level > player_level:
            continue
        result.append(quest)
    return sorted(result, key=lambda q: (q.min_level, _normalize(q.name)))


def _sections(quest: Quest) -> list[str]:
    found = (_SECTION.match(step.text) for step in quest.steps)
    # „[The Curse Spreads / Edron]”: każda część osobno, żeby słowa nie mieszały się między misjami.
    return [_normalize(part) for match in found if match for part in match.group(1).split(" / ")]


T = TypeVar("T")


def hide_groups(things: Iterable[T], groups: dict[str, Callable[[T], bool]], shown: set[str]) -> list[T]:
    """Usuwa rzeczy z ukrytych grup. Rzecz w kilku grupach zostaje tylko, gdy wszystkie są pokazane."""
    hidden = [test for name, test in groups.items() if name not in shown]
    return [thing for thing in things if not any(test(thing) for test in hidden)]
