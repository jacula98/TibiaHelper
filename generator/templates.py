"""Szablony MediaWiki ({{Nazwa|a|klucz=b}}) z zagnieżdżeniami.

parse_infobox w wikitext.py czyta tylko pola w jednej linii. Infobox potwora
ma pola wieloliniowe (umiejętności, loot), więc tu liczymy nawiasy {{ }} i [[ ]],
żeby dzielić tekst tylko na „|” najwyższego poziomu.
"""

from dataclasses import dataclass, field


@dataclass
class Template:
    name: str
    args: list[str] = field(default_factory=list)  # parametry bez nazwy, w kolejności
    params: dict[str, str] = field(default_factory=dict)  # parametry „klucz = wartość”


def _closing(text: str, start: int) -> int:
    """Indeks zaraz za „}}” zamykającym szablon otwarty w text[start:start+2]."""
    depth = 0
    i = start
    while i < len(text) - 1:
        pair = text[i : i + 2]
        if pair in ("{{", "[["):
            depth += 1
            i += 2
        elif pair in ("}}", "]]"):
            depth -= 1
            i += 2
            if depth == 0:
                return i
        else:
            i += 1
    return len(text)


def split_top(inner: str) -> list[str]:
    """Dzieli na „|” poza zagnieżdżonymi {{ }} i [[ ]]."""
    parts, depth, start, i = [], 0, 0, 0
    while i < len(inner):
        pair = inner[i : i + 2]
        if pair in ("{{", "[["):
            depth += 1
            i += 2
        elif pair in ("}}", "]]"):
            depth -= 1
            i += 2
        elif inner[i] == "|" and depth == 0:
            parts.append(inner[start:i])
            start = i = i + 1
        else:
            i += 1
    parts.append(inner[start:])
    return parts


def parse(text: str) -> Template:
    """„{{Nazwa|a|k=b}}” -> Template. Tekst musi być całym szablonem."""
    inner = text.strip()[2:-2]
    name, *rest = split_top(inner)
    template = Template(name.strip())
    for part in rest:
        key, sep, value = part.partition("=")
        # „=” wewnątrz zagnieżdżonego szablonu nie robi z parametru nazwanego.
        if sep and "{{" not in key and "[[" not in key:
            template.params[key.strip().lower()] = value.strip()
        else:
            template.args.append(part.strip())
    return template


def find(text: str, name: str) -> Template | None:
    """Pierwszy szablon o tej nazwie (np. "Infobox Creature") albo None."""
    start = text.find("{{" + name)
    while start >= 0:
        after = text[start + 2 + len(name) : start + 3 + len(name)]
        # „{{Infobox Creature” nie może pasować do „{{Infobox CreatureX”.
        if after in ("|", "}", "\n", " ", ""):
            return parse(text[start : _closing(text, start)])
        start = text.find("{{" + name, start + 2)
    return None


def children(value: str) -> list[Template]:
    """Szablony najwyższego poziomu w wartości, np. pozycje {{Loot Table|...}}."""
    found, i = [], 0
    while (start := value.find("{{", i)) >= 0:
        end = _closing(value, start)
        found.append(parse(value[start:end]))
        i = end
    return found
