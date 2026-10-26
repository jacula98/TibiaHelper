"""Mapy pięter Tibii z projektu tibiamaps (tibia-map-data).

Każde piętro to jeden PNG 2560 x 2048, gdzie 1 piksel = 1 kratka w grze.
Autorzy zachęcają do używania tych plików („Feel free to use”), a kod
projektu jest na licencji MIT. Pobieramy piętro przy pierwszym użyciu
i trzymamy w %APPDATA%/TibiaHelper/maps, więc później działa bez internetu.
"""

import logging
import urllib.request
from collections.abc import Callable
from pathlib import Path

from .models import GROUND_FLOOR, MAP_X_MIN, MAP_Y_MIN
from .storage import write_bytes_atomic

log = logging.getLogger(__name__)

# Pierwszy adres jest polecany przez autorów; drugi to ten sam plik bezpośrednio z repo.
FLOOR_URLS = (
    "https://tibiamaps.github.io/tibia-map-data/floor-{z:02d}-map.png",
    "https://raw.githubusercontent.com/tibiamaps/tibia-map-data/gh-pages/floor-{z:02d}-map.png",
)
TIMEOUT_SECONDS = 20
MAX_BYTES = 10 * 1024 * 1024  # piętro ma ok. 0,5-1 MB
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

Fetch = Callable[[str], bytes]


def to_pixel(x: int, y: int) -> tuple[int, int]:
    """Współrzędne z gry -> piksel na obrazku piętra."""
    return x - MAP_X_MIN, y - MAP_Y_MIN


def floor_label(z: int) -> str:
    """Opis piętra tak, jak mówią gracze: parter, +1 (w górę), -2 (pod ziemią)."""
    if z == GROUND_FLOOR:
        return "parter"
    return f"{GROUND_FLOOR - z:+d}"


def floor_path(maps_dir: Path, z: int) -> Path:
    return maps_dir / f"floor-{z:02d}-map.png"


def _download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "TibiaHelper"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("Plik mapy jest za duży")
    return data


def ensure_floor(maps_dir: Path, z: int, fetch: Fetch = _download) -> Path:
    """Ścieżka do PNG piętra; pobiera go, jeśli jeszcze go nie ma.

    Rzuca OSError albo ValueError, gdy żaden adres nie zadziałał.
    Wywołuj w wątku w tle: pobieranie może chwilę potrwać.
    """
    if not 0 <= z <= 15:
        raise ValueError(f"Nie ma piętra {z}")
    path = floor_path(maps_dir, z)
    if path.exists():
        return path
    last_error: Exception = OSError("brak adresów")
    for template in FLOOR_URLS:
        url = template.format(z=z)
        try:
            data = fetch(url)
            # Zapisujemy tylko prawdziwy PNG, a nie np. stronę błędu z HTML.
            if not data.startswith(PNG_SIGNATURE):
                raise ValueError(f"{url} nie zwrócił obrazka PNG")
            write_bytes_atomic(path, data)
            return path
        except (OSError, ValueError) as exc:
            log.info("Nie udało się pobrać mapy z %s: %s", url, exc)
            last_error = exc
    raise last_error
