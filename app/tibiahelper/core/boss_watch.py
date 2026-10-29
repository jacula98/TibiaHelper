"""Bossy na serwerze: czy wczoraj zabijały graczy albo zostały zabite. Bez Qt, żeby łatwo testować.

Źródło: statystyki zabójstw („Kill Statistics”) z tibia.com, przez darmowe TibiaData API
(bez klucza, kod na MIT). Statystyki zmieniają się raz na dobę, ok. 3:00 czasu niemieckiego,
więc każdy program pyta najwyżej raz na „dzień statystyk” (wynik w boss_watch.json).
Tak jak boosted: każdy program pyta sam, bez serwera autora.

Bossy do sprawdzania są w data/boss_spawns.json: tylko te, które pojawiają się na świecie
(raidy, rzadkie spawny). Bossy z questów i instancji giną codziennie, więc tylko by spamowały.
"""

import http.client
import json
import logging
import re
import urllib.parse
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .boosted import _summer_time
from .storage import write_json_atomic
from .updater import Fetch, download

log = logging.getLogger(__name__)

KILLSTATS_URL = "https://api.tibiadata.com/v4/killstatistics/{world}"
# Nazwy światów to same litery (np. „Antica”, „Bona”). Nic innego nie trafia do adresu.
_WORLD = re.compile(r"^[A-Za-z]{3,30}$")
MAX_ENTRIES = 5000  # na świecie jest ok. 1500 ras; więcej to zła odpowiedź
MAX_RESPAWN_DAYS = 400


@dataclass(frozen=True)
class WatchedBoss:
    """Boss ze spawnem na świecie. respawn_days: okno respawnu w dniach (od, do) albo None."""

    monster: str
    respawn_days: tuple[int, int] | None = None


@dataclass(frozen=True)
class Sighting:
    """Boss ze statystyk ostatniej doby: ilu graczy zabił i ile razy go zabito."""

    monster: str
    name: str
    players_killed: int
    killed: int


@dataclass(frozen=True)
class WatchResult:
    world: str
    day: str  # dzień statystyk, np. "2026-10-29"
    sightings: list[Sighting] = field(default_factory=list)


def clean_world(text: object) -> str | None:
    """Nazwa świata z ustawień, z wielkiej litery („antica” -> „Antica”), albo None."""
    if not isinstance(text, str):
        return None
    world = text.strip()
    return world.capitalize() if _WORLD.match(world) else None


def stats_day(moment: datetime) -> date:
    """Dzień statystyk. Tibia liczy je ok. 3:00 czasu niemieckiego; bierzemy 4:00, z zapasem.

    4:00 w Niemczech to 2:00 UTC latem i 3:00 UTC zimą.
    """
    moment = moment.astimezone(timezone.utc)
    return (moment - timedelta(hours=2 if _summer_time(moment) else 3)).date()


def load_watched(path: Path) -> dict[str, WatchedBoss]:
    """data/boss_spawns.json -> {id potwora: WatchedBoss}. Brak albo zły plik = pusta lista."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        entries = raw["bosses"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        log.info("Brak listy bossów do sprawdzania (%s): %s", path, exc)
        return {}
    watched: dict[str, WatchedBoss] = {}
    for entry in entries if isinstance(entries, list) else []:
        try:
            boss = WatchedBoss(str(entry["monster"]), _respawn(entry.get("respawn_days")))
        except (KeyError, TypeError, AttributeError, ValueError):
            continue  # zły wpis pomijamy, reszta działa
        watched[boss.monster] = boss
    return watched


def load_worlds(path: Path) -> list[str]:
    """Światy do listy w ustawieniach (z data/boss_spawns.json). Zły wpis pomijamy."""
    try:
        worlds = json.loads(path.read_text(encoding="utf-8"))["worlds"]
    except (OSError, ValueError, KeyError, TypeError):
        return []
    return sorted({w for w in map(clean_world, worlds if isinstance(worlds, list) else []) if w})


def _respawn(value: object) -> tuple[int, int] | None:
    if value is None:
        return None
    low, high = value  # type: ignore[misc]
    if not (isinstance(low, int) and isinstance(high, int) and 0 < low <= high <= MAX_RESPAWN_DAYS):
        raise ValueError(f"złe okno respawnu: {value!r}")
    return low, high


def parse_killstats(data: bytes) -> dict[str, tuple[int, int]]:
    """Odpowiedź TibiaData -> {nazwa rasy małymi literami: (zabici gracze, zabite potwory)} z ostatniej doby.

    Rzuca ValueError, gdy odpowiedź ma zły format.
    """
    try:
        entries = json.loads(data.decode("utf-8"))["killstatistics"]["entries"]
    except (UnicodeDecodeError, KeyError, TypeError) as exc:
        raise ValueError(f"Zła odpowiedź z TibiaData: {exc}") from exc
    if not isinstance(entries, list) or len(entries) > MAX_ENTRIES:
        raise ValueError("Zła lista statystyk z TibiaData")
    stats: dict[str, tuple[int, int]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("race"), str):
            continue
        players, killed = entry.get("last_day_players_killed"), entry.get("last_day_killed")
        if isinstance(players, int) and isinstance(killed, int) and players >= 0 and killed >= 0:
            stats[entry["race"].strip().lower()] = (players, killed)
    return stats


def find_sightings(stats: dict[str, tuple[int, int]], names: dict[str, str]) -> list[Sighting]:
    """Bossy, które wczoraj kogoś zabiły albo zginęły. names: {id potwora: nazwa z wiki}."""
    found = []
    for monster_id, name in names.items():
        players, killed = stats.get(name.lower(), (0, 0))
        if players or killed:
            found.append(Sighting(monster_id, name, players, killed))
    return sorted(found, key=lambda s: s.name.lower())


def load_cache(path: Path) -> WatchResult | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        sightings = [
            Sighting(str(s["monster"]), str(s["name"]), int(s["players_killed"]), int(s["killed"]))
            for s in raw["sightings"]
        ]
        return WatchResult(str(raw["world"]), str(raw["day"]), sightings)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


def is_current(result: WatchResult | None, world: str, now: datetime) -> bool:
    return result is not None and result.world == world and result.day == stats_day(now).isoformat()


def check_world(
    cache: Path, world: str, names: dict[str, str], now: datetime, fetch: Fetch = download
) -> tuple[WatchResult | None, bool]:
    """Bossy ze statystyk świata. Zwraca (wynik, czy nowy).

    „Nowy” = właśnie pobrany z sieci: tylko wtedy pokazujemy powiadomienie, żeby po
    ponownym uruchomieniu programu nie wyskakiwało drugi raz. Bez sieci: (ostatni wynik, False).
    Wołaj w wątku w tle: zapytanie może trwać kilka sekund.
    """
    cached = load_cache(cache)
    if is_current(cached, world, now):
        return cached, False
    url = KILLSTATS_URL.format(world=urllib.parse.quote(world))
    try:
        stats = parse_killstats(fetch(url))
    except (OSError, http.client.HTTPException, ValueError) as exc:
        log.info("Sprawdzanie bossów pominięte: %s", exc)
        return (cached if cached is not None and cached.world == world else None), False
    result = WatchResult(world, stats_day(now).isoformat(), find_sightings(stats, names))
    try:
        write_json_atomic(cache, asdict(result))
    except OSError as exc:
        log.info("Nie udało się zapisać %s: %s", cache, exc)
    return result, True
