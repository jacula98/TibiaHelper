"""Pomocnik raidów i world change (data/raids.json, dane z TibiaWiki, CC BY-SA).

Gracz wkleja wiadomości z gry (np. „10:31 Rat plague in Thais!” z Server Log).
Rozpoznajemy raid albo world change po treści komunikatu, a dla raidu liczymy
z godziny wiadomości, kiedy przyjdą kolejne fale. Czasy fal z wiki liczą się
od pierwszego komunikatu raidu.

Bez Qt, żeby łatwo testować. Wklejony tekst traktujemy tylko jako dane do porównania.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger(__name__)

# Tyle tekstu bierzemy z wklejonego pola: Server Log z całego dnia to i tak mniej.
MAX_INPUT = 20_000
# Godzina z czatu późniejsza od zegara komputera o więcej niż tyle to wiadomość z wczoraj.
FUTURE_TOLERANCE = timedelta(minutes=5)

_CLOCK = re.compile(r"^\s*(\d{1,2}):(\d{2})(?::(\d{2}))?\s+(.*)$")
_NON_WORD = re.compile(r"[^\w]+")


@dataclass(frozen=True)
class Wave:
    at: int  # sekundy od pierwszego komunikatu
    message: str  # pusty = fala bez komunikatu


@dataclass(frozen=True)
class Raid:
    id: str
    name: str
    area: str
    waves: tuple[Wave, ...]
    creatures: tuple[str, ...] = ()
    source_url: str = ""
    subarea: str = ""
    description: str = ""
    historic: bool = False


@dataclass(frozen=True)
class ChangeMessage:
    text: str
    note: str = ""


@dataclass(frozen=True)
class WorldChange:
    id: str
    name: str
    kind: str  # "world" albo "mini"
    keywords: tuple[str, ...] = ()
    messages: tuple[ChangeMessage, ...] = ()
    source_url: str = ""
    location: str = ""
    description: str = ""
    dangers: str = ""
    reward: str = ""


@dataclass(frozen=True)
class RaidData:
    raids: tuple[Raid, ...] = ()
    world_changes: tuple[WorldChange, ...] = ()


@dataclass(frozen=True)
class ChatLine:
    clock: tuple[int, int, int] | None  # (godz, min, sek) z początku linii albo None
    text: str


@dataclass(frozen=True)
class RaidMatch:
    raid: Raid
    wave: int  # indeks fali, której komunikat wkleił gracz (ostatni rozpoznany)
    started_at: datetime  # godzina pierwszego komunikatu raidu
    from_clock: bool  # False = w tekście nie było godziny, przyjęliśmy „teraz”

    def wave_time(self, index: int) -> datetime:
        return self.started_at + timedelta(seconds=self.raid.waves[index].at)


@dataclass(frozen=True)
class ChangeMatch:
    change: WorldChange
    message: ChangeMessage | None  # None = rozpoznane tylko po nazwie


@dataclass(frozen=True)
class Recognition:
    raids: list[RaidMatch] = field(default_factory=list)
    changes: list[ChangeMatch] = field(default_factory=list)


# --- wczytanie data/raids.json ---------------------------------------------------


def _text(raw: dict, key: str) -> str:
    value = raw.get(key, "")
    return value.strip() if isinstance(value, str) else ""


def _raid(raw: dict) -> Raid:
    waves = tuple(
        Wave(int(w["at"]), str(w.get("message", ""))) for w in raw["waves"] if isinstance(w.get("at"), int)
    )
    if not waves:
        raise ValueError("raid bez fal")
    return Raid(
        id=str(raw["id"]),
        name=str(raw["name"]),
        area=_text(raw, "area"),
        waves=tuple(sorted(waves, key=lambda w: w.at)),
        creatures=tuple(str(c) for c in raw.get("creatures", [])),
        source_url=_text(raw, "source_url"),
        subarea=_text(raw, "subarea"),
        description=_text(raw, "description"),
        historic=bool(raw.get("historic", False)),
    )


def _change(raw: dict) -> WorldChange:
    return WorldChange(
        id=str(raw["id"]),
        name=str(raw["name"]),
        kind="mini" if raw.get("kind") == "mini" else "world",
        keywords=tuple(str(k) for k in raw.get("keywords", []) if str(k).strip()),
        messages=tuple(ChangeMessage(str(m["text"]), str(m.get("note", ""))) for m in raw.get("messages", [])),
        source_url=_text(raw, "source_url"),
        location=_text(raw, "location"),
        description=_text(raw, "description"),
        dangers=_text(raw, "dangers"),
        reward=_text(raw, "reward"),
    )


def parse_raid_data(raw: object) -> RaidData:
    """Zawartość raids.json -> RaidData. Zły wpis pomijamy, żeby reszta działała."""
    if not isinstance(raw, dict):
        raise ValueError("Zły plik raids.json")
    raids, changes = [], []
    for parse, items, out in ((_raid, raw.get("raids", []), raids), (_change, raw.get("world_changes", []), changes)):
        for item in items if isinstance(items, list) else []:
            try:
                out.append(parse(item))
            except (KeyError, TypeError, ValueError) as exc:
                log.warning("Pominięto wpis w raids.json: %s", exc)
    return RaidData(tuple(raids), tuple(changes))


def load_raid_data(path: Path) -> RaidData:
    """Brak albo uszkodzony plik = puste dane (narzędzie pokaże, że nic nie rozpoznało)."""
    try:
        return parse_raid_data(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        log.warning("Nie wczytano %s: %s", path, exc)
        return RaidData()


# --- rozpoznawanie wklejonego tekstu ----------------------------------------------


def normalize(text: str) -> str:
    """Małe litery, bez znaków przestankowych: „Rat plague in Thais!” == „rat plague in thais”."""
    return " ".join(_NON_WORD.sub(" ", text.lower()).split())


def split_lines(text: str) -> list[ChatLine]:
    """Linie czatu z godziną na początku („10:31 …” albo „10:31:05 …”)."""
    lines = []
    # Końcówka tekstu: w Server Log najnowsze wiadomości są na dole.
    for line in text[-MAX_INPUT:].splitlines():
        if not line.strip():
            continue
        match = _CLOCK.match(line)
        if match:
            hour, minute, second = int(match.group(1)), int(match.group(2)), int(match.group(3) or 0)
            if hour < 24 and minute < 60 and second < 60:
                lines.append(ChatLine((hour, minute, second), match.group(4).strip()))
                continue
        lines.append(ChatLine(None, line.strip()))
    return lines


def _same_message(line: str, message: str) -> bool:
    """Linia to ten komunikat. Dopuszczamy dopiski przed i po (np. nick albo „[Server]”)."""
    return bool(message) and (line == message or f" {message} " in f" {line} ")


def line_time(clock: tuple[int, int, int], now: datetime) -> datetime:
    """Godzina z czatu jako data: dziś, a jeśli wychodzi „w przyszłości”, to wczoraj."""
    hour, minute, second = clock
    moment = now.replace(hour=hour, minute=minute, second=second, microsecond=0)
    return moment - timedelta(days=1) if moment > now + FUTURE_TOLERANCE else moment


def _match_raid(raid: Raid, lines: list[ChatLine], texts: list[str], now: datetime) -> RaidMatch | None:
    messages = [normalize(w.message) for w in raid.waves]
    wave, last_line = -1, None
    for line, text in zip(lines, texts, strict=True):
        # Kolejna linia to późniejsza fala: tak rozróżniamy powtórzony komunikat (np. Rat plague po 30 min).
        later = [i for i in range(wave + 1, len(messages)) if _same_message(text, messages[i])]
        if later:
            wave, last_line = later[0], line
    if last_line is None:
        return None
    if last_line.clock is None:
        return RaidMatch(raid, wave, now - timedelta(seconds=raid.waves[wave].at), from_clock=False)
    started = line_time(last_line.clock, now) - timedelta(seconds=raid.waves[wave].at)
    return RaidMatch(raid, wave, started, from_clock=True)


def _keyword_found(text: str, keyword: str) -> bool:
    word = normalize(keyword)
    return bool(word) and f" {word} " in f" {text} "


def _match_change(change: WorldChange, texts: list[str], leftover: str) -> ChangeMatch | None:
    for message in change.messages:
        if any(_same_message(text, normalize(message.text)) for text in texts):
            return ChangeMatch(change, message)
    if any(_keyword_found(leftover, keyword) for keyword in change.keywords):
        return ChangeMatch(change, None)
    return None


def _known_messages(data: RaidData) -> list[str]:
    messages = [w.message for raid in data.raids for w in raid.waves]
    messages += [m.text for change in data.world_changes for m in change.messages]
    return [m for m in dict.fromkeys(normalize(message) for message in messages) if m]


def recognize(text: str, data: RaidData, now: datetime | None = None) -> Recognition:
    """Raidy i world change, które pasują do wklejonego tekstu."""
    now = now or datetime.now()
    lines = split_lines(text)
    if not lines:
        return Recognition()
    # Normalizujemy raz: przy wklejonym całym Server Log to setki linii.
    texts = [normalize(line.text) for line in lines]
    raids = [m for raid in data.raids if (m := _match_raid(raid, lines, texts, now))]
    # Po nazwie szukamy tylko w liniach, które nie są znanym komunikatem: „A hive infestation…”
    # to mini world change Hive Outpost, a nie world change Hive Born.
    known = _known_messages(data)
    leftover = " ".join(t for t in texts if not any(_same_message(t, m) for m in known))
    changes = [m for change in data.world_changes if (m := _match_change(change, texts, leftover))]
    # Najpierw raidy z najświeższą wklejoną wiadomością.
    raids.sort(key=lambda m: m.wave_time(m.wave), reverse=True)
    # Dokładny komunikat przed dopasowaniem po samej nazwie.
    changes.sort(key=lambda m: m.message is None)
    return Recognition(raids, changes)


def next_wave(match: RaidMatch, now: datetime) -> int | None:
    """Indeks najbliższej fali, która jeszcze nie przyszła, albo None (wszystkie już były)."""
    for index in range(len(match.raid.waves)):
        if match.wave_time(index) > now:
            return index
    return None


def format_countdown(seconds: float) -> str:
    """Odliczanie: „4:05” (min:sek) albo „1:02:03” (godz:min:sek)."""
    seconds = max(0, int(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"
