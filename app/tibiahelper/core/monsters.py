"""Obrazki potworów i opis do dymka. Bez Qt, żeby łatwo testować.

Obrazki to grafiki CipSoft z TibiaWiki, więc nie trzymamy ich w repo.
Aplikacja pobiera je przy pierwszym użyciu (adres z danych, zawsze z
serwera plików TibiaWiki) i trzyma w %APPDATA%/TibiaHelper/monsters.
"""

import logging
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

from .i18n import N_, tr
from .models import SPRITE_URL_PREFIX, Monster
from .storage import write_bytes_atomic

log = logging.getLogger(__name__)

TIMEOUT_SECONDS = 15
MAX_BYTES = 512 * 1024  # obrazek potwora ma zwykle kilka KB
RETRIES = 2
RETRY_DELAY = 1.0  # sekundy
# Rozpoznajemy obrazek po pierwszych bajtach, żeby nie zapisać np. strony błędu z HTML.
SIGNATURES = {b"GIF87a": ".gif", b"GIF89a": ".gif", b"\x89PNG\r\n\x1a\n": ".png"}

# N_: tłumaczymy przy pokazaniu, tr(ELEMENT_NAMES[...]) (zob. i18n.py).
ELEMENT_NAMES = {
    "physical": N_("fizyczne"),
    "earth": N_("ziemia"),
    "fire": N_("ogień"),
    "energy": N_("energia"),
    "ice": N_("lód"),
    "holy": N_("święte"),
    "death": N_("śmierć"),
}

Fetch = Callable[[str], bytes]


def sprite_path(sprites_dir: Path, monster_id: str) -> Path | None:
    """Pobrany obrazek potwora albo None, gdy jeszcze go nie ma."""
    return image_path(sprites_dir, monster_id)


def image_path(folder: Path, key: str) -> Path | None:
    """Pobrany obrazek (potwora albo przedmiotu) o tej nazwie pliku albo None."""
    for ext in dict.fromkeys(SIGNATURES.values()):
        path = folder / f"{key}{ext}"
        if path.exists():
            return path
    return None


def item_key(name: str) -> str:
    """Nazwa pliku obrazka przedmiotu, np. "Dragon's Tail" -> "dragon-s-tail"."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "item"


def _download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "TibiaHelper"})
    for attempt in range(RETRIES + 1):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
                data = response.read(MAX_BYTES + 1)
            break
        except urllib.error.HTTPError as exc:
            # Serwer obrazków wiki czasem odpowiada 503; po chwili ten sam adres działa.
            if exc.code < 500 or attempt == RETRIES:
                raise
            time.sleep(RETRY_DELAY)
    if len(data) > MAX_BYTES:
        raise ValueError("Obrazek potwora jest za duży")
    return data


def original_url(url: str) -> str:
    """Adres pliku w oryginalnym formacie (GIF/PNG).

    Bez tego serwer Fandomu często oddaje WebP, którego nie zapisujemy.
    """
    return url + ("&" if "?" in url else "?") + "format=original"


def ensure_sprite(sprites_dir: Path, monster: Monster, fetch: Fetch = _download) -> Path:
    """Ścieżka do obrazka potwora; pobiera go, jeśli jeszcze go nie ma.

    Rzuca OSError albo ValueError przy błędzie. Wywołuj w wątku w tle.
    """
    return ensure_image(sprites_dir, monster.id, monster.image_url, fetch)


def ensure_image(folder: Path, key: str, url: str | None, fetch: Fetch = _download) -> Path:
    """Obrazek z serwera plików TibiaWiki zapisany jako folder/key.gif (albo .png)."""
    existing = image_path(folder, key)
    if existing is not None:
        return existing
    # Model już to sprawdza; tu drugi raz, bo od tego zależy, z kim łączy się aplikacja.
    if url is None or not url.startswith(SPRITE_URL_PREFIX):
        raise ValueError(f"Niedozwolony adres obrazka: {url}")
    data = fetch(original_url(url))
    ext = next((ext for sig, ext in SIGNATURES.items() if data.startswith(sig)), None)
    if ext is None:
        raise ValueError(f"{url} nie zwrócił obrazka GIF/PNG")
    path = folder / f"{key}{ext}"
    write_bytes_atomic(path, data)
    return path


def download_items(items_dir: Path, images: dict[str, str], fetch: Fetch = _download) -> list[str]:
    """Pobiera brakujące obrazki przedmiotów (nazwa -> adres); zwraca nazwy pobranych."""
    done = []
    for name, url in images.items():
        if image_path(items_dir, item_key(name)) is not None:
            continue
        try:
            ensure_image(items_dir, item_key(name), url, fetch)
            done.append(name)
        except (OSError, ValueError) as exc:
            log.info("Nie udało się pobrać obrazka %s: %s", name, exc)
    return done


def download_missing(sprites_dir: Path, monsters: list[Monster], fetch: Fetch = _download) -> list[str]:
    """Pobiera brakujące obrazki; zwraca id tych, które się udały. Błędy tylko loguje."""
    done = []
    for monster in monsters:
        if monster.image_url is None or sprite_path(sprites_dir, monster.id) is not None:
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
        lines.append(tr("Słaby na: {list}", list=", ".join(f"{tr(ELEMENT_NAMES[e])} {p}%" for e, p in weak)))
    if strong:
        lines.append(tr("Odporny na: {list}", list=", ".join(f"{tr(ELEMENT_NAMES[e])} {p}%" for e, p in strong)))
    return lines


# Sortowanie listy potworów: nazwa -> (klucz, malejąco?). Kolejność tu = kolejność w menu.
# Polska nazwa jest kluczem; w menu pokazujemy tr(nazwa).
SORTS: dict[str, tuple[Callable[[Monster], object], bool]] = {
    "A–Z": (lambda m: m.name.lower(), False),
    N_("HP rosnąco"): (lambda m: m.hp, False),
    N_("HP malejąco"): (lambda m: m.hp, True),
    N_("Exp rosnąco"): (lambda m: m.exp, False),
    N_("Exp malejąco"): (lambda m: m.exp, True),
    # Exp za każdy punkt HP: im więcej, tym bardziej opłaca się bić (max(hp, 1), bo bywa HP 0).
    N_("Exp / HP (najlepsze)"): (lambda m: m.exp / max(m.hp, 1), True),
}


# Filtry listy jak przy przedmiotach: grupy domyślnie ukryte, do pokazania w menu „Filtry”.
MONSTER_FILTERS: dict[str, Callable[[Monster], bool]] = {
    N_("Bossy"): lambda m: m.boss,
    N_("Eventowe"): lambda m: m.event,
    N_("Niedostępne w grze"): lambda m: m.unavailable,
    N_("Bez HP na wiki"): lambda m: m.hp == 0,
    # Np. zwierzęta z miast, przyzwańce i obiekty z questów: nic za nie nie wpada.
    N_("Bez expa"): lambda m: m.exp == 0,
}


def sort_monsters(monsters: list[Monster], sort: str) -> list[Monster]:
    """Potwory posortowane wybranym sposobem; przy remisie alfabetycznie."""
    key, reverse = SORTS[sort]
    by_name = sorted(monsters, key=lambda m: m.name.lower())
    # sorted jest stabilne: remisy zostają w kolejności alfabetycznej.
    return sorted(by_name, key=key, reverse=reverse)
