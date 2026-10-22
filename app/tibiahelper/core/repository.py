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

from .models import SCHEMA_VERSION, Quest, QuestFileHeader

log = logging.getLogger(__name__)


class QuestFileError(Exception):
    """Plik nie nadaje się do użycia w całości."""


@dataclass(frozen=True)
class LoadResult:
    data_version: int
    quests: list[Quest]
    errors: list[str] = field(default_factory=list)

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

    quests: list[Quest] = []
    errors: list[str] = []
    seen_ids: set[str] = set()

    for index, raw_quest in enumerate(header.quests):
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

    for message in errors:
        log.warning(message)

    return LoadResult(data_version=header.data_version, quests=quests, errors=errors)


def load_quest_file(path: Path) -> LoadResult:
    """Wczytuje i waliduje plik questów z dysku."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise QuestFileError(f"Nie można odczytać {path}: {exc}") from exc
    return parse_quest_data(raw)
