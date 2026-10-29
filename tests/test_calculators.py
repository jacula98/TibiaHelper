"""Testy kalkulatorów z zakładki „Narzędzia”."""

import pytest

from tibiahelper.core.calculators import (
    PartyMember,
    format_gold,
    format_minutes,
    offline_minutes_needed,
    parse_gold,
    parse_party_analyzer,
    parse_stamina,
    skill_plan,
    skill_points_needed,
    split_loot,
    store_rows,
)
from tibiahelper.core.items import cheapest_buy_price
from tibiahelper.core.models import Item, Trade

ANALYZER = """Session data: From 2026-10-29, 10:00:00 to 2026-10-29, 11:00:00
Session: 01:00h
Loot Type: Market
Loot: 1,500,000
Supplies: 600,000
Balance: 900,000
Knight Jacek (Leader)
\tLoot: 1,200,000
\tSupplies: 200,000
\tBalance: 1,000,000
\tDamage: 2,000,000
\tHealing: 10,000
Druid Ola
\tLoot: 300,000
\tSupplies: 250,000
\tBalance: 50,000
\tDamage: 500,000
\tHealing: 900,000
Paladin Bob
    Loot: 0
    Supplies: 150,000
    Balance: -150,000
    Damage: 1,000,000
    Healing: 0
"""


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("1,234,567", 1_234_567),
        ("1.234.567", 1_234_567),
        ("500k", 500_000),
        ("1.5kk", 1_500_000),
        ("1,500k", 1_500_000),
        ("2.5k", 2_500),
        ("1,5kk", 1_500_000),
        ("-12,345", -12_345),
        (" 42 ", 42),
        ("", None),
        ("abc", None),
        ("5kkkk", None),
    ],
)
def test_parse_gold(text, value):
    assert parse_gold(text) == value


def test_format_gold():
    assert format_gold(1_234_567) == "1,234,567"
    assert format_gold(-5_000) == "-5,000"


def test_store_rows_example_from_jacek():
    # 1 TC = 1000 gp, 125 Health Potion za 6 TC: 6000 gp, czyli 48 gp za sztukę.
    row = next(r for r in store_rows(1000, {}) if r.offer.name == "Health Potion" and r.offer.amount == 125)
    assert row.gold == 6000
    assert row.per_unit == 48
    assert row.npc_per_unit is None and row.cheaper_in_store is None


def test_store_rows_filter_and_npc_comparison():
    rows = store_rows(1000, {"Health Potion": 50, "Cure Poison Rune (Item)": 40}, "casks")
    assert {r.offer.category for r in rows} == {"casks"}
    cask = next(r for r in rows if r.offer.name == "Health Cask")
    # Cask napełnia 1000 potionów za 5 TC: 5 gp za potion, a NPC chce 50 gp.
    assert cask.per_unit == 5 and cask.npc_per_unit == 50 and cask.cheaper_in_store
    rune = next(r for r in store_rows(1000, {"Cure Poison Rune (Item)": 40}, "runes") if r.offer.name == "Cure Poison Rune")
    assert rune.npc_per_unit == 40 and rune.cheaper_in_store is False


def test_store_exercise_weapons_use_npc_price():
    lasting = next(r for r in store_rows(10_000, {}, "other") if r.offer.name == "Lasting Exercise Weapon")
    assert lasting.gold == 7_200_000 and lasting.npc_per_unit == 10_000_000


def test_cheapest_buy_price():
    item = Item(
        name="Health Potion", source_url="https://tibia.fandom.com/wiki/Health_Potion", price=50,
        buy_from=[Trade(npc="A"), Trade(npc="B", price=45)],
    )
    assert cheapest_buy_price(item) == 45
    assert cheapest_buy_price(Item(name="X", source_url="https://tibia.fandom.com/wiki/X")) is None


def test_parse_party_analyzer():
    members = parse_party_analyzer(ANALYZER)
    assert [m.name for m in members] == ["Knight Jacek", "Druid Ola", "Paladin Bob"]
    assert members[0].leader and not members[1].leader
    assert members[2].balance == -150_000
    assert members[1].loot == 300_000


def test_parse_ignores_random_text():
    assert parse_party_analyzer("cześć\njak leci?") == []


def test_missing_balance_is_loot_minus_supplies():
    members = parse_party_analyzer("Ola\n Loot: 100\n Supplies: 30\n")
    assert members[0].balance == 70


def test_split_loot_everyone_ends_equal():
    members = parse_party_analyzer(ANALYZER)
    split = split_loot(members)
    assert split.total == 900_000
    assert split.share == 300_000
    after = {m.name: m.balance for m in members}
    for t in split.transfers:
        after[t.sender] -= t.amount
        after[t.receiver] += t.amount
    assert set(after.values()) == {300_000}
    assert all(t.sender == "Knight Jacek" for t in split.transfers)


def test_split_loot_remainder_stays_with_payer():
    split = split_loot([PartyMember("A", balance=101), PartyMember("B", balance=0)])
    assert split.share == 50
    assert [(t.sender, t.receiver, t.amount) for t in split.transfers] == [("A", "B", 50)]


def test_split_loot_negative_hunt():
    split = split_loot([PartyMember("A", balance=-100), PartyMember("B", balance=-300)])
    assert split.share == -200
    assert split.transfers[0].command == "transfer 100 to B"


def test_split_loot_equal_needs_no_transfers():
    assert split_loot([PartyMember("A", balance=5), PartyMember("B", balance=5)]).transfers == []
    assert split_loot([]).transfers == []


@pytest.mark.parametrize(("text", "minutes"), [("39:30", 2370), ("42", 2520), ("0:05", 5), ("42:01", None), ("12:60", None), ("x", None)])
def test_parse_stamina(text, minutes):
    assert parse_stamina(text) == minutes


def test_offline_bonus_hours_match_wiki():
    # TibiaWiki: z 39:00 do 42:00 trzeba 18 h 10 min offline.
    assert offline_minutes_needed(39 * 60) == 18 * 60 + 10


def test_offline_crossing_bonus_threshold():
    assert offline_minutes_needed(38 * 60, 40 * 60) == 10 + 60 * 3 + 60 * 6
    assert offline_minutes_needed(42 * 60) == 0
    assert format_minutes(1090) == "18:10"


def test_skill_points_match_wiki_formula():
    # Knight, melee: 50 * 1.1^(skill-10) punktów na następny poziom.
    assert skill_points_needed("melee", "knight", 10, 0, 11) == pytest.approx(50)
    assert skill_points_needed("melee", "knight", 10, 50, 12) == pytest.approx(25 + 55)


def test_lasting_weapon_example_from_wiki():
    # TibiaWiki: jedna Lasting Exercise Weapon daje knightowi skill z 15 do ok. 66, druidowi ML z 1 do 66.
    assert skill_plan("melee", "knight", 15, 0, 66).weapons[2].count == 1
    assert skill_plan("magic", "druid", 1, 0, 66).weapons[2].count == 1


def test_skill_plan_bonuses_reduce_charges():
    base = skill_plan("distance", "paladin", 80, 0, 90).charges
    assert skill_plan("distance", "paladin", 80, 0, 90, expert_dummy=True).charges < base
    assert skill_plan("distance", "paladin", 80, 0, 90, double_skill=True).charges == pytest.approx(base / 2, abs=1)
    assert skill_plan("magic", "druid", 50, 0, 50).charges == 0
