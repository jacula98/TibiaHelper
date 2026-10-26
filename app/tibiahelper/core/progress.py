"""Zapis postępu gracza: które kroki questa są odhaczone.

Plik JSON w %APPDATA%/TibiaHelper/progress.json:
    {"version": 1, "quests": {"annihilator-quest": [0, 2]}}
Kroki zapisujemy po indeksie (od 0). Kluczem jest id questa, dlatego id
nie może się zmieniać po publikacji.
"""

import json
import logging
import os
from pathlib import Path

from .models import Quest

log = logging.getLogger(__name__)

PROGRESS_VERSION = 1


class ProgressStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._done: dict[str, set[int]] = self._load()

    def done_steps(self, quest_id: str) -> set[int]:
        # Zwracamy kopię, żeby nikt nie zmienił stanu z pominięciem zapisu.
        return set(self._done.get(quest_id, set()))

    def count_done(self, quest: Quest) -> int:
        """Liczba odhaczonych kroków, które nadal istnieją w queście.

        Jeśli autor usunie kroki, stare indeksy spoza zakresu są pomijane.
        """
        return sum(1 for i in self._done.get(quest.id, set()) if i < len(quest.steps))

    def set_step(self, quest_id: str, step_index: int, done: bool) -> None:
        steps = self._done.setdefault(quest_id, set())
        if done:
            steps.add(step_index)
        else:
            steps.discard(step_index)
        if not steps:
            del self._done[quest_id]
        self._save()

    def reset_quest(self, quest_id: str) -> None:
        if self._done.pop(quest_id, None) is not None:
            self._save()

    def _load(self) -> dict[str, set[int]]:
        if not self._path.exists():
            return {}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            return {
                str(quest_id): {int(i) for i in steps if int(i) >= 0}
                for quest_id, steps in raw["quests"].items()
            }
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            # Uszkodzony plik nie może zablokować aplikacji. Odkładamy go na bok
            # (a nie kasujemy), żeby dało się go jeszcze ręcznie odzyskać.
            log.warning("Nie można odczytać postępu z %s: %s", self._path, exc)
            self._move_aside()
            return {}

    def _move_aside(self) -> None:
        try:
            os.replace(self._path, self._path.with_suffix(".json.corrupt"))
        except OSError as exc:
            log.warning("Nie można odłożyć uszkodzonego pliku postępu: %s", exc)

    def _save(self) -> None:
        data = {
            "version": PROGRESS_VERSION,
            "quests": {qid: sorted(steps) for qid, steps in sorted(self._done.items())},
        }
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            # Zapis atomowy: najpierw plik tymczasowy, potem podmiana. Gdy komputer
            # wyłączy się w trakcie zapisu, zostaje stary plik, a nie urwany JSON.
            tmp = self._path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, self._path)
        except OSError as exc:
            # Brak zapisu to nie powód do zamknięcia okna; postęp zostaje w pamięci.
            log.error("Nie można zapisać postępu do %s: %s", self._path, exc)
