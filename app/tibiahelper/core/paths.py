"""Ścieżki do plików aplikacji."""

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
