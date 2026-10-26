"""Odczyt i zapis data/quests.json po stronie generatora."""

from pathlib import Path

from tibiahelper.core import author

DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "quests.json"


def load(path: Path = DATA_FILE) -> dict:
    return author.load_data(path)


def find(data: dict, quest_id: str) -> dict | None:
    return author.find_quest(data, quest_id)


def save(data: dict, path: Path = DATA_FILE) -> None:
    """Zapis wspólny z edytorem w trybie autora: walidacja, data_version + 1, zapis atomowy."""
    author.save_data(data, path)
