"""Tryb autora: zmiany w data/quests.json z poziomu aplikacji.

Logika bez Qt, żeby dało się ją testować. Okno edytora (ui/quest_editor.py)
tylko zbiera dane od autora i woła te funkcje. Generator zapisuje plik tą
samą funkcją save_data, więc obie drogi pilnują tych samych zasad.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from .models import SCHEMA_VERSION, Boss, Hunt, Monster, Quest
from .storage import write_bytes_atomic
from .terminology import find_forbidden

TODO_MARK = "TODO"


class AuthorError(ValueError):
    """Zmiana, której nie zapisujemy; komunikat jest dla autora."""


def load_data(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def find_quest(data: dict, quest_id: str) -> dict | None:
    return next((q for q in data["quests"] if q.get("id") == quest_id), None)


def _problems(exc: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(p) for p in error['loc']) or 'całość'}: {error['msg']}" for error in exc.errors()
    )


def check_quest(quest: dict, monster_ids: set[str] | None = None) -> Quest:
    """Walidacja jednego questa z czytelnym komunikatem zamiast śladu pydantic.

    monster_ids: znane potwory z pliku; None = nie sprawdzamy odwołań.
    """
    try:
        model = Quest.model_validate(quest)
    except ValidationError as exc:
        raise AuthorError(f"Quest {quest.get('id', '?')!r} ma błędy: {_problems(exc)}") from exc
    if monster_ids is not None:
        unknown = sorted({m.id for step in model.steps for m in step.monsters} - monster_ids)
        if unknown:
            raise AuthorError(
                f"Quest {model.id!r}: nieznane potwory {unknown}. "
                "Dodaj je generatorem: python -m generator monster \"Nazwa\""
            )
    forbidden = find_forbidden(json.dumps(quest, ensure_ascii=False))
    if forbidden:
        raise AuthorError(
            f"Zamień {forbidden[0]!r} na „bramka lvl-owa” (odmienione w zdaniu, np. „przez bramkę lvl-ową”)."
        )
    return model


def check_boss(boss: dict, monster_ids: set[str], quest_steps: dict[str, int]) -> Boss:
    """Walidacja bossa: poprawne pola, istniejący potwór i questy, bez angielskich nazw."""
    try:
        model = Boss.model_validate(boss)
    except ValidationError as exc:
        raise AuthorError(f"Boss {boss.get('monster', '?')!r} ma błędy: {_problems(exc)}") from exc
    if model.monster not in monster_ids:
        raise AuthorError(f"Boss {model.monster!r}: nie ma takiego potwora w pliku.")
    unknown = sorted({r.quest for r in model.quests} - quest_steps.keys())
    if unknown:
        raise AuthorError(f"Boss {model.monster!r}: nieznane questy {unknown}.")
    for requirement in model.quests:
        if requirement.step is not None and requirement.step > quest_steps[requirement.quest]:
            raise AuthorError(
                f"Boss {model.monster!r}: quest {requirement.quest!r} ma tylko "
                f"{quest_steps[requirement.quest]} kroków, a wymaganie mówi o kroku {requirement.step}."
            )
    forbidden = find_forbidden(json.dumps(boss, ensure_ascii=False))
    if forbidden:
        raise AuthorError(
            f"Zamień {forbidden[0]!r} na „bramka lvl-owa” (odmienione w zdaniu, np. „przez bramkę lvl-ową”)."
        )
    return model


def check_hunt(hunt: dict, monster_ids: set[str]) -> Hunt:
    """Walidacja miejsca huntu: poprawne pola, znane potwory, bez angielskiej nazwy bramki w uwagach."""
    try:
        model = Hunt.model_validate(hunt)
    except ValidationError as exc:
        raise AuthorError(f"Hunt {hunt.get('id', '?')!r} ma błędy: {_problems(exc)}") from exc
    unknown = sorted(set(model.monster_ids()) - monster_ids)
    if unknown:
        raise AuthorError(f"Hunt {model.id!r}: nieznane potwory {unknown}.")
    # Tylko to, co pisze autor: opis z wiki jest po angielsku i może mieć oryginalną nazwę.
    forbidden = find_forbidden(json.dumps([model.notes, [p.label for p in model.route]], ensure_ascii=False))
    if forbidden:
        raise AuthorError(
            f"Zamień {forbidden[0]!r} na „bramka lvl-owa” (odmienione w zdaniu, np. „przez bramkę lvl-ową”)."
        )
    return model


def upsert_boss(data: dict, boss: dict) -> None:
    """Dodaje bossa albo podmienia tego z tym samym potworem. Lista posortowana po id potwora."""
    bosses = data.setdefault("bosses", [])
    for index, old in enumerate(bosses):
        if old.get("monster") == boss["monster"]:
            bosses[index] = boss
            return
    bosses.append(boss)
    bosses.sort(key=lambda b: b["monster"])


def save_data(data: dict, path: Path) -> None:
    """Sprawdza wszystkie questy, podbija data_version i zapisuje plik.

    Najpierw walidacja, potem zapis: na dysk nigdy nie trafi plik,
    który aplikacja by odrzuciła.
    """
    monster_ids: set[str] = set()
    for index, raw in enumerate(data.get("monsters", [])):
        try:
            monster = Monster.model_validate(raw)
        except ValidationError as exc:
            raise AuthorError(f"Potwór #{index} ma błędy: {_problems(exc)}") from exc
        # Aplikacja wzięłaby tylko pierwszego z duplikatów, więc nie zapisujemy takiego pliku.
        if monster.id in monster_ids:
            raise AuthorError(f"Potwór {monster.id!r} jest w pliku dwa razy.")
        monster_ids.add(monster.id)
    for quest in data["quests"]:
        check_quest(quest, monster_ids)
    quest_steps = {quest["id"]: len(quest.get("steps", [])) for quest in data["quests"]}
    boss_ids: set[str] = set()
    for boss in data.get("bosses", []):
        model = check_boss(boss, monster_ids, quest_steps)
        if model.monster in boss_ids:
            raise AuthorError(f"Boss {model.monster!r} jest w pliku dwa razy.")
        boss_ids.add(model.monster)
    hunt_ids: set[str] = set()
    for hunt in data.get("hunts", []):
        model = check_hunt(hunt, monster_ids)
        if model.id in hunt_ids:
            raise AuthorError(f"Hunt {model.id!r} jest w pliku dwa razy.")
        hunt_ids.add(model.id)
    # Plik z potworami wymaga nowszej aplikacji: starsza dostanie jasny komunikat.
    data["schema_version"] = max(data["schema_version"], SCHEMA_VERSION)
    data["data_version"] += 1
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    write_bytes_atomic(path, text.encode("utf-8"))


def upsert_monster(data: dict, monster: dict) -> None:
    """Dodaje potwora albo podmienia tego o tym samym id (np. po zmianie na wiki)."""
    monsters = data.setdefault("monsters", [])
    for index, old in enumerate(monsters):
        if old.get("id") == monster["id"]:
            monsters[index] = monster
            return
    monsters.append(monster)
    monsters.sort(key=lambda m: m["id"])


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
