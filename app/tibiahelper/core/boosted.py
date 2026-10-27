"""Dzisiejszy boosted potwór i boosted boss z TibiaWiki. Bez Qt, żeby łatwo testować.

Wiki trzyma ich nazwy w dwóch szablonach, które redaktorzy zmieniają codziennie
po server save. Jedno zapytanie do API zwraca oba naraz.

Wynik zapisujemy w %APPDATA%/TibiaHelper/boosted.json z „dniem Tibii”, więc
w ciągu dnia program pyta wiki najwyżej raz (plus ponowne próby, dopóki wiki
nie pokaże nowego dnia).
"""

import http.client
import json
import logging
import re
import urllib.parse
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from .storage import write_json_atomic
from .updater import Fetch, download

log = logging.getLogger(__name__)

CREATURE_PAGE = "Template:Boosted Creature"
BOSS_PAGE = "Template:Boosted Boss"
API_URL = "https://tibia.fandom.com/api.php?" + urllib.parse.urlencode(
    {
        "action": "query",
        "prop": "revisions",
        "rvprop": "content|timestamp",
        "rvslots": "main",
        "format": "json",
        "titles": f"{CREATURE_PAGE}|{BOSS_PAGE}",
    }
)
# Server save jest o 10:00 czasu niemieckiego: 8:00 UTC latem, 9:00 UTC zimą.
# Wcześniej niż o tej godzinie nadal trwa „wczorajszy” dzień Tibii.
# Nazwa z wiki trafia do okna, więc wpuszczamy tylko zwykłe znaki nazw potworów.
_NAME = re.compile(r"^[A-Za-z0-9 '.,()-]{1,60}$")


@dataclass(frozen=True)
class Boosted:
    day: str  # dzień Tibii, którego dotyczą dane, np. "2026-10-27"
    creature: str | None
    boss: str | None


def _last_sunday(year: int, month: int) -> date:
    day = date(year, month, 31)  # marzec i październik mają po 31 dni
    return day - timedelta(days=(day.weekday() + 1) % 7)


def _summer_time(moment: datetime) -> bool:
    """Czas letni w UE: od ostatniej niedzieli marca do ostatniej niedzieli października, o 1:00 UTC.

    Liczymy sami, bo strefy czasowe (zoneinfo) na Windows wymagają dodatkowego pakietu tzdata.
    """
    start = datetime.combine(_last_sunday(moment.year, 3), time(1), timezone.utc)
    end = datetime.combine(_last_sunday(moment.year, 10), time(1), timezone.utc)
    return start <= moment < end


def tibia_day(moment: datetime) -> date:
    """Dzień Tibii: zmienia się przy server save, a nie o północy."""
    moment = moment.astimezone(timezone.utc)
    server_save = timedelta(hours=8 if _summer_time(moment) else 9)
    return (moment - server_save).date()


def _clean_name(text: object) -> str | None:
    if not isinstance(text, str):
        return None
    name = text.strip()
    return name if _NAME.match(name) else None


def parse_response(data: bytes) -> Boosted:
    """Odpowiedź API -> Boosted. Dzień liczymy z daty ostatniej zmiany szablonów na wiki.

    Rzuca ValueError, gdy odpowiedź ma zły format.
    """
    try:
        pages = json.loads(data.decode("utf-8"))["query"]["pages"].values()
    except (UnicodeDecodeError, KeyError, TypeError, AttributeError) as exc:
        raise ValueError(f"Zła odpowiedź z wiki: {exc}") from exc
    names: dict[str, str | None] = {}
    days: list[date] = []
    for page in pages:
        try:
            revision = page["revisions"][0]
            names[page["title"]] = _clean_name(revision["slots"]["main"]["*"])
            days.append(tibia_day(datetime.fromisoformat(revision["timestamp"].replace("Z", "+00:00"))))
        except (KeyError, IndexError, TypeError, AttributeError, ValueError):
            continue  # brak strony albo dziwny wpis: pomijamy tylko ten szablon
    if not days:
        raise ValueError("Wiki nie zwróciła szablonów boosted")
    # Starsza z dwóch dat: jeśli redaktor zmienił dopiero jeden szablon, drugi jest jeszcze wczorajszy.
    return Boosted(min(days).isoformat(), names.get(CREATURE_PAGE), names.get(BOSS_PAGE))


def load_cache(path: Path) -> Boosted | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return Boosted(str(raw["day"]), _clean_name(raw.get("creature")), _clean_name(raw.get("boss")))
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


def is_current(boosted: Boosted | None, now: datetime) -> bool:
    return boosted is not None and boosted.day == tibia_day(now).isoformat()


def get_boosted(cache: Path, now: datetime, fetch: Fetch = download) -> Boosted | None:
    """Dzisiejszy boosted z pliku albo z wiki. Bez sieci: ostatni znany wynik (albo None).

    Wynik może być z poprzedniego dnia (brak sieci albo wiki jeszcze nie zmieniona):
    sprawdź is_current, zanim pokażesz go jako dzisiejszy.

    Wołaj w wątku w tle: zapytanie do wiki może trwać kilka sekund.
    """
    cached = load_cache(cache)
    if is_current(cached, now):
        return cached
    try:
        fresh = parse_response(fetch(API_URL))
    except (OSError, http.client.HTTPException, ValueError) as exc:
        log.info("Pobieranie boosted pominięte: %s", exc)
        return cached
    try:
        write_json_atomic(cache, asdict(fresh))
    except OSError as exc:
        log.info("Nie udało się zapisać %s: %s", cache, exc)
    return fresh
