"""Model danych questów (data/quests.json).

Ten moduł jest wspólny dla aplikacji i generatora, więc oba sprawdzają
dane tą samą walidacją. Nie importuje niczego z PySide6.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Najnowsza wersja formatu pliku, którą ta wersja aplikacji rozumie.
# Podbijamy ją tylko przy zmianach niekompatybilnych wstecz.
SCHEMA_VERSION = 1

WIKI_URL_PREFIX = "https://tibia.fandom.com/wiki/"

QuestStatus = Literal["draft", "reviewed"]


class _Model(BaseModel):
    # extra="forbid": literówka w nazwie pola (np. "npcs") to błąd, a nie cicho
    # ignorowane pole. frozen=True: obiekty są tylko do odczytu.
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class Step(_Model):
    text: str = Field(min_length=1)
    location: str | None = None
    npc: str | None = None
    items: list[str] = Field(default_factory=list)


class Quest(_Model):
    # id w stylu "annihilator-quest": służy jako klucz zapisu postępu,
    # więc nie może się zmieniać po publikacji questa.
    id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    name: str = Field(min_length=1)
    min_level: int = Field(ge=0)
    premium: bool
    source_url: str
    # None = jeszcze nie pobrano z wiki (np. quest wpisany ręcznie).
    wiki_revision: int | None = Field(default=None, ge=1)
    status: QuestStatus = "draft"
    reviewed_at: datetime | None = None
    # Ustawiane przez generator, gdy strona na wiki zmieniła się po przeglądzie.
    # Quest dalej jest widoczny dla graczy, a autor wie, co przejrzeć.
    needs_review: bool = False
    steps: list[Step] = Field(min_length=1)
    required_items: list[str] = Field(default_factory=list)
    rewards: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_consistency(self) -> "Quest":
        # Link do źródła jest wymagany przez licencję CC BY-SA, więc pilnujemy,
        # żeby faktycznie prowadził do TibiaWiki.
        if not self.source_url.startswith(WIKI_URL_PREFIX):
            raise ValueError(f"source_url musi zaczynać się od {WIKI_URL_PREFIX}")
        if self.status == "reviewed":
            if self.reviewed_at is None:
                raise ValueError("quest 'reviewed' musi mieć reviewed_at")
            if self.wiki_revision is None:
                raise ValueError("quest 'reviewed' musi mieć wiki_revision")
        return self

    @property
    def is_visible(self) -> bool:
        """Czy quest ma być pokazany graczom."""
        return self.status == "reviewed"


class QuestFileHeader(_Model):
    """Nagłówek pliku. Questy celowo są tu surowe (list[dict]).

    Każdy quest walidujemy osobno w repository.py, żeby jeden błędny quest
    nie unieważniał całego pliku.
    """

    schema_version: int = Field(ge=1)
    # Rośnie przy każdej publikacji danych; updater porównuje ją z GitHubem.
    data_version: int = Field(ge=1)
    quests: list[dict]
