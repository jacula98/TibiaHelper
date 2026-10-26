"""Obrazki potworów i opis do dymka. Bez Qt, żeby łatwo testować.

Obrazki to grafiki CipSoft z TibiaWiki, więc nie trzymamy ich w repo.
Aplikacja pobiera je przy pierwszym użyciu (adres z danych, zawsze z
serwera plików TibiaWiki) i trzyma w %APPDATA%/TibiaHelper/monsters.
"""

import logging
import urllib.request
from collections.abc import Callable
from pathlib import Path

from .models import SPRITE_URL_PREFIX, Monster
from .storage import write_bytes_atomic

log = logging.getLogger(__name__)

TIMEOUT_SECONDS = 15
MAX_BYTES = 512 * 1024  # obrazek potwora ma zwykle kilka KB
# Rozpoznajemy obrazek po pierwszych bajtach, żeby nie zapisać np. strony błędu z HTML.
SIGNATURES = {b"GIF87a": ".gif", b"GIF89a": ".gif", b"\x89PNG\r\n\x1a\n": ".png"}

ELEMENT_NAMES = {
    "physical": "fizyczne",
    "earth": "ziemia",
    "fire": "ogień",
    "energy": "energia",
    "ice": "lód",
    "holy": "święte",
    "death": "śmierć",
}

Fetch = Callable[[str], bytes]


def sprite_path(sprites_dir: Path, monster_id: str) -> Path | None:
    """Pobrany obrazek potwora albo None, gdy jeszcze go nie ma."""
    for ext in dict.fromkeys(SIGNATURES.values()):
        path = sprites_dir / f"{monster_id}{ext}"
        if path.exists():
            return path
    return None


def _download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "TibiaHelper"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("Obrazek potwora jest za duży")
    return data


def ensure_sprite(sprites_dir: Path, monster: Monster, fetch: Fetch = _download) -> Path:
    """Ścieżka do obrazka; pobiera go, jeśli jeszcze go nie ma.

    Rzuca OSError albo ValueError przy błędzie. Wywołuj w wątku w tle.
    """
    existing = sprite_path(sprites_dir, monster.id)
    if existing is not None:
        return existing
    # Model już to sprawdza; tu drugi raz, bo od tego zależy, z kim łączy się aplikacja.
    if not monster.image_url.startswith(SPRITE_URL_PREFIX):
        raise ValueError(f"Niedozwolony adres obrazka: {monster.image_url}")
    data = fetch(monster.image_url)
    ext = next((ext for sig, ext in SIGNATURES.items() if data.startswith(sig)), None)
    if ext is None:
        raise ValueError(f"{monster.image_url} nie zwrócił obrazka GIF/PNG")
    path = sprites_dir / f"{monster.id}{ext}"
    write_bytes_atomic(path, data)
    return path


def download_missing(sprites_dir: Path, monsters: list[Monster], fetch: Fetch = _download) -> list[str]:
    """Pobiera brakujące obrazki; zwraca id tych, które się udały. Błędy tylko loguje."""
    done = []
    for monster in monsters:
        if sprite_path(sprites_dir, monster.id) is not None:
            continue
        try:
            ensure_sprite(sprites_dir, monster, fetch)
            done.append(monster.id)
        except (OSError, ValueError) as exc:
            log.info("Nie udało się pobrać obrazka %s: %s", monster.id, exc)
    return done


def describe(monster: Monster) -> list[str]:
    """Linie dymka: HP i exp, potem słabości (> 100%) i odporności (< 100%)."""
    lines = [f"HP {monster.hp:,} · exp {monster.exp:,}".replace(",", " ")]
    weak = [(e, p) for e, p in monster.elements.items() if p > 100]
    strong = [(e, p) for e, p in monster.elements.items() if p < 100]
    if weak:
        lines.append("Słaby na: " + ", ".join(f"{ELEMENT_NAMES[e]} {p}%" for e, p in weak))
    if strong:
        lines.append("Odporny na: " + ", ".join(f"{ELEMENT_NAMES[e]} {p}%" for e, p in strong))
    return lines
