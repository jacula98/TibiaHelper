"""Materiał do szkicu questa ze strony /Spoiler na TibiaWiki.

To NIE jest gotowy poradnik: tekst jest po angielsku i dosłownie z wiki.
Daje autorowi treść do uproszczenia w trybie autora, zamiast pustego szkicu.
Pierwszy krok ma „TODO”, więc szkicu nie da się oznaczyć jako przejrzany,
dopóki autor go nie przerobi.
"""

import re

from tibiahelper.core.models import MAP_X_MAX, MAP_X_MIN, MAP_Y_MAX, MAP_Y_MIN

from .terminology import apply_terms
from .wikitext import BLOCK

TODO_STEP = "TODO: przetłumacz i uprość kroki poniżej (tekst z TibiaWiki, po angielsku)"
MAX_STEPS = 40
MAX_STEP_CHARS = 600
MAX_ITEM_CHARS = 120

# Szablony, z których zostawiamy tekst (np. {{KW|mead}} -> mead, {{Sound|...}} -> "...").
_KEEP = re.compile(r"\{\{(?:KW|Ilink|ilink|Sound|sound|Server Message|Message|Item Obtained)\|([^{}|]*)[^{}]*\}\}")
_FILE = re.compile(r"\[\[(?:File|Image):[^\[\]]*(?:\[\[[^\]]*\]\][^\[\]]*)*\]\]", re.IGNORECASE)
_LINK = re.compile(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]")
_HEADING = re.compile(r"^(=+)\s*(.*?)\s*\1\s*$")
_REF = re.compile(r"<ref[^>]*>.*?</ref>|<[^>]+>", re.DOTALL)
REQUIRED_HEADINGS = ("required equipment", "requirements", "required items")


def _strip_templates(text: str) -> str:
    # Zagnieżdżone szablony usuwamy od środka, aż nic nie zostanie.
    previous = None
    while previous != text:
        previous = text
        text = re.sub(r"\{\{[^{}]*\}\}", "", text)
    return text


def clean(text: str) -> str:
    """Wikitekst -> zwykły tekst w jednej linii."""
    text = _FILE.sub("", text)
    text = _KEEP.sub(lambda m: m.group(1), text)
    text = _strip_templates(text)
    text = _LINK.sub(r"\1", text)
    text = _REF.sub("", text)
    text = text.replace("'''", "").replace("''", "")
    text = re.sub(r"^[*#:;]+\s*", "", text.strip())
    return apply_terms(" ".join(text.split()))


def _shorten(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + " …"


# {{Mapper Coords|125.252|121.75|5|3|text=here}}: zamieniamy na znacznik @@x,y,z@@ + tekst linku,
# zanim usuniemy resztę szablonów (także wieloliniowych, np. rozmowy z NPC).
_MAPPER = re.compile(r"\{\{Mapper Coords\|([^{}]*)\}\}")
_COORD = re.compile(r"^(\d+)\.(\d+)$")
_TOKEN = re.compile(r"@@(\d+),(\d+),(\d+)@@")


def _mapper_token(match: re.Match) -> str:
    parts = match.group(1).split("|")
    text = next((p.split("=", 1)[1] for p in parts if p.startswith("text=")), "")
    numbers = [p for p in parts if "=" not in p]
    if len(numbers) >= 3 and _COORD.match(numbers[0]) and _COORD.match(numbers[1]) and numbers[2].isdigit():
        bx, ox = (int(v) for v in numbers[0].split("."))
        by, oy = (int(v) for v in numbers[1].split("."))
        return f"@@{bx * BLOCK + ox},{by * BLOCK + oy},{int(numbers[2])}@@{text}"
    return text


def _markers(line: str, label: str) -> tuple[str, list[dict]]:
    """Wyjmuje znaczniki współrzędnych z linii -> pinezki (bez anchor: stoją na końcu kroku)."""
    found = []
    for x, y, z in ((int(v) for v in m.groups()) for m in _TOKEN.finditer(line)):
        if MAP_X_MIN <= x <= MAP_X_MAX and MAP_Y_MIN <= y <= MAP_Y_MAX and 0 <= z <= 15:
            found.append({"x": x, "y": y, "z": z, "label": label, "kind": "place"})
    return _TOKEN.sub("", line), found[:5]


def draft_content(wikitext: str, quest_name: str) -> tuple[list[dict], list[str]]:
    """(kroki, potrzebne przedmioty) ze strony /Spoiler."""
    steps: list[dict] = [{"text": TODO_STEP}]
    required: list[str] = []
    heading = ""
    pending_heading = ""
    text_only = _MAPPER.sub(_mapper_token, wikitext)
    text_only = _strip_templates(_KEEP.sub(lambda m: m.group(1), text_only))
    for line in text_only.splitlines():
        line, markers = _markers(line.strip(), quest_name)
        match = _HEADING.match(line)
        if match:
            heading = clean(match.group(2))
            pending_heading = heading
            continue
        text = clean(line)
        if len(text) < 3:
            continue
        if heading.lower() in REQUIRED_HEADINGS:
            required.append(_shorten(text, MAX_ITEM_CHARS))
            continue
        if len(steps) >= MAX_STEPS:
            continue
        # Nagłówek sekcji (np. „Mission 2: …”) trafia na początek jej pierwszego kroku.
        if pending_heading:
            text = f"[{pending_heading}] {text}"
            pending_heading = ""
        step: dict = {"text": _shorten(text, MAX_STEP_CHARS)}
        if markers:
            step["markers"] = markers
        steps.append(step)
    return steps, required
