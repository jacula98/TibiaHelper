"""Aktualizacja questów z GitHuba.

Jak to działa:
- przy starcie bierzemy lokalną kopię o wyższym data_version: wbudowaną
  w aplikację albo pobraną wcześniej do %APPDATA%/TibiaHelper/quests.json,
- w tle pobieramy quests.json z repo na GitHubie; jeśli jest poprawny
  i nowszy, zapisujemy go jako nową kopię lokalną,
- bez internetu po prostu zostaje to, co już jest na dysku.

Pobrany plik to tylko dane (JSON): walidujemy go tak samo jak lokalny
i nigdy nie wykonujemy z niego żadnego kodu.
"""

import http.client
import json
import logging
import urllib.request
from collections.abc import Callable
from pathlib import Path

from .repository import LoadResult, QuestFileError, load_quest_file, parse_quest_data
from .storage import write_json_atomic

log = logging.getLogger(__name__)

DATA_URL = "https://raw.githubusercontent.com/jacula98/TibiaHelper/main/data/quests.json"
TIMEOUT_SECONDS = 10
# Obecny plik ma kilkanaście KB. Limit chroni przed pobieraniem czegoś ogromnego.
MAX_BYTES = 5 * 1024 * 1024

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
    request = urllib.request.Request(url, headers={"User-Agent": "TibiaHelper"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("Plik z danymi jest za duży")
    return data


def update_from_github(
    current_version: int, cached: Path, fetch: Fetch = download
) -> LoadResult | None:
    """Pobiera dane z GitHuba. Zwraca nowe dane albo None, gdy nie ma nic nowszego.

    Każdy problem (brak sieci, zły JSON, za nowy schemat) kończy się None
    i wpisem w logu: aplikacja działa dalej na danych lokalnych.
    """
    try:
        raw = json.loads(fetch(DATA_URL).decode("utf-8"))
        result = parse_quest_data(raw)
    except (OSError, http.client.HTTPException, ValueError, QuestFileError) as exc:
        # OSError: błędy sieci (URLError, timeout); HTTPException: zerwane połączenie
        # w trakcie odczytu; ValueError: zły JSON albo UTF-8.
        log.info("Aktualizacja danych pominięta: %s", exc)
        return None

    if result.data_version <= current_version:
        return None
    try:
        write_json_atomic(cached, raw)
    except OSError as exc:
        # Nowe dane i tak pokażemy teraz; zapis spróbuje się udać przy kolejnym starcie.
        log.error("Nie można zapisać pobranych danych do %s: %s", cached, exc)
    return result
