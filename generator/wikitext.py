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
