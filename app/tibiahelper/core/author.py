"""Tryb autora: zmiany w data/quests.json z poziomu aplikacji.

Logika bez Qt, żeby dało się ją testować. Okno edytora (ui/quest_editor.py)
tylko zbiera dane od autora i woła te funkcje. Generator zapisuje plik tą
samą funkcją save_data, więc obie drogi pilnują tych samych zasad.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from .models import Quest
from .storage import write_bytes_atomic
from .terminology import find_forbidden

TODO_MARK = "TODO"


class AuthorError(ValueError):
    """Zmiana, której nie zapisujemy; komunikat jest dla autora."""


def load_data(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def find_quest(data: dict, quest_id: str) -> dict | None:
    return next((q for q in data["quests"] if q.get("id") == quest_id), None)


def check_quest(quest: dict) -> Quest:
    """Walidacja jednego questa z czytelnym komunikatem zamiast śladu pydantic."""
    try:
        model = Quest.model_validate(quest)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in error['loc']) or 'quest'}: {error['msg']}"
            for error in exc.errors()
        )
        raise AuthorError(f"Quest {quest.get('id', '?')!r} ma błędy: {problems}") from exc
    forbidden = find_forbidden(json.dumps(quest, ensure_ascii=False))
    if forbidden:
        raise AuthorError(
            f"Zamień {forbidden[0]!r} na „bramka lvl-owa” (odmienione w zdaniu, np. „przez bramkę lvl-ową”)."
        )
    return model


def save_data(data: dict, path: Path) -> None:
    """Sprawdza wszystkie questy, podbija data_version i zapisuje plik.

    Najpierw walidacja, potem zapis: na dysk nigdy nie trafi plik,
    który aplikacja by odrzuciła.
    """
    for quest in data["quests"]:
        check_quest(quest)
    data["data_version"] += 1
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    write_bytes_atomic(path, text.encode("utf-8"))


def replace_quest(data: dict, quest: dict) -> None:
    """Podmienia quest o tym samym id (id się nie zmienia: od niego zależy postęp graczy)."""
    for index, old in enumerate(data["quests"]):
        if old.get("id") == quest["id"]:
            data["quests"][index] = quest
            return
    raise AuthorError(f"Nie ma questa o id {quest['id']!r}")


def mark_reviewed(quest: dict, now: datetime | None = None) -> dict:
    """Zmienia szkic na przejrzany. Zwraca nowy słownik, nie zmienia podanego."""
    if any(TODO_MARK in step.get("text", "") for step in quest["steps"]):
        raise AuthorError("Quest ma jeszcze kroki z „TODO”. Uzupełnij je przed oznaczeniem jako przejrzany.")
    if not quest.get("wiki_revision"):
        raise AuthorError("Brak rewizji z TibiaWiki. Pobierz quest generatorem (fetch), potem oznacz.")
    reviewed = dict(quest)
    reviewed["status"] = "reviewed"
    reviewed["reviewed_at"] = (now or datetime.now(UTC)).isoformat(timespec="seconds")
    reviewed["needs_review"] = False
    return reviewed
