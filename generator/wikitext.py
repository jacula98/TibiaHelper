"""Proste wyciąganie danych z wikitekstu TibiaWiki.

Nie piszemy pełnego parsera MediaWiki: potrzebujemy tylko pól z
{{Infobox Quest ...}}, gdzie każde pole jest w osobnej linii "| klucz = wartość".
"""

import re

_LINK = re.compile(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]")  # [[Cel|tekst]] lub [[Cel]]
_TEMPLATE = re.compile(r"\{\{[^{}]*\}\}")
_FIELD = re.compile(r"^\|\s*([\w ]+?)\s*=\s*(.*)$")


def strip_markup(text: str) -> str:
    """Zamienia linki na sam tekst i usuwa szablony oraz pogrubienia."""
    text = _LINK.sub(r"\1", text)
    text = _TEMPLATE.sub("", text)
    text = text.replace("'''", "").replace("''", "")
    return " ".join(text.split())


def parse_infobox(wikitext: str) -> dict[str, str]:
    """Pola z {{Infobox Quest}} jako tekst bez znaczników wiki."""
    fields: dict[str, str] = {}
    inside = False
    for line in wikitext.splitlines():
        if line.lstrip().startswith("{{Infobox Quest"):
            inside = True
            continue
        if not inside:
            continue
        if line.strip() == "}}":
            break
        match = _FIELD.match(line.strip())
        if match:
            fields[match.group(1).strip().lower()] = strip_markup(match.group(2))
    return fields


# {{Mapper Coords|127.137|125.93|7|4|text=here}}: x i y jako "blok.przesunięcie", potem piętro.
_MAPPER = re.compile(r"\{\{Mapper Coords\|(\d+)\.(\d+)\|(\d+)\.(\d+)\|(\d+)[^{}]*\}\}")
BLOCK = 256  # TibiaWiki zapisuje współrzędne jako numer bloku 256 kratek i pozycję w bloku


def wiki_coord(value: str) -> int:
    """"125.151" -> 32151 (125 * 256 + 151): zamiana zapisu TibiaWiki na współrzędną z gry."""
    block, _, offset = value.strip().partition(".")
    return int(block) * BLOCK + int(offset or 0)


def mapper_coords(wikitext: str, context: int = 120) -> list[dict]:
    """Wszystkie {{Mapper Coords}} z tekstem przed nimi (żeby autor wiedział, czego dotyczą)."""
    found = []
    for match in _MAPPER.finditer(wikitext):
        bx, ox, by, oy, z = (int(g) for g in match.groups())
        before = strip_markup(wikitext[max(0, match.start() - context) : match.start()])
        found.append({"x": bx * BLOCK + ox, "y": by * BLOCK + oy, "z": z, "context": before})
    return found


def infobox_position(wikitext: str) -> dict | None:
    """Pozycja z infoboxu NPC/miejsca (pola posx, posy, posz), jeśli jest."""
    fields = {}
    for name in ("posx", "posy", "posz"):
        match = re.search(rf"^\|\s*{name}\s*=\s*([\d.]+)", wikitext, flags=re.MULTILINE)
        if match is None:
            return None
        fields[name] = match.group(1)
    return {
        "x": wiki_coord(fields["posx"]),
        "y": wiki_coord(fields["posy"]),
        "z": int(float(fields["posz"])),
    }
