"""Sprawdzanie, czy na GitHubie jest nowsza wersja programu (Release z plikiem .exe).

Aktualizacja danych (updater.py) pobiera tylko poradniki. Nowy kod, np. nowa
zakładka, przychodzi w nowym .exe, który autor wrzuca jako Release na GitHubie.
Program niczego sam nie instaluje: pokazuje tylko pasek z przyciskiem „Pobierz”,
który otwiera stronę Release w przeglądarce.
"""

import http.client
import json
import logging
import re
from dataclasses import dataclass

from .updater import Fetch, download

log = logging.getLogger(__name__)

# API GitHuba bez logowania: 60 zapytań na godzinę z jednego IP, a pytamy raz przy starcie.
LATEST_URL = "https://api.github.com/repos/jacula98/TibiaHelper/releases/latest"
RELEASES_PAGE = "https://github.com/jacula98/TibiaHelper/releases/"
_VERSION = re.compile(r"^v?(\d+)\.(\d+)(?:\.(\d+))?$")


@dataclass(frozen=True)
class Release:
    version: str  # np. "1.2.0", bez „v”
    url: str  # strona Release na GitHubie


def parse_version(text: str) -> tuple[int, int, int] | None:
    """„v1.2.3” albo „1.2” -> (1, 2, 3) / (1, 2, 0). Inny format -> None."""
    match = _VERSION.match(text.strip())
    if match is None:
        return None
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch or 0)


def check_for_release(current: str, fetch: Fetch = download) -> Release | None:
    """Najnowszy Release, jeśli jest nowszy od current. Każdy problem (brak sieci, brak Release) -> None."""
    try:
        raw = json.loads(fetch(LATEST_URL).decode("utf-8"))
        tag = str(raw["tag_name"])
        url = str(raw.get("html_url", ""))
    except (OSError, http.client.HTTPException, ValueError, KeyError, TypeError) as exc:
        # 404 (HTTPError to OSError) = jeszcze żadnego Release; to nie jest błąd.
        log.info("Sprawdzanie nowej wersji programu pominięte: %s", exc)
        return None
    latest, mine = parse_version(tag), parse_version(current)
    if latest is None or mine is None or latest <= mine:
        return None
    # Link otwieramy w przeglądarce, więc tylko do Release tego repo, nigdy gdzie indziej.
    if not url.startswith(RELEASES_PAGE):
        url = RELEASES_PAGE + "latest"
    return Release(".".join(map(str, latest)), url)
