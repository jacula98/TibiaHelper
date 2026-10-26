"""Wspólny zapis plików w katalogu użytkownika."""

import json
import os
from pathlib import Path


def write_bytes_atomic(path: Path, data: bytes) -> None:
    """Zapisuje plik atomowo. Błąd zapisu zgłasza jako OSError.

    Najpierw plik tymczasowy, potem podmiana. Gdy komputer wyłączy się w trakcie
    zapisu, zostaje stary plik, a nie urwany.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def write_json_atomic(path: Path, data: object) -> None:
    write_bytes_atomic(path, json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))
