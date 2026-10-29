"""Kalkulatory z zakładki „Narzędzia”: cena ze Store, podział lootu, stamina i skille. Bez Qt, żeby łatwo testować.

Store: potiony, runy, caski i kegi kosztują w Store Tibia Coins (TC), a TC kupuje się na Markecie
za gold. Gracz wpisuje cenę 1 TC, a my liczymy cenę paczki w gp i cenę jednej sztuki
(np. 125 Health Potion za 6 TC przy 1000 gp za TC: 6000 gp, czyli 48 gp za sztukę).

Party: gracz kopiuje w kliencie Party Hunt Analyzer (przycisk „Copy to clipboard”) i wkleja tekst.
Wygląda on mniej więcej tak (wcięcia to tabulatory albo spacje):

    Session data: From 2026-10-29, 10:00:00 to 2026-10-29, 11:00:00
    Session: 01:00h
    Loot Type: Market
    Loot: 1,200,000
    Supplies: 300,000
    Balance: 900,000
    Knight Jacek (Leader)
        Loot: 1,000,000
        Supplies: 100,000
        Balance: 900,000
        Damage: 2,000,000
        Healing: 10,000
    Druid Ola
        Loot: 200,000
        ...

Każdy gracz powinien skończyć z równą częścią całego balansu, więc ci „na plusie”
oddają nadwyżkę tym „na minusie” (komenda u bankiera: „transfer 100000 to Druid Ola”).
"""

import math
import re
from dataclasses import dataclass

# Mnożniki skrótów, których gracze używają przy cenach: 500k, 1.5kk.
_SUFFIXES = {"": 1, "k": 1_000, "kk": 1_000_000, "kkk": 1_000_000_000}
_AMOUNT = re.compile(r"^(-?)(\d+(?:[.,]\d+)?)\s*(k*)$")
# Linia gracza z wartością, np. „Loot: 1,000,000” albo „Balance: -5,000”.
_FIELD = re.compile(r"^(Loot|Supplies|Balance|Damage|Healing):\s*(-?[\d,.]+)\s*$", re.IGNORECASE)
LEADER_MARK = "(Leader)"
MAX_PLAYERS = 50  # zabezpieczenie przed wklejeniem czegoś zupełnie innego niż analyzer


def parse_gold(text: str) -> int | None:
    """Kwota wpisana przez gracza: „1,234,567”, „1.234.567”, „500k”, „1.5kk”. Zły tekst daje None."""
    raw = text.strip().lower().replace(" ", "")
    if not raw:
        return None
    # Bez skrótu przecinki i kropki to tylko separatory tysięcy (tak pokazuje je Tibia).
    # Przy „k” też, gdy po nich są dokładnie 3 cyfry: „1,500k” to 1,500,000, a „1.5kk” to 1,500,000.
    if not raw.endswith("k") or re.fullmatch(r"-?\d{1,3}([.,]\d{3})+k", raw):
        raw = raw.replace(",", "").replace(".", "")
    match = _AMOUNT.match(raw)
    if not match or match.group(3) not in _SUFFIXES:
        return None
    sign, number, suffix = match.groups()
    value = round(float(number.replace(",", ".")) * _SUFFIXES[suffix])
    return -value if sign else value


def format_gold(value: int) -> str:
    """Kwota jak w kliencie Tibii: 1,234,567."""
    return f"{value:,}"


@dataclass(frozen=True)
class PartyMember:
    name: str
    loot: int = 0
    supplies: int = 0
    balance: int = 0
    leader: bool = False


@dataclass(frozen=True)
class Transfer:
    sender: str
    receiver: str
    amount: int

    @property
    def command(self) -> str:
        # Dokładnie to, co gracz wpisuje u bankiera NPC (bez przecinków, inaczej NPC nie zrozumie).
        return f"transfer {self.amount} to {self.receiver}"


@dataclass(frozen=True)
class LootSplit:
    total: int  # balans całego party
    share: int  # ile powinien mieć każdy gracz
    transfers: list[Transfer]


def parse_party_analyzer(text: str) -> list[PartyMember]:
    """Gracze z tekstu Party Hunt Analyzera. Pola przed pierwszym graczem to podsumowanie party (pomijamy)."""
    members: list[dict] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        field = _FIELD.match(stripped)
        if field:
            if members:
                value = parse_gold(field.group(2))
                if value is not None:
                    members[-1][field.group(1).lower()] = value
            continue
        # Linie z dwukropkiem bez kwoty to nagłówki sesji (Session data, Loot Type itd.).
        if ":" in stripped:
            continue
        leader = stripped.endswith(LEADER_MARK)
        name = stripped.removesuffix(LEADER_MARK).strip()
        if name:
            members.append({"name": name, "leader": leader})
        if len(members) > MAX_PLAYERS:
            break
    result = []
    for m in members:
        # Gracz bez żadnej kwoty to raczej przypadkowa linia tekstu, a nie gracz.
        if not any(k in m for k in ("loot", "supplies", "balance")):
            continue
        loot, supplies = m.get("loot", 0), m.get("supplies", 0)
        balance = m.get("balance", loot - supplies)
        result.append(PartyMember(m["name"], loot, supplies, balance, m["leader"]))
    return result


def split_loot(members: list[PartyMember]) -> LootSplit:
    """Kto komu ile przelewa, żeby każdy miał równą część balansu (jak najmniej przelewów)."""
    if not members:
        return LootSplit(0, 0, [])
    total = sum(m.balance for m in members)
    # Dzielimy w dół do pełnego golda; reszta (najwyżej kilka gp) zostaje u tych, co płacą.
    share = total // len(members)
    payers = sorted(((m.balance - share, m.name) for m in members if m.balance > share), reverse=True)
    receivers = sorted(((share - m.balance, m.name) for m in members if m.balance < share), reverse=True)
    transfers = []
    # Zachłannie: największy dłużnik płaci największemu wierzycielowi, aż jeden z nich się wyzeruje.
    pi = ri = 0
    payers = [list(p) for p in payers]
    receivers = [list(r) for r in receivers]
    while pi < len(payers) and ri < len(receivers):
        amount = min(payers[pi][0], receivers[ri][0])
        if amount > 0:
            transfers.append(Transfer(payers[pi][1], receivers[ri][1], amount))
        payers[pi][0] -= amount
        receivers[ri][0] -= amount
        if payers[pi][0] == 0:
            pi += 1
        if receivers[ri][0] == 0:
            ri += 1
    return LootSplit(total, share, transfers)


# --- Stamina (zasady z TibiaWiki, strona „Stamina”) ---
MAX_STAMINA = 42 * 60  # minuty
BONUS_STAMINA = 39 * 60  # od 39:00 w górę są „happy hours” (+50% expa dla premium)
LOW_STAMINA = 14 * 60  # poniżej 14:00 połowa expa i brak lootu
OFFLINE_DELAY = 10  # regeneracja rusza dopiero po 10 minutach offline
MINUTES_PER_STAMINA = 3  # 3 minuty offline = 1 minuta staminy
MINUTES_PER_BONUS_STAMINA = 6  # w godzinach bonusowych dwa razy wolniej


def parse_stamina(text: str) -> int | None:
    """„39:30” albo „39” -> minuty. Poza zakresem 0–42:00 albo zły tekst daje None."""
    match = re.fullmatch(r"\s*(\d{1,2})(?::(\d{1,2}))?\s*", text)
    if not match:
        return None
    hours, minutes = int(match.group(1)), int(match.group(2) or 0)
    total = hours * 60 + minutes
    if minutes >= 60 or total > MAX_STAMINA:
        return None
    return total


def format_minutes(minutes: int) -> str:
    """Minuty jako „hh:mm” (jak stamina w kliencie)."""
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def offline_minutes_needed(current: int, target: int = MAX_STAMINA) -> int:
    """Ile minut trzeba być wylogowanym, żeby stamina urosła z `current` do `target` (w minutach)."""
    target = min(target, MAX_STAMINA)
    if current >= target:
        return 0
    normal = max(0, min(target, BONUS_STAMINA) - current)
    bonus = max(0, target - max(current, BONUS_STAMINA))
    return OFFLINE_DELAY + normal * MINUTES_PER_STAMINA + bonus * MINUTES_PER_BONUS_STAMINA


# --- Skille (wzory z TibiaWiki, strony „Formulae” i „Exercise Weapons”) ---
# Punkty na kolejny poziom: A * b^(skill - c). A zależy od skilla, b od profesji, c to skill startowy.
SKILL_CONSTANT = {"magic": 1600, "melee": 50, "fist": 50, "distance": 30, "shielding": 100}
SKILL_OFFSET = {"magic": 0, "melee": 10, "fist": 10, "distance": 10, "shielding": 10}
VOCATION_CONSTANT = {
    "knight": {"magic": 3.0, "melee": 1.1, "fist": 1.1, "distance": 1.4, "shielding": 1.1},
    "paladin": {"magic": 1.4, "melee": 1.2, "fist": 1.2, "distance": 1.1, "shielding": 1.1},
    "sorcerer": {"magic": 1.1, "melee": 2.0, "fist": 1.5, "distance": 2.0, "shielding": 1.5},
    "druid": {"magic": 1.1, "melee": 1.8, "fist": 1.5, "distance": 1.8, "shielding": 1.5},
    "monk": {"magic": 1.25, "melee": 1.4, "fist": 1.1, "distance": 1.5, "shielding": 1.15},
}
# Ile punktów skilla daje jeden ładunek exercise weapon (miecz/topór/maczuga/wraps, łuk, różdżka, tarcza).
POINTS_PER_CHARGE = {"magic": 600, "melee": 7.2, "fist": 7.2, "distance": 4.32, "shielding": 14.4}
SECONDS_PER_CHARGE = 2
EXPERT_DUMMY_BONUS = 1.1  # dummy w domu (Demon/Ferumbras/Monk Exercise Dummy) daje +10%


@dataclass(frozen=True)
class ExerciseWeapon:
    name: str
    charges: int
    gold: int
    coins: int


EXERCISE_WEAPONS = (
    ExerciseWeapon("Exercise", 500, 347_222, 25),
    ExerciseWeapon("Durable", 1_800, 1_250_000, 90),
    ExerciseWeapon("Lasting", 14_400, 10_000_000, 720),
)


def points_for_next(skill: str, vocation: str, level: int) -> float:
    """Punkty potrzebne z poziomu `level` na `level + 1`."""
    b = VOCATION_CONSTANT[vocation][skill]
    return SKILL_CONSTANT[skill] * b ** (level - SKILL_OFFSET[skill])


def skill_points_needed(skill: str, vocation: str, current: int, percent_done: float, target: int) -> float:
    """Punkty od obecnego poziomu (z `percent_done` % paska) do `target`."""
    if target <= current:
        return 0.0
    left = points_for_next(skill, vocation, current) * (1 - min(max(percent_done, 0), 100) / 100)
    return left + sum(points_for_next(skill, vocation, level) for level in range(current + 1, target))


@dataclass(frozen=True)
class WeaponPlan:
    weapon: ExerciseWeapon
    count: int  # ile sztuk kupić (w górę, bo nie kupi się pół broni)
    gold: int
    coins: int


@dataclass(frozen=True)
class SkillPlan:
    points: float
    charges: int
    seconds: int  # czas bicia w dummy
    weapons: list[WeaponPlan]


def skill_plan(
    skill: str, vocation: str, current: int, percent_done: float, target: int, expert_dummy: bool = False,
    double_skill: bool = False,
) -> SkillPlan:
    """Ile ładunków i broni treningowych trzeba, żeby dobić skill do `target`."""
    points = skill_points_needed(skill, vocation, current, percent_done, target)
    per_charge = POINTS_PER_CHARGE[skill]
    if expert_dummy:
        per_charge *= EXPERT_DUMMY_BONUS
    if double_skill:
        per_charge *= 2
    charges = math.ceil(points / per_charge) if points > 0 else 0
    weapons = []
    for weapon in EXERCISE_WEAPONS:
        count = math.ceil(charges / weapon.charges)
        weapons.append(WeaponPlan(weapon, count, count * weapon.gold, count * weapon.coins))
    return SkillPlan(points, charges, charges * SECONDS_PER_CHARGE, weapons)


# --- Store (ceny z TibiaWiki, strony „Store/Potions”, „Store/Runes”, „Store/Casks”, „Store/Kegs”) ---
STORE_CATEGORIES = ("potions", "kegs", "casks", "runes", "other")
CASK_FILLS = 1000  # cask (do domu) napełnia 1000 pustych fiolek
KEG_FILLS = 500  # keg (do plecaka) napełnia 500 fiolek


@dataclass(frozen=True)
class StoreOffer:
    name: str  # nazwa z gry (tak też szukamy ceny u NPC)
    amount: int  # ile sztuk dostajesz (dla casku i kegu: ile potionów napełnia)
    coins: int
    category: str
    unit: str = ""  # przedmiot liczony „za sztukę”, gdy inny niż name (cask -> potion)

    @property
    def unit_name(self) -> str:
        return self.unit or self.name


def _potion_packs(name: str, small: tuple[int, int], big: tuple[int, int]) -> list[StoreOffer]:
    # Każdy potion jest w Store w dwóch paczkach: mniejszej i większej (np. 100 i 250 sztuk).
    return [StoreOffer(name, small[0], small[1], "potions"), StoreOffer(name, big[0], big[1], "potions")]


def _refill(kind: str, fills: int, category: str, prices: dict[str, int]) -> list[StoreOffer]:
    return [
        StoreOffer(f"{potion.replace(' Potion', '')} {kind}", fills, coins, category, unit=potion)
        for potion, coins in prices.items()
    ]


STORE_OFFERS: tuple[StoreOffer, ...] = (
    *_potion_packs("Health Potion", (125, 6), (300, 11)),
    *_potion_packs("Strong Health Potion", (100, 10), (250, 21)),
    *_potion_packs("Great Health Potion", (100, 18), (250, 41)),
    *_potion_packs("Ultimate Health Potion", (100, 29), (250, 68)),
    *_potion_packs("Supreme Health Potion", (100, 47), (250, 113)),
    *_potion_packs("Mana Potion", (125, 6), (300, 12)),
    *_potion_packs("Strong Mana Potion", (100, 7), (250, 17)),
    *_potion_packs("Great Mana Potion", (100, 11), (250, 26)),
    *_potion_packs("Ultimate Mana Potion", (100, 33), (250, 79)),
    *_potion_packs("Great Spirit Potion", (100, 18), (250, 41)),
    *_potion_packs("Ultimate Spirit Potion", (100, 33), (250, 79)),
    *_refill("Keg", KEG_FILLS, "kegs", {
        "Health Potion": 26, "Strong Health Potion": 53, "Great Health Potion": 103,
        "Ultimate Health Potion": 175, "Supreme Health Potion": 288, "Mana Potion": 26,
        "Strong Mana Potion": 43, "Great Mana Potion": 66, "Ultimate Mana Potion": 202,
        "Great Spirit Potion": 105, "Ultimate Spirit Potion": 202,
    }),
    *_refill("Cask", CASK_FILLS, "casks", {
        "Health Potion": 5, "Strong Health Potion": 11, "Great Health Potion": 22,
        "Ultimate Health Potion": 36, "Supreme Health Potion": 59, "Mana Potion": 5,
        "Strong Mana Potion": 9, "Great Mana Potion": 14, "Ultimate Mana Potion": 42,
        "Great Spirit Potion": 22, "Ultimate Spirit Potion": 42,
    }),
    *(StoreOffer(f"{name} Rune", 250, coins, "runes") for name, coins in (
        ("Animate Dead", 75), ("Avalanche", 12), ("Chameleon", 42), ("Convince Creature", 16),
        ("Cure Poison", 13), ("Disintegrate", 5), ("Energy Bomb", 40), ("Energy Field", 8),
        ("Energy Wall", 17), ("Explosion", 6), ("Fireball", 6), ("Fire Bomb", 29), ("Fire Field", 6),
        ("Fire Wall", 12), ("Great Fireball", 12), ("Icicle", 6), ("Intense Healing", 19),
        ("Magic Wall", 23), ("Paralyse", 140), ("Poison Bomb", 17), ("Poison Wall", 10),
        ("Soulfire", 9), ("Stone Shower", 7), ("Sudden Death", 28), ("Thunderstorm", 9),
        ("Ultimate Healing", 35), ("Wild Growth", 32),
    )),
    # Exercise weapons: każdy rodzaj (miecz, łuk, różdżka…) kosztuje tyle samo, więc jeden wiersz na wielkość.
    *(StoreOffer(f"{w.name} Exercise Weapon" if w.name != "Exercise" else "Exercise Weapon", 1, w.coins, "other")
      for w in EXERCISE_WEAPONS),
)
# Ceny broni treningowych u NPC (na wiki nie ma jednego przedmiotu „Exercise Weapon”).
NPC_PRICE_OVERRIDES = {
    ("Exercise Weapon" if w.name == "Exercise" else f"{w.name} Exercise Weapon"): w.gold for w in EXERCISE_WEAPONS
}


@dataclass(frozen=True)
class StoreRow:
    offer: StoreOffer
    gold: int  # cena całej paczki w gp
    per_unit: float  # gp za jedną sztukę
    npc_per_unit: int | None  # najtańsza cena za sztukę u NPC (None = NPC tego nie sprzedaje)

    @property
    def cheaper_in_store(self) -> bool | None:
        if self.npc_per_unit is None:
            return None
        return self.per_unit < self.npc_per_unit


def store_rows(coin_gold: int, npc_prices: dict[str, int], category: str | None = None) -> list[StoreRow]:
    """Oferty ze Store przeliczone na gp przy cenie 1 TC = `coin_gold` (category None = wszystkie)."""
    rows = []
    for offer in STORE_OFFERS:
        if category is not None and offer.category != category:
            continue
        gold = offer.coins * coin_gold
        name = offer.unit_name
        # Runy, które są też czarem, mają na wiki dopisek „(Item)”, np. „Cure Poison Rune (Item)”.
        npc = NPC_PRICE_OVERRIDES.get(name, npc_prices.get(name, npc_prices.get(f"{name} (Item)")))
        rows.append(StoreRow(offer, gold, gold / offer.amount, npc))
    return rows
