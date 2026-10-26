"""Odczyt i zapis data/quests.json po stronie generatora."""

import json
import os
from pathlib import Path

from tibiahelper.core.models import Quest

DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "quests.json"


def load(path: Path = DATA_FILE) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def find(data: dict, quest_id: str) -> dict | None:
    return next((q for q in data["quests"] if q.get("id") == quest_id), None)


def save(data: dict, path: Path = DATA_FILE) -> None:
    """Zapisuje plik po walidacji każdego questa i podbija data_version.

    Walidujemy przed zapisem, żeby generator nigdy nie zapisał pliku,
    który aplikacja by odrzuciła.
    """
    for quest in data["quests"]:
        Quest.model_validate(quest)
    data["data_version"] += 1
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
