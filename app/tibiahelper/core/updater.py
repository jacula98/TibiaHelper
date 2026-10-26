"""Aktualizacja questów z GitHuba.

Jak to działa:
- przy starcie bierzemy lokalną kopię o wyższym data_version: wbudowaną
  w aplikację albo pobraną wcześniej do %APPDATA%/TibiaHelper/quests.json,
- w tle pobieramy quests.json z repo na GitHubie; jeśli jest poprawny
  i nowszy, pytamy użytkownika, czy zaktualizować; dopiero po zgodzie
  zapisujemy go jako nową kopię lokalną,
- bez internetu po prostu zostaje to, co już jest na dysku.

Pobrany plik to tylko dane (JSON): walidujemy go tak samo jak lokalny
i nigdy nie wykonujemy z niego żadnego kodu.
"""

import http.client
import json
import logging
import urllib.request
import zlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .repository import LoadResult, QuestFileError, load_quest_file, parse_quest_data
from .spawns import parse_spawns
from .storage import write_json_atomic

log = logging.getLogger(__name__)

DATA_URL = "https://raw.githubusercontent.com/jacula98/TibiaHelper/main/data/quests.json"
# Miejsca występowania potworów (TibiaRoute): pobierane razem z nowymi poradnikami.
SPAWNS_URL = "https://raw.githubusercontent.com/jacula98/TibiaHelper/main/data/spawns.json"
TIMEOUT_SECONDS = 10
# Plik z bazą potworów i questów ma ok. 5 MB (spakowany gzipem ok. 0,7 MB).
# Limity chronią przed pobieraniem albo rozpakowaniem czegoś ogromnego.
MAX_BYTES = 15 * 1024 * 1024  # tyle pobieramy z sieci (gdyby serwer nie spakował pliku)
MAX_UNPACKED = 30 * 1024 * 1024  # tyle może mieć plik po rozpakowaniu

# Funkcja pobierająca: url -> bajty. W testach podmieniamy ją na sztuczną.
Fetch = Callable[[str], bytes]


def load_best_local(bundled: Path, cached: Path) -> LoadResult:
    """Wybiera lokalną kopię o wyższym data_version.

    Wbudowana kopia może być nowsza od pobranej, np. po instalacji nowej
    wersji programu. Uszkodzona kopia pobrana nie blokuje wbudowanej.
    """
    best: LoadResult | None = None
    last_error: QuestFileError | None = None
    for path in (bundled, cached):
        if not path.exists():
            continue
        try:
            result = load_quest_file(path)
        except QuestFileError as exc:
            log.warning("%s", exc)
            last_error = exc
            continue
        if best is None or result.data_version > best.data_version:
            best = result
    if best is None:
        raise last_error or QuestFileError("Brak pliku z questami")
    return best


def download(url: str = DATA_URL) -> bytes:
    if not url.startswith("https://"):
        raise ValueError("Dane pobieramy tylko przez HTTPS")
    # gzip: GitHub wysyła wtedy ok. 7x mniej danych przy każdym sprawdzeniu aktualizacji.
    request = urllib.request.Request(url, headers={"User-Agent": "TibiaHelper", "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
        data = response.read(MAX_BYTES + 1)
        packed = response.headers.get("Content-Encoding", "").lower() == "gzip"
    if len(data) > MAX_BYTES:
        raise ValueError("Plik z danymi jest za duży")
    return gunzip(data) if packed else data


def gunzip(data: bytes) -> bytes:
    """Rozpakowuje gzip z limitem rozmiaru (mały plik może się rozpakować do ogromnego)."""
    unpacker = zlib.decompressobj(16 + zlib.MAX_WBITS)  # 16+: format gzip, nie goły zlib
    try:
        result = unpacker.decompress(data, MAX_UNPACKED + 1)
    except zlib.error as exc:
        raise ValueError(f"Uszkodzony gzip: {exc}") from exc
    if len(result) > MAX_UNPACKED or unpacker.unconsumed_tail:
        raise ValueError("Plik z danymi po rozpakowaniu jest za duży")
    return result


@dataclass(frozen=True)
class Update:
    """Nowsze dane z GitHuba, jeszcze niezapisane na dysku."""

    result: LoadResult
    raw: dict
    # Nowsze spawns.json albo None (brak zmian lub nie udało się pobrać).
    spawns_raw: dict | None = None

    @property
    def data_version(self) -> int:
        return self.result.data_version


def check_for_update(current_version: int, fetch: Fetch = download, spawns_version: int = 0) -> Update | None:
    """Sprawdza, czy na GitHubie są nowsze dane. Niczego nie zapisuje.

    Zapis robi dopiero apply_update(), gdy użytkownik się zgodzi.
    Każdy problem (brak sieci, zły JSON, za nowy schemat) kończy się None
    i wpisem w logu: aplikacja działa dalej na danych lokalnych.
    """
    try:
        raw = json.loads(fetch(DATA_URL).decode("utf-8"))
        result = parse_quest_data(raw)
    except (OSError, http.client.HTTPException, ValueError, QuestFileError) as exc:
        # OSError: błędy sieci (URLError, timeout); HTTPException: zerwane połączenie
        # w trakcie odczytu; ValueError: zły JSON albo UTF-8.
        log.info("Sprawdzanie aktualizacji pominięte: %s", exc)
        return None
    if result.data_version <= current_version:
        return None
    return Update(result, raw, _check_spawns(spawns_version, fetch))


def _check_spawns(current_version: int, fetch: Fetch) -> dict | None:
    """spawns.json, jeśli na GitHubie jest nowszy. Błąd tu nie blokuje aktualizacji poradników."""
    try:
        raw = json.loads(fetch(SPAWNS_URL).decode("utf-8"))
        version = parse_spawns(raw).version
    except (OSError, http.client.HTTPException, ValueError) as exc:
        log.info("Pominięto aktualizację miejsc potworów: %s", exc)
        return None
    return raw if version > current_version else None


def apply_update(update: Update, cached: Path, cached_spawns: Path | None = None) -> bool:
    """Zapisuje pobrane dane jako lokalną kopię. False, gdy zapis się nie udał."""
    try:
        # Najpierw spawny: gdy ten zapis się nie uda, poradniki zostają stare
        # i przy następnym starcie aktualizacja (razem ze spawnami) będzie zaproponowana znowu.
        if update.spawns_raw is not None and cached_spawns is not None:
            write_json_atomic(cached_spawns, update.spawns_raw)
        write_json_atomic(cached, update.raw)
    except OSError as exc:
        log.error("Nie można zapisać pobranych danych do %s: %s", cached, exc)
        return False
    return True
