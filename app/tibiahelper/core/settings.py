"""Ustawienia okna: przezroczystość, motyw kolorystyczny, pozycja i rozmiar oraz język.

Plik JSON w %APPDATA%/TibiaHelper/settings.json:
    {"version": 1, "opacity": 0.9, "theme": "dark", "geometry": "<base64>", "language": "pl", "world": "Antica"}
"theme" to klucz motywu z ui/theme.py (nieznany klucz = motyw domyślny).
"geometry" to wynik QWidget.saveGeometry() zapisany jako tekst base64.
"world" to świat (serwer) do powiadomień o bossach; brak = powiadomienia wyłączone.
Ten moduł nie zna Qt, żeby dało się go testować bez okna.
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from .boss_watch import clean_world
from .i18n import DEFAULT_LANGUAGE, LANGUAGES
from .storage import write_json_atomic

log = logging.getLogger(__name__)

SETTINGS_VERSION = 1
MIN_OPACITY = 0.1  # 0% schowałoby okno całkiem i nie dałoby się go znaleźć
MAX_OPACITY = 1.0
DEFAULT_THEME = "dark"


@dataclass
class Settings:
    opacity: float = MAX_OPACITY
    theme: str = DEFAULT_THEME
    geometry: str | None = None
    language: str = DEFAULT_LANGUAGE
    world: str | None = None


def clamp_opacity(value: float) -> float:
    return min(MAX_OPACITY, max(MIN_OPACITY, value))


def load_settings(path: Path) -> Settings:
    """Wczytuje ustawienia. Brak albo uszkodzony plik daje ustawienia domyślne."""
    if not path.exists():
        return Settings()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        opacity = clamp_opacity(float(raw.get("opacity", MAX_OPACITY)))
        geometry = raw.get("geometry")
        if geometry is not None and not isinstance(geometry, str):
            geometry = None
        # Starsze pliki nie mają motywu, więc biorą domyślny.
        theme = raw.get("theme", DEFAULT_THEME)
        if not isinstance(theme, str):
            theme = DEFAULT_THEME
        # Nieznany język (np. wpisany ręcznie) daje polski zamiast błędu.
        language = raw.get("language", DEFAULT_LANGUAGE)
        if not isinstance(language, str) or language not in LANGUAGES:
            language = DEFAULT_LANGUAGE
        # Zła nazwa świata (np. wpisana ręcznie w pliku) wyłącza powiadomienia o bossach.
        world = clean_world(raw.get("world"))
        return Settings(opacity=opacity, theme=theme, geometry=geometry, language=language, world=world)
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        # Ustawienia łatwo odtworzyć, więc przy błędzie po prostu startujemy od domyślnych.
        log.warning("Nie można odczytać ustawień z %s: %s", path, exc)
        return Settings()


def save_settings(path: Path, settings: Settings) -> None:
    data = {
        "version": SETTINGS_VERSION,
        "opacity": clamp_opacity(settings.opacity),
        "theme": settings.theme,
        "geometry": settings.geometry,
        "language": settings.language,
        "world": clean_world(settings.world),
    }
    try:
        write_json_atomic(path, data)
    except OSError as exc:
        log.error("Nie można zapisać ustawień do %s: %s", path, exc)
