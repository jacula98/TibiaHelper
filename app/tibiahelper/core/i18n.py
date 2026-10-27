"""Tłumaczenia interfejsu. Bez Qt, żeby łatwo testować.

Kluczem jest polski tekst z kodu: tr("Ustawienia") w języku angielskim daje "Settings".
Tłumaczenia są w app/tibiahelper/i18n/<kod>.json ({"polski tekst": "tłumaczenie"}).
Brak tłumaczenia = polski tekst, więc program nigdy nie pokaże pustego napisu.

Zmienne w tekście zapisujemy jako {nazwa}: tr("Wersja: {n}", n=3). Tłumacz może
przestawić {n} w zdaniu, czego nie da się zrobić, sklejając kawałki tekstu.

Treść questów (kroki z data/quests.json) zostaje po polsku. Nazwy potworów,
przedmiotów i NPC są po angielsku, tak jak w grze, i ich nie tłumaczymy.
"""

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

# Obok kodu, jak ui/assets. W .exe: --add-data "app/tibiahelper/i18n;tibiahelper/i18n".
TRANSLATIONS_DIR = Path(__file__).resolve().parent.parent / "i18n"
DEFAULT_LANGUAGE = "pl"
# Kod -> nazwa w tym języku (gracz szuka swojego języka po jego własnej nazwie).
LANGUAGES = {
    "pl": "Polski",
    "en": "English",
    "pt_BR": "Português (Brasil)",
    "de": "Deutsch",
    "sv": "Svenska",
}

_language = DEFAULT_LANGUAGE
_catalog: dict[str, str] = {}


def load_catalog(language: str, folder: Path | None = None) -> dict[str, str]:
    """Słownik tłumaczeń języka. Polski i brakujący albo uszkodzony plik dają pusty słownik."""
    if language == DEFAULT_LANGUAGE:
        return {}
    path = (folder or TRANSLATIONS_DIR) / f"{language}.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.warning("Brak tłumaczeń dla %s: %s", language, exc)
        return {}
    if not isinstance(raw, dict):
        return {}
    # Tylko pary tekst -> niepusty tekst: zły wpis nie może wywrócić programu.
    return {k: v for k, v in raw.items() if isinstance(k, str) and isinstance(v, str) and v}


def set_language(language: str) -> str:
    """Ustawia język całego programu. Nieznany kod daje polski. Zwraca użyty kod."""
    global _language, _catalog
    if language not in LANGUAGES:
        language = DEFAULT_LANGUAGE
    _language = language
    _catalog = load_catalog(language)
    return language


def current_language() -> str:
    return _language


def tr(text: str, **values: object) -> str:
    """Tekst w wybranym języku; {nazwa} w tekście zastępuje wartością z values."""
    translated = _catalog.get(text, text)
    if not values:
        return translated
    try:
        return translated.format(**values)
    except (KeyError, IndexError, ValueError, TypeError, AttributeError):
        # Literówka w tłumaczeniu (np. {m} zamiast {n}): lepiej pokazać polski tekst niż się wywrócić.
        return text.format(**values)


def N_(text: str) -> str:  # noqa: N802 (nazwa jak w gettext)
    """Oznacza tekst do tłumaczenia, ale go nie tłumaczy.

    Dla stałych modułu (np. nazwy sortowania): powstają przy imporcie, zanim
    wiadomo, jaki język wybrał gracz. Tłumaczymy je dopiero przy pokazaniu: tr(stała).
    Test (tests/test_i18n.py) zbiera teksty z tr("...") i N_("..."), żeby sprawdzić tłumaczenia.
    """
    return text
