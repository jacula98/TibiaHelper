"""Wspólny zapis plików JSON w katalogu użytkownika."""

import json
import os
from pathlib import Path


def write_json_atomic(path: Path, data: object) -> None:
    """Zapisuje JSON atomowo. Błąd zapisu zgłasza jako OSError.

    Najpierw plik tymczasowy, potem podmiana. Gdy komputer wyłączy się w trakcie
    zapisu, zostaje stary plik, a nie urwany JSON.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
