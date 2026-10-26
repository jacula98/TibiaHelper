"""Tekst kroku jako HTML z klikalnymi pinezkami. Bez Qt, żeby łatwo testować.

Tekst z pliku danych zawsze przechodzi przez html.escape, więc nie da się
nim wstrzyknąć własnego HTML. Jedyne znaczniki to te, które dodajemy tu sami.
"""

from html import escape

from ..core.models import Step

PIN_LINK_PREFIX = "pin:"


def pin_link(index: int) -> str:
    return f"{PIN_LINK_PREFIX}{index}"


def parse_pin_link(link: str) -> int | None:
    """Numer pinezki z adresu „pin:N” albo None dla innych linków."""
    if not link.startswith(PIN_LINK_PREFIX):
        return None
    number = link.removeprefix(PIN_LINK_PREFIX)
    return int(number) if number.isdigit() else None


def step_html(number: int, step: Step, pin_img: str) -> str:
    """„N. tekst” z pinezką za fragmentem `anchor` każdego punktu na mapie.

    pin_img to gotowy znacznik <img> (rozmiar zależy od czcionki, więc ustala go UI).
    """
    text = step.text
    # (miejsce w tekście, numer punktu); punkt bez anchor trafia na koniec tekstu.
    positions = []
    for index, marker in enumerate(step.markers):
        found = text.find(marker.anchor) if marker.anchor else -1
        end = found + len(marker.anchor) if found >= 0 else len(text)
        positions.append((end, index))
    positions.sort()

    parts = [f"{number}. "]
    start = 0
    for end, index in positions:
        parts.append(escape(text[start:end]))
        title = escape(step.markers[index].label, quote=True)
        parts.append(f'&nbsp;<a href="{pin_link(index)}" title="{title}">{pin_img}</a>')
        start = end
    parts.append(escape(text[start:]))
    return "".join(parts)
