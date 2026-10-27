"""Link „Wyślij raport”: otwiera formularz Google z wpisaną nazwą bossa albo miejsca.

Tak jak przy „Zgłoś błąd”, aplikacja niczego sama nie wysyła. Wypełnione pola
są w adresie URL, a gracz wkleja loot (albo Hunt Analyzer) i sam klika „Prześlij”.
Odpowiedzi trafiają do publicznego arkusza autora. Program czyta go (najwyżej
co 15 minut) i pokazuje ostatnie raporty pod bossem albo miejscem huntu.
"""

import csv
import datetime
import http.client
import io
import json
import logging
import urllib.parse
from dataclasses import asdict, dataclass
from pathlib import Path

from .models import Hunt, Monster
from .storage import write_json_atomic
from .updater import Fetch, download

log = logging.getLogger(__name__)

FORM_URL = (
    "https://docs.google.com/forms/d/e/"
    "1FAIpQLSdhU_EixKIDQvsA7Di0v8rWw1YeaPniMr8g02s3kUylfg_p6Q/viewform"
)
# Numery pól formularza (z linku „Wstępne wypełnienie formularza”).
# Zmiana tytułu pytania ich nie zmienia; usunięcie pytania i dodanie nowego już tak.
SUBJECT_FIELD = "entry.125121479"  # „Boss” (dla huntów: „Hunt: <miejsce>”)
DATE_FIELD = "entry.1877872251"  # „Data”
HUNT_PREFIX = "Hunt: "


def boss_report_url(monster: Monster, today: datetime.date | None = None) -> str:
    return _url(boss_subject(monster), today)


def hunt_report_url(hunt: Hunt, today: datetime.date | None = None) -> str:
    # Jeden formularz na oba rodzaje raportów; przedrostek odróżnia miejsce od bossa.
    return _url(hunt_subject(hunt), today)


def _url(subject: str, today: datetime.date | None) -> str:
    today = today or datetime.date.today()
    # Pola autora i komentarza zostają puste: wypełnia je gracz.
    query = urllib.parse.urlencode(
        {"usp": "pp_url", SUBJECT_FIELD: subject, DATE_FIELD: today.isoformat()}
    )
    return f"{FORM_URL}?{query}"


# --- ostatnie raporty (odczyt arkusza z odpowiedziami) ------------------------

# Publiczny eksport arkusza z odpowiedziami jako CSV (tylko odczyt, bez klucza).
SHEET_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1Yo_v_KamDe85JXVRolC0f8sGUWpRsMec6iHk5QKMrSw/export?format=csv"
)
REFRESH_SECONDS = 15 * 60  # częściej nie pytamy: raporty nie zmieniają się co minutę
MAX_REPORTS = 2000  # tyle najnowszych wierszy trzymamy (resztę pomijamy)
# Teksty wpisują obcy ludzie: ucinamy je, żeby jeden wpis nie zalał okna.
MAX_LOOT = 1500
MAX_SHORT = 80
MAX_COMMENT = 300
# Nagłówki to tytuły pytań; szukamy po początku, bo jacek może je jeszcze poprawić.
_COLUMNS = {
    "subject": ("boss",),
    "loot": ("loot",),
    "date": ("data", "date"),
    "author": ("autor", "author"),
    "comment": ("komentarz", "comment"),
    "timestamp": ("sygnatura", "timestamp"),
}


@dataclass(frozen=True)
class Report:
    subject: str
    loot: str
    date: str
    author: str
    comment: str


def _clip(text: str, limit: int) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _column_indexes(header: list[str]) -> dict[str, int]:
    found: dict[str, int] = {}
    for index, title in enumerate(header):
        title = title.strip().casefold()
        for key, prefixes in _COLUMNS.items():
            if key not in found and title.startswith(prefixes):
                found[key] = index
    return found


def parse_reports(data: bytes) -> list[Report]:
    """CSV z arkusza -> raporty, najnowsze pierwsze. Rzuca ValueError przy złym formacie."""
    try:
        rows = list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))
    except (UnicodeDecodeError, csv.Error) as exc:
        raise ValueError(f"Zły plik z raportami: {exc}") from exc
    if not rows:
        return []
    columns = _column_indexes(rows[0])
    if "subject" not in columns or "loot" not in columns:
        raise ValueError("W arkuszu nie ma kolumn Boss i Loot")

    def cell(row: list[str], key: str) -> str:
        index = columns.get(key)
        return row[index] if index is not None and index < len(row) else ""

    reports = []
    # Formularz dopisuje odpowiedzi na końcu arkusza, więc od końca = od najnowszych.
    for row in reversed(rows[1:]):
        subject, loot = cell(row, "subject").strip(), cell(row, "loot").strip()
        if not subject or not loot:
            continue
        date = cell(row, "date").strip() or cell(row, "timestamp").strip()[:10]
        reports.append(
            Report(
                subject=_clip(subject, MAX_SHORT),
                loot=_clip(loot, MAX_LOOT),
                date=_clip(date, MAX_SHORT),
                author=_clip(cell(row, "author"), MAX_SHORT),
                comment=_clip(cell(row, "comment"), MAX_COMMENT),
            )
        )
        if len(reports) >= MAX_REPORTS:
            break
    return reports


def boss_subject(monster: Monster) -> str:
    return monster.name


def hunt_subject(hunt: Hunt) -> str:
    return HUNT_PREFIX + hunt.name


def reports_for(reports: list[Report], subject: str) -> list[Report]:
    """Raporty o jednym bossie albo miejscu. Wielkość liter i spacje nie mają znaczenia."""
    key = " ".join(subject.split()).casefold()
    return [r for r in reports if " ".join(r.subject.split()).casefold() == key]


def load_cache(path: Path) -> tuple[float, list[Report]]:
    """(czas pobrania, raporty) z pliku. Brak albo zły plik: (0, [])."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        reports = [Report(**{k: str(item[k]) for k in Report.__dataclass_fields__}) for item in raw["reports"]]
        return float(raw["fetched_at"]), reports[:MAX_REPORTS]
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return 0.0, []


def get_reports(cache: Path, now: float, fetch: Fetch = download) -> list[Report]:
    """Raporty z pliku albo świeże z arkusza (najwyżej co REFRESH_SECONDS). Bez sieci: ostatnie znane.

    Wołaj w wątku w tle: pobranie arkusza może trwać kilka sekund.
    """
    fetched_at, cached = load_cache(cache)
    if 0 <= now - fetched_at < REFRESH_SECONDS:
        return cached
    try:
        fresh = parse_reports(fetch(SHEET_CSV_URL))
    except (OSError, http.client.HTTPException, ValueError) as exc:
        log.info("Pobieranie raportów pominięte: %s", exc)
        return cached
    try:
        write_json_atomic(cache, {"fetched_at": now, "reports": [asdict(r) for r in fresh]})
    except OSError as exc:
        log.info("Nie udało się zapisać %s: %s", cache, exc)
    return fresh
