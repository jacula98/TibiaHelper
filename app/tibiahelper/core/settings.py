"""Ustawienia okna: przezroczystość oraz pozycja i rozmiar.

Plik JSON w %APPDATA%/TibiaHelper/settings.json:
    {"version": 1, "opacity": 0.9, "geometry": "<base64>"}
"geometry" to wynik QWidget.saveGeometry() zapisany jako tekst base64.
Ten moduł nie zna Qt, żeby dało się go testować bez okna.
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from .storage import write_json_atomic

log = logging.getLogger(__name__)

SETTINGS_VERSION = 1
MIN_OPACITY = 0.1  # 0% schowałoby okno całkiem i nie dałoby się go znaleźć
MAX_OPACITY = 1.0


@dataclass
class Settings:
    opacity: float = MAX_OPACITY
    geometry: str | None = None


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
        return Settings(opacity=opacity, geometry=geometry)
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        # Ustawienia łatwo odtworzyć, więc przy błędzie po prostu startujemy od domyślnych.
        log.warning("Nie można odczytać ustawień z %s: %s", path, exc)
        return Settings()


def save_settings(path: Path, settings: Settings) -> None:
    data = {
        "version": SETTINGS_VERSION,
        "opacity": clamp_opacity(settings.opacity),
        "geometry": settings.geometry,
    }
    try:
        write_json_atomic(path, data)
    except OSError as exc:
        log.error("Nie można zapisać ustawień do %s: %s", path, exc)
