"""Timery bossów: „zabity” i okno, w którym boss może się znowu pojawić. Bez Qt, żeby łatwo testować.

Plik JSON w %APPDATA%/TibiaHelper/boss_timers.json:
    {"version": 1, "timers": {"tyrn": {"killed_at": "2026-10-29T12:00:00+00:00",
                                       "min_days": 3, "max_days": 7, "notified": false}}}
"notified" = powiadomienie „boss może się zaraz pojawić” już było (żeby nie wyskakiwało znowu).
"""

import json
import logging
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path

from .boss_watch import MAX_RESPAWN_DAYS
from .storage import write_json_atomic

log = logging.getLogger(__name__)

TIMERS_VERSION = 1
# Tyle przed początkiem okna respawnu przychodzi powiadomienie.
WARN_BEFORE = timedelta(hours=1)


@dataclass(frozen=True)
class BossTimer:
    killed_at: datetime  # zawsze ze strefą czasową (UTC)
    min_days: int
    max_days: int
    notified: bool = False

    @property
    def window_start(self) -> datetime:
        return self.killed_at + timedelta(days=self.min_days)

    @property
    def window_end(self) -> datetime:
        return self.killed_at + timedelta(days=self.max_days)


def make_timer(killed_at: datetime, min_days: int, max_days: int) -> BossTimer:
    """Nowy timer. Okno poprawiamy, zamiast rzucać błędem (np. „od 7 do 3” -> 3–7)."""
    low, high = sorted((min_days, max_days))
    low = min(max(low, 1), MAX_RESPAWN_DAYS)
    high = min(max(high, low), MAX_RESPAWN_DAYS)
    return BossTimer(killed_at, low, high)


def load_timers(path: Path) -> dict[str, BossTimer]:
    """Timery z pliku. Brak albo zły plik = brak timerów; zły wpis pomijamy."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))["timers"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        if path.exists():
            log.warning("Nie można odczytać timerów z %s: %s", path, exc)
        return {}
    timers: dict[str, BossTimer] = {}
    for monster_id, entry in raw.items() if isinstance(raw, dict) else []:
        try:
            killed_at = datetime.fromisoformat(entry["killed_at"])
            if killed_at.tzinfo is None:
                continue
            timer = make_timer(killed_at, int(entry["min_days"]), int(entry["max_days"]))
            timers[str(monster_id)] = replace(timer, notified=bool(entry.get("notified", False)))
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
    return timers


def save_timers(path: Path, timers: dict[str, BossTimer]) -> None:
    data = {
        "version": TIMERS_VERSION,
        "timers": {
            monster_id: {
                "killed_at": t.killed_at.isoformat(timespec="seconds"),
                "min_days": t.min_days,
                "max_days": t.max_days,
                "notified": t.notified,
            }
            for monster_id, t in timers.items()
        },
    }
    try:
        write_json_atomic(path, data)
    except OSError as exc:
        log.error("Nie można zapisać timerów do %s: %s", path, exc)


def due_warnings(timers: dict[str, BossTimer], now: datetime) -> list[str]:
    """Bossy, o których trzeba teraz przypomnieć: okno respawnu zaczyna się za mniej niż godzinę
    (albo już trwa, np. gdy komputer był wyłączony), a powiadomienia jeszcze nie było.
    """
    return [
        monster_id
        for monster_id, t in timers.items()
        if not t.notified and t.window_start - WARN_BEFORE <= now < t.window_end
    ]


def format_left(delta: timedelta) -> str:
    """Ile zostało, krótko: „2 d 5 h”, „3 h 20 min”, „15 min”. Bez tłumaczenia: same skróty."""
    minutes = max(0, int(delta.total_seconds() // 60))
    days, rest = divmod(minutes, 24 * 60)
    hours, minutes = divmod(rest, 60)
    if days:
        return f"{days} d {hours} h"
    if hours:
        return f"{hours} h {minutes} min"
    return f"{minutes} min"
