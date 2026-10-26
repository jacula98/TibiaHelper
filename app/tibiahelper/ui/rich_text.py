"""Tekst kroku jako HTML z pinezkami i obrazkami potworów. Bez Qt, żeby łatwo testować.

Tekst z pliku danych zawsze przechodzi przez html.escape, więc nie da się
nim wstrzyknąć własnego HTML. Jedyne znaczniki to te, które dodajemy tu sami.
"""

from collections.abc import Callable
from html import escape

from ..core.models import Monster, Step
from ..core.monsters import describe

PIN_LINK_PREFIX = "pin:"
MONSTER_LINK_PREFIX = "mon:"


def pin_link(index: int) -> str:
    return f"{PIN_LINK_PREFIX}{index}"


def monster_link(index: int) -> str:
    return f"{MONSTER_LINK_PREFIX}{index}"


def _parse_link(link: str, prefix: str) -> int | None:
    if not link.startswith(prefix):
        return None
    number = link.removeprefix(prefix)
    return int(number) if number.isdigit() else None


def parse_pin_link(link: str) -> int | None:
    """Numer pinezki z adresu „pin:N” albo None dla innych linków."""
    return _parse_link(link, PIN_LINK_PREFIX)


def parse_monster_link(link: str) -> int | None:
    """Numer potwora w kroku z adresu „mon:N” albo None dla innych linków."""
    return _parse_link(link, MONSTER_LINK_PREFIX)


def _anchor_end(text: str, anchor: str | None) -> int:
    """Miejsce zaraz za fragmentem `anchor`; bez anchor (albo gdy go brak) koniec tekstu."""
    found = text.find(anchor) if anchor else -1
    return found + len(anchor) if found >= 0 else len(text)


def step_html(
    number: int,
    step: Step,
    pin_img: str,
    monster_img: Callable[[int], str] = lambda index: "",
) -> str:
    """„N. tekst” z pinezką za fragmentem `anchor` punktu na mapie i obrazkiem za potworem.

    pin_img to gotowy znacznik <img> (rozmiar zależy od czcionki, więc ustala go UI).
    monster_img(i) zwraca znacznik obrazka i-tego potwora kroku (UI wie, czy jest pobrany).
    """
    text = step.text
    # (miejsce w tekście, kolejność, gotowy HTML): pinezki i potwory wstawiamy jednym przejściem.
    inserts = []
    for index, marker in enumerate(step.markers):
        title = escape(marker.label, quote=True)
        html = f'&nbsp;<a href="{pin_link(index)}" title="{title}">{pin_img}</a>'
        inserts.append((_anchor_end(text, marker.anchor), len(inserts), html))
    for index, monster in enumerate(step.monsters):
        html = f'&nbsp;<a href="{monster_link(index)}">{monster_img(index)}</a>'
        inserts.append((_anchor_end(text, monster.anchor), len(inserts), html))
    inserts.sort()

    parts = [f"{number}. "]
    start = 0
    for end, _, html in inserts:
        parts.append(escape(text[start:end]))
        parts.append(html)
        start = end
    parts.append(escape(text[start:]))
    return "".join(parts)


def monster_tooltip(monster: Monster, img_tag: str = "") -> str:
    """Dymek potwora: obrazek, nazwa, HP/exp, słabości i odporności."""
    lines = "<br>".join(escape(line) for line in describe(monster))
    return (
        f'<table cellspacing="4"><tr><td>{img_tag}</td>'
        f"<td><b>{escape(monster.name)}</b><br>{lines}</td></tr></table>"
    )
