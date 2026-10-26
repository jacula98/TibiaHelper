"""Bezpieczne wczytywanie data/quests.json.

Zasada: błędne dane nie mogą wywalić aplikacji.
- uszkodzony plik / zły nagłówek -> QuestFileError (wywołujący może wtedy
  sięgnąć po inną kopię, np. wbudowaną w .exe),
- pojedynczy błędny quest -> pomijamy go i zapisujemy błąd w LoadResult.errors.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from .models import SCHEMA_VERSION, Item, Monster, Npc, Quest, QuestFileHeader

log = logging.getLogger(__name__)


class QuestFileError(Exception):
    """Plik nie nadaje się do użycia w całości."""


@dataclass(frozen=True)
class LoadResult:
    data_version: int
    quests: list[Quest]
    errors: list[str] = field(default_factory=list)
    # Potwory po id, do obrazków i dymków w krokach.
    monsters: dict[str, Monster] = field(default_factory=dict)
    # Przedmioty i NPC po nazwie zapisanej małymi literami (loot na wiki bywa pisany różnie).
    items: dict[str, Item] = field(default_factory=dict)
    npcs: dict[str, Npc] = field(default_factory=dict)

    @property
    def visible_quests(self) -> list[Quest]:
        """Tylko questy przejrzane przez autora (status 'reviewed')."""
        return [q for q in self.quests if q.is_visible]


def parse_quest_data(raw: object) -> LoadResult:
    """Waliduje już sparsowany JSON. Oddzielone od odczytu pliku, żeby łatwo testować."""
    try:
        header = QuestFileHeader.model_validate(raw)
    except ValidationError as exc:
        raise QuestFileError(f"Nieprawidłowy nagłówek pliku: {exc}") from exc

    if header.schema_version > SCHEMA_VERSION:
        raise QuestFileError(
            f"Plik ma schema_version {header.schema_version}, a ta wersja aplikacji "
            f"obsługuje najwyżej {SCHEMA_VERSION}. Zaktualizuj aplikację."
        )

    errors: list[str] = []
    monsters = _parse_monsters(header.monsters, errors)

    quests: list[Quest] = []
    seen_ids: set[str] = set()

    for index, raw_quest in enumerate(header.quests):
        if not isinstance(raw_quest, dict):
            errors.append(f"quest #{index}: to nie jest obiekt JSON, pominięto")
            continue
        label = f"quest #{index} ({raw_quest.get('id', '?')})"
        try:
            quest = Quest.model_validate(raw_quest)
        except ValidationError as exc:
            errors.append(f"{label}: {exc}")
            continue
        # Duplikat id pomieszałby zapis postępu, więc zostawiamy pierwszy.
        if quest.id in seen_ids:
            errors.append(f"{label}: zduplikowane id, pominięto")
            continue
        seen_ids.add(quest.id)
        quests.append(quest)
        # Nieznany potwór to tylko brak obrazka, więc quest zostaje, ale autor dowie się z logu.
        unknown = {m.id for step in quest.steps for m in step.monsters} - monsters.keys()
        if unknown:
            errors.append(f"{label}: nieznane potwory {sorted(unknown)}, będą bez obrazka")

    items = _parse_named(header.items, Item, "przedmiot", errors)
    npcs = _parse_named(header.npcs, Npc, "NPC", errors)

    for message in errors:
        log.warning(message)

    return LoadResult(
        data_version=header.data_version,
        quests=quests,
        errors=errors,
        monsters=monsters,
        items=items,
        npcs=npcs,
    )


def _parse_named(raw_list: list, model: type, what: str, errors: list[str]) -> dict:
    """Wpisy z polem name (przedmioty, NPC) po nazwie małymi literami. Błędny wpis pomijamy."""
    result = {}
    for index, raw in enumerate(raw_list):
        try:
            entry = model.model_validate(raw)
        except ValidationError as exc:
            errors.append(f"{what} #{index}: {exc}")
            continue
        # Kilku NPC o tym samym imieniu (np. w różnych miastach): zostaje pierwszy.
        result.setdefault(entry.name.lower(), entry)
    return result


def _parse_monsters(raw_monsters: list, errors: list[str]) -> dict[str, Monster]:
    monsters: dict[str, Monster] = {}
    for index, raw in enumerate(raw_monsters):
        try:
            monster = Monster.model_validate(raw)
        except ValidationError as exc:
            errors.append(f"potwór #{index}: {exc}")
            continue
        if monster.id in monsters:
            errors.append(f"potwór #{index} ({monster.id}): zduplikowane id, pominięto")
            continue
        monsters[monster.id] = monster
    return monsters


def load_quest_file(path: Path) -> LoadResult:
    """Wczytuje i waliduje plik questów z dysku."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise QuestFileError(f"Nie można odczytać {path}: {exc}") from exc
    return parse_quest_data(raw)
