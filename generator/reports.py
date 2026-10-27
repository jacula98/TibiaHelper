"""Raporty graczy z formularza Google -> data/reports.json.

Arkusz odpowiedzi czyta tylko autor (ta komenda), a nie program graczy: przy wielu
graczach Google mógłby blokować częste pobieranie. Gracze dostają raporty razem
z aktualizacją poradników (jak spawns.json).
"""

import json
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from tibiahelper.core.reports import SHEET_CSV_URL, Report, load_reports, parse_reports, reports_to_json
from tibiahelper.core.storage import write_bytes_atomic

from .quests_file import DATA_FILE

REPORTS_FILE = DATA_FILE.with_name("reports.json")
MAX_BYTES = 5 * 1024 * 1024


def download(url: str = SHEET_CSV_URL) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "TibiaHelper-generator"})
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 (stały adres https)
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("Arkusz z raportami jest za duży")
    return data


def update(csv_data: bytes, path: Path = REPORTS_FILE, now: datetime | None = None) -> int | None:
    """Zapisuje raporty, gdy się zmieniły. Zwraca liczbę raportów albo None (bez zmian).

    Bez zmian nie zapisujemy: inaczej każde uruchomienie dawałoby graczom „nowe dane”.
    """
    reports: list[Report] = parse_reports(csv_data)
    if path.exists() and load_reports(path)[1] == reports:
        return None
    now = now or datetime.now(UTC)
    version = int(now.strftime("%Y%m%d%H%M"))  # rośnie z czasem, jak wersja spawnów
    text = json.dumps(reports_to_json(version, reports), ensure_ascii=False, indent=1) + "\n"
    write_bytes_atomic(path, text.encode("utf-8"))
    return len(reports)
