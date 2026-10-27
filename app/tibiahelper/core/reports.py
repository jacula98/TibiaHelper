"""Link „Wyślij raport”: otwiera formularz Google z wpisaną nazwą bossa albo miejsca.

Tak jak przy „Zgłoś błąd”, aplikacja niczego sama nie wysyła. Wypełnione pola
są w adresie URL, a gracz wkleja loot (albo Hunt Analyzer) i sam klika „Prześlij”.
Odpowiedzi trafiają do arkusza autora, z którego korzysta generator.
"""

import datetime
import urllib.parse

from .models import Hunt, Monster

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
    return _url(monster.name, today)


def hunt_report_url(hunt: Hunt, today: datetime.date | None = None) -> str:
    # Jeden formularz na oba rodzaje raportów; przedrostek odróżnia miejsce od bossa.
    return _url(HUNT_PREFIX + hunt.name, today)


def _url(subject: str, today: datetime.date | None) -> str:
    today = today or datetime.date.today()
    # Pola autora i komentarza zostają puste: wypełnia je gracz.
    query = urllib.parse.urlencode(
        {"usp": "pp_url", SUBJECT_FIELD: subject, DATE_FIELD: today.isoformat()}
    )
    return f"{FORM_URL}?{query}"
