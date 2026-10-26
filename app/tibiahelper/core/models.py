"""Model danych questów (data/quests.json).

Ten moduł jest wspólny dla aplikacji i generatora, więc oba sprawdzają
dane tą samą walidacją. Nie importuje niczego z PySide6.
"""

from datetime import datetime
from typing import Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Najnowsza wersja formatu pliku, którą ta wersja aplikacji rozumie.
# Podbijamy ją tylko przy zmianach niekompatybilnych wstecz.
# 2: punkty na mapie w krokach (Step.markers), 3: potwory (Monster, Step.monsters),
# 4: szczegóły potworów (loot, umiejętności, miejsca) do zakładki „Potwory”,
# 5-6: obrazki przedmiotów i NPC, 7: przedmioty (Item) i NPC (Npc) do zakładki „Przedmioty”
SCHEMA_VERSION = 7

WIKI_URL_PREFIX = "https://tibia.fandom.com/wiki/"

QuestStatus = Literal["draft", "reviewed"]

# Zasięg mapy Tibii (zgodny z mapami tibiamaps: 2560 x 2048 kratek, piętra 0-15).
MAP_X_MIN, MAP_X_MAX = 31744, 31744 + 2560 - 1
MAP_Y_MIN, MAP_Y_MAX = 30976, 30976 + 2048 - 1
GROUND_FLOOR = 7  # w Tibii z=7 to parter, mniejsze z są wyżej, większe pod ziemią

MarkerKind = Literal["npc", "place", "passage", "use"]

# Żywioły obrażeń w Tibii, w kolejności jak na TibiaWiki.
Element = Literal["physical", "earth", "fire", "energy", "ice", "holy", "death"]
ELEMENTS: tuple[str, ...] = get_args(Element)
# Obrazki potworów to pliki z TibiaWiki (grafiki © CipSoft). Aplikacja pobiera je
# tylko z tego serwera, żeby adres w danych nie mógł prowadzić gdziekolwiek.
SPRITE_URL_PREFIX = "https://static.wikia.nocookie.net/tibia/images/"

# Rzadkość dropu tak, jak zapisuje ją TibiaWiki.
Rarity = Literal["always", "common", "uncommon", "semi-rare", "rare", "very rare"]


class _Model(BaseModel):
    # extra="forbid": literówka w nazwie pola (np. "npcs") to błąd, a nie cicho
    # ignorowane pole. frozen=True: obiekty są tylko do odczytu.
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class MapPoint(_Model):
    """Punkt na mapie Tibii, pokazywany po kliknięciu pinezki przy kroku."""

    x: int = Field(ge=MAP_X_MIN, le=MAP_X_MAX)
    y: int = Field(ge=MAP_Y_MIN, le=MAP_Y_MAX)
    z: int = Field(ge=0, le=15)
    label: str = Field(min_length=1)
    # npc / place (miejsce) / passage (przejście, np. dziura, drabina) / use (coś do użycia)
    kind: MarkerKind = "place"
    # Fragment tekstu kroku, za którym stoi pinezka. Brak = pinezka na końcu tekstu.
    anchor: str | None = None


class LootItem(_Model):
    name: str = Field(min_length=1)
    amount: str | None = None  # np. "0-10"; None = 1 sztuka
    rarity: Rarity | None = None


def _check_image(url: str | None) -> None:
    if url is not None and not url.startswith(SPRITE_URL_PREFIX):
        raise ValueError(f"image_url musi zaczynać się od {SPRITE_URL_PREFIX}")


class Npc(_Model):
    """NPC z TibiaWiki: gdzie stoi (pinezki w krokach, „komu sprzedać”) i jak wygląda."""

    name: str = Field(min_length=1)
    x: int = Field(ge=MAP_X_MIN, le=MAP_X_MAX)
    y: int = Field(ge=MAP_Y_MIN, le=MAP_Y_MAX)
    z: int = Field(ge=0, le=15)
    city: str | None = None
    image_url: str | None = None

    @model_validator(mode="after")
    def _check_url(self) -> "Npc":
        _check_image(self.image_url)
        return self

    @property
    def title(self) -> str:
        """Tekst na liście: imię i miasto (NPC o tym samym imieniu bywa kilku)."""
        return f"{self.name} ({self.city})" if self.city else self.name


class Trade(_Model):
    """NPC, który kupuje albo sprzedaje przedmiot. price None = cena jak w polu przedmiotu."""

    npc: str = Field(min_length=1)
    price: int | None = Field(default=None, ge=0)


class Item(_Model):
    """Przedmiot z TibiaWiki do zakładki „Przedmioty”."""

    name: str = Field(min_length=1)
    source_url: str
    image_url: str | None = None
    category: str | None = None
    weight: float | None = Field(default=None, ge=0)
    # Za ile NPC kupuje od gracza (value) i za ile sprzedaje graczowi (price), w gp.
    value: int | None = Field(default=None, ge=0)
    price: int | None = Field(default=None, ge=0)
    sell_to: list[Trade] = Field(default_factory=list)  # tym NPC gracz może sprzedać
    buy_from: list[Trade] = Field(default_factory=list)  # od tych NPC gracz może kupić

    @model_validator(mode="after")
    def _check_urls(self) -> "Item":
        _check_image(self.image_url)
        if not self.source_url.startswith(WIKI_URL_PREFIX):
            raise ValueError(f"source_url musi zaczynać się od {WIKI_URL_PREFIX}")
        return self


class Monster(_Model):
    """Potwór z TibiaWiki: obrazek, dymek (HP, exp, słabości) i strona w zakładce „Potwory”."""

    id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    name: str = Field(min_length=1)
    hp: int = Field(ge=0)
    exp: int = Field(ge=0)
    # Obrażenia w % względem normalnych, tylko te różne od 100% (np. holy 125 = słaby na holy).
    elements: dict[Element, int] = Field(default_factory=dict)
    # None = na wiki nie ma obrazka.
    image_url: str | None = None
    source_url: str
    wiki_revision: int | None = Field(default=None, ge=1)
    # Szczegóły do strony potwora. Teksty są z wiki, po angielsku.
    armor: int | None = Field(default=None, ge=0)
    speed: int | None = Field(default=None, ge=0)
    boss: bool = False
    bestiary_class: str | None = None
    bestiary_level: str | None = None
    abilities: list[str] = Field(default_factory=list)
    loot: list[LootItem] = Field(default_factory=list)
    location: str | None = None

    @model_validator(mode="after")
    def _check_urls(self) -> "Monster":
        if self.image_url is not None and not self.image_url.startswith(SPRITE_URL_PREFIX):
            raise ValueError(f"image_url musi zaczynać się od {SPRITE_URL_PREFIX}")
        if not self.source_url.startswith(WIKI_URL_PREFIX):
            raise ValueError(f"source_url musi zaczynać się od {WIKI_URL_PREFIX}")
        return self


class StepMonster(_Model):
    """Potwór wspomniany w kroku: obrazek stoi za fragmentem `anchor` (jak pinezka)."""

    id: str  # id z listy "monsters" w pliku
    count: int | None = Field(default=None, ge=1)  # None = nie wiadomo ile
    anchor: str | None = None


class Step(_Model):
    text: str = Field(min_length=1)
    location: str | None = None
    npc: str | None = None
    items: list[str] = Field(default_factory=list)
    markers: list[MapPoint] = Field(default_factory=list)
    monsters: list[StepMonster] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_anchors(self) -> "Step":
        # Literówka w anchor schowałaby pinezkę/obrazek, więc łapiemy ją już przy walidacji.
        for item in (*self.markers, *self.monsters):
            if item.anchor is not None and item.anchor not in self.text:
                raise ValueError(f"anchor {item.anchor!r} nie występuje w tekście kroku")
        return self


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

    def monster_counts(self) -> list[tuple[str, int | None]]:
        """Potwory z całego questa do sekcji „Potwory”: (id, łączna liczba).

        Liczba jest sumą z kroków; gdy choć w jednym kroku jej nie podano,
        zwracamy None, bo suma byłaby myląca.
        """
        totals: dict[str, int | None] = {}
        for step in self.steps:
            for monster in step.monsters:
                if monster.id not in totals:
                    totals[monster.id] = monster.count
                elif totals[monster.id] is None or monster.count is None:
                    totals[monster.id] = None
                else:
                    totals[monster.id] += monster.count
        return list(totals.items())


class QuestFileHeader(_Model):
    """Nagłówek pliku. Questy celowo są tu surowe (list[Any]).

    Każdy quest walidujemy osobno w repository.py, żeby jeden błędny quest
    nie unieważniał całego pliku.
    """

    schema_version: int = Field(ge=1)
    # Rośnie przy każdej publikacji danych; updater porównuje ją z GitHubem.
    data_version: int = Field(ge=1)
    # Też surowe: błędny potwór nie może zablokować wszystkich questów.
    monsters: list[Any] = Field(default_factory=list)
    # Przedmioty i NPC: też surowe, każdy wpis sprawdzany osobno w repository.py.
    items: list[Any] = Field(default_factory=list)
    npcs: list[Any] = Field(default_factory=list)
    quests: list[Any]
