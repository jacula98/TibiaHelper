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
