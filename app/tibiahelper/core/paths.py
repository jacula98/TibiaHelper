"""Ścieżki do plików aplikacji."""

import os
import sys
from pathlib import Path


def bundled_data_file() -> Path:
    """quests.json dołączony do aplikacji.

    W .exe z PyInstallera pliki są rozpakowane do katalogu sys._MEIPASS.
    Przy uruchomieniu ze źródeł bierzemy data/ z katalogu repo.
    """
    bundle_dir = getattr(sys, "_MEIPASS", None)
    if bundle_dir:
        return Path(bundle_dir) / "data" / "quests.json"
    return Path(__file__).resolve().parents[3] / "data" / "quests.json"


def user_data_dir() -> Path:
    """Katalog na dane użytkownika: %APPDATA%/TibiaHelper na Windowsie.

    Poza Windowsem (np. testy na Linuksie) używamy ~/.tibiahelper.
    """
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "TibiaHelper"
    return Path.home() / ".tibiahelper"


def progress_file() -> Path:
    return user_data_dir() / "progress.json"


def cached_data_file() -> Path:
    """quests.json pobrany z GitHuba (nowszy niż wbudowany)."""
    return user_data_dir() / "quests.json"


def settings_file() -> Path:
    return user_data_dir() / "settings.json"


def maps_dir() -> Path:
    """Pobrane mapy pięter (tibiamaps)."""
    return user_data_dir() / "maps"


def sprites_dir() -> Path:
    """Pobrane obrazki potworów (TibiaWiki, © CipSoft)."""
    return user_data_dir() / "monsters"


def items_dir() -> Path:
    """Pobrane obrazki przedmiotów z lootu (TibiaWiki, © CipSoft)."""
    return user_data_dir() / "items"


def npcs_dir() -> Path:
    """Pobrane obrazki NPC (TibiaWiki, © CipSoft)."""
    return user_data_dir() / "npcs"


def bundled_spawns_file() -> Path:
    """spawns.json dołączony do aplikacji (obok quests.json)."""
    return bundled_data_file().with_name("spawns.json")


def cached_spawns_file() -> Path:
    """spawns.json pobrany z GitHuba razem z aktualizacją poradników."""
    return user_data_dir() / "spawns.json"


def bundled_qol_dir() -> Path:
    """Gotowe ustawienia lootu i cen (Quality of life), dołączone obok quests.json."""
    return bundled_data_file().with_name("qol")


def boosted_file() -> Path:
    """Dzisiejszy boosted potwór i boss (z TibiaWiki), żeby nie pytać wiki przy każdym starcie."""
    return user_data_dir() / "boosted.json"


def bundled_reports_file() -> Path:
    """reports.json dołączony do aplikacji (obok quests.json)."""
    return bundled_data_file().with_name("reports.json")


def cached_reports_file() -> Path:
    """reports.json pobrany z GitHuba razem z aktualizacją poradników."""
    return user_data_dir() / "reports.json"
