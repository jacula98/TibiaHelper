"""Raidy i world change z TibiaWiki do data/raids.json (pomocnik raidów w zakładce Narzędzia).

Raidy: strony „<Miasto> Raids” mają sekcje z {{Raid Message|czas|komunikat|czas|komunikat…}}.
Czas liczy się od pierwszego komunikatu. Pusty komunikat = fala bez ogłoszenia.

World change: komunikaty Towncryera (NPC w Thais), tablicy The World Board i ze spoilerów
world change. Do tego pola z {{Infobox Quest}} strony (gdzie, opis, potwory, nagroda).
"""

import json
import re
from pathlib import Path

from tibiahelper.core.storage import write_json_atomic

from . import templates
from .quests import slugify, source_url
from .wiki_api import WikiPage
from .wikitext import strip_markup

DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "raids.json"
RAID_PAGE = "Raid"  # ogólna strona: z niej bierzemy tylko „Global Raids”
TOWNCRYER = "Towncryer"
WORLD_BOARD = "The World Board"
MAX_TEXT = 400

_HEADING = re.compile(r"^(=+)\s*(.*?)\s*\1\s*$", re.MULTILINE)
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_TAG = re.compile(r"<[^>]+>")  # np. <br />: strip_markup usuwa tylko znaczniki wiki
_PARENS = re.compile(r"\s*\([^)]*\)")
_TIME = re.compile(r"^\d{1,2}:[\d?]{2}(:[\d?]{2})?$")
_SUBAREA = re.compile(r"^Subarea:\s*(.+)$", re.MULTILINE)
# {{Message|type=chat|tekst}} i {{Server Message|tekst}}: tekst jest ostatnim parametrem.
_MESSAGE = re.compile(r"\{\{(?:Server )?Message\|(?:type=\w+\|)?([^{}]*)\}\}")
_WC_LINK = re.compile(r"\[\[([^\]|]*World Change)(?:\|[^\]]*)?\]\]")
# Słowa, o które pyta się Guide NPC (strona „World Changes”) -> strona world change.
GUIDE_KEYWORDS = {
    "Horestis": "The Mummy's Curse World Change",
    "Mage Tower": "The Mage's Tower World Change",
    "Master's Voice": "Their Master's Voice World Change",
    "Horses": "Horse Station World Change",
    "Demon War": "Demon Wars World Change",
    "Sea Serpent": "The Fire-Feathered Serpent World Change",
    "Deepling": "Deeplings World Change",
    "Hive": "Hive Born World Change",
}


def parse_time(value: str) -> int | None:
    """Czas z wiki -> sekundy od pierwszego komunikatu. None = nieznany („00:??”).

    Trzy części to gg:mm:ss. Przy dwóch wiki pisze różnie: „00:04” to 4 minuty (strony miast),
    a „10:00” to 10 minut (Vandura Raids). Dlatego „00:mm” czytamy jako minuty, a resztę jako mm:ss.
    """
    value = value.strip()
    if not _TIME.match(value) or "?" in value:
        return None
    parts = [int(p) for p in value.split(":")]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    first, second = parts
    return second * 60 if first == 0 else first * 60 + second


def _text(value: str) -> str:
    return strip_markup(_TAG.sub(" ", value))


def _clip(text: str, limit: int = MAX_TEXT) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _waves(template: templates.Template) -> list[dict]:
    """Pary (czas, komunikat) z {{Raid Message}}. Fale z nieznanym czasem pomijamy."""
    args = list(template.args)
    waves = []
    for index in range(0, len(args), 2):
        at = parse_time(args[index])
        if at is None:
            continue
        message = strip_markup(args[index + 1]) if index + 1 < len(args) else ""
        waves.append({"at": at, "message": _clip(message)})
    return sorted(waves, key=lambda w: w["at"])


def _description(section: str) -> str:
    """Pierwszy akapit opisu sekcji (bez szablonów, „Subarea:” i „Events:”)."""
    lines = []
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("{{", "|", "}}", "<", "Subarea:", "Events:", "Note:")):
            if lines:
                break
            continue
        lines.append(stripped)
    return _clip(strip_markup(" ".join(lines)))


def _creatures(section: str) -> list[str]:
    found = templates.find(section, "CreatureList")
    if found is None:
        return []
    names = [strip_markup(arg) for arg in found.args]
    return list(dict.fromkeys(n for n in names if n))


def _sections(wikitext: str) -> list[tuple[str, str, str]]:
    """(nagłówek 2. poziomu, nazwa sekcji, treść) dla każdej sekcji z {{Raid Message}}."""
    headings = list(_HEADING.finditer(wikitext))
    found, group = [], ""
    for index, match in enumerate(headings):
        level, title = len(match.group(1)), strip_markup(match.group(2))
        end = headings[index + 1].start() if index + 1 < len(headings) else len(wikitext)
        body = wikitext[match.end() : end]
        if level == 2:
            group = title
        if "{{Raid Message" in body:
            found.append((group, title, body))
    return found


def build_raids(pages: dict[str, WikiPage]) -> list[dict]:
    """Raidy z komunikatem (tylko takie da się rozpoznać po wklejonym tekście)."""
    raids: list[dict] = []
    taken: set[str] = set()
    # Ten sam raid bywa na dwóch stronach (np. „Darashia Raids” i „Northern Darama Raids”).
    # Zostawiamy pierwszy (strony idą alfabetycznie, więc zwykle strona miasta).
    seen: set[tuple] = set()
    for title, page in sorted(pages.items()):
        text = _COMMENT.sub("", page.wikitext)
        area = title.removesuffix(" Raids").removesuffix("/Raids")
        for group, name, body in _sections(text):
            if title == RAID_PAGE and "global" not in group.lower():
                continue
            start = body.find("{{Raid Message")
            waves = _waves(templates.parse(body[start : templates._closing(body, start)]))
            if not any(w["message"] for w in waves):
                continue  # raid bez ogłoszenia: gracz nie ma czego wkleić
            if "deprecated" in name.lower() or name.startswith("Passed"):
                continue  # raidy, których już nie ma w grze
            signature = (name, tuple(w["message"] for w in waves))
            if signature in seen:
                continue
            seen.add(signature)
            raid_id = slugify(name)
            if raid_id in taken:
                raid_id = slugify(f"{area} {name}")
            taken.add(raid_id)
            subarea = _SUBAREA.search(body)
            raid = {
                "id": raid_id,
                "name": name.removeprefix("Historic: "),
                "area": "Global" if title == RAID_PAGE else area,
                "waves": waves,
                "creatures": _creatures(body),
                "source_url": source_url(title),
            }
            if subarea:
                # Bez dopisków w nawiasie, np. „(not announced)”.
                raid["subarea"] = _PARENS.sub("", strip_markup(subarea.group(1))).strip()
            if description := _description(body):
                raid["description"] = description
            if "historic" in group.lower() or name.startswith("Historic"):
                raid["historic"] = True
            raids.append(raid)
    return raids


def _towncryer_messages(wikitext: str) -> list[tuple[str, str, str]]:
    """(strona world change, komunikat, uwaga) z tabeli na stronie Towncryera."""
    found = []
    for row in wikitext.split("|-"):
        link = _WC_LINK.search(row)
        if link is None:
            continue
        for match in _MESSAGE.finditer(row):
            # Uwaga w nawiasie za komunikatem, np. „(when Dworcs dominate)”.
            after = row[match.end() :].split("{{", 1)[0].split("\n|", 1)[0]
            note = _text(after).strip(" ()")
            found.append((link.group(1), strip_markup(match.group(1)), note))
    return found


def _world_board_messages(wikitext: str) -> list[tuple[str, str, str]]:
    """(strona, komunikat, uwaga) z listy „* {{Server Message|…}} — [[X]] is active…”."""
    found = []
    for line in wikitext.splitlines():
        message, link = _MESSAGE.search(line), _WC_LINK.search(line)
        if not line.startswith("*") or message is None or link is None:
            continue
        rest = _text(line[link.end() :]).removeprefix("is active").strip(" .")
        note = rest.removeprefix("and ").removeprefix("at ")
        found.append((link.group(1), strip_markup(message.group(1)), note))
    return found


def _short_name(title: str) -> str:
    return title.removesuffix(" Mini World Change").removesuffix(" World Change")


def build_world_changes(pages: dict[str, WikiPage], mini: set[str]) -> list[dict]:
    """World change i mini world change. pages: strony world change, Towncryer, The World Board, spoilery."""
    messages: dict[str, list[dict]] = {}

    def add(title: str, text: str, note: str = "") -> None:
        known = messages.setdefault(title, [])
        if text and all(m["text"] != text for m in known):
            known.append({"text": _clip(text), **({"note": _clip(note, 120)} if note else {})})

    for source, parse in ((TOWNCRYER, _towncryer_messages), (WORLD_BOARD, _world_board_messages)):
        if source in pages:
            for title, text, note in parse(pages[source].wikitext):
                add(title, text, note)
    keywords: dict[str, list[str]] = {}
    for keyword, title in GUIDE_KEYWORDS.items():
        keywords.setdefault(title, []).append(keyword)

    changes = []
    for title in sorted(t for t in pages if t.endswith("World Change")):
        # templates.find zamiast parse_infobox: pola bywają wieloliniowe („Either:<br />* …”).
        infobox = templates.find(pages[title].wikitext, "Infobox Quest")
        info = infobox.params if infobox else {}
        spoiler = pages.get(title + "/Spoiler")
        if spoiler is not None:
            for match in re.finditer(r"\{\{(?:Server Message|Message\|type=server)\|([^{}]*)\}\}", spoiler.wikitext):
                add(title, strip_markup(match.group(1)))
        short = _short_name(title)
        change = {
            "id": slugify(title),
            "name": short,
            "kind": "mini" if title in mini else "world",
            "keywords": [short.removeprefix("The "), *keywords.get(title, [])],
            "messages": messages.get(title, []),
            "source_url": source_url(title),
        }
        for field, key in (("location", "location"), ("description", "legend"), ("dangers", "dangers"),
                           ("reward", "reward")):
            value = re.sub(r"\s*\*\s*", " ", _text(info.get(key, ""))).strip(" .:,")
            if value and value.lower() not in ("none", "unknown", "?"):
                change[field] = _clip(value)
        changes.append(change)
    return changes


def save(raids: list[dict], world_changes: list[dict], path: Path = DATA_FILE) -> None:
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    data = {"data_version": old.get("data_version", 0) + 1, "raids": raids, "world_changes": world_changes}
    write_json_atomic(path, data)
