"""Testy zakładki Quality of life: wgrywanie loot filtra i cen do folderów postaci."""

import json

from tibiahelper.core import loot_settings
from tibiahelper.core.paths import bundled_qol_dir


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_bundled_files_are_valid():
    loot = json.loads((bundled_qol_dir() / loot_settings.LOOT_FILE).read_text(encoding="utf-8"))
    prices = json.loads((bundled_qol_dir() / loot_settings.PRICES_FILE).read_text(encoding="utf-8"))
    assert loot["listType"] == "blacklist" and loot["blacklistTypes"]
    assert set(prices["primaryLootValueSources"].values()) == {"market"}


def test_install_merges_keeps_player_settings_and_backs_up(tmp_path):
    source = tmp_path / "qol"
    _write(source / loot_settings.LOOT_FILE, {"blacklistTypes": [1, 2], "listType": "blacklist", "whitelistTypes": []})
    _write(source / loot_settings.PRICES_FILE, {"customSalePrices": {}, "primaryLootValueSources": {"10": "market"}})

    base = tmp_path / "characterdata"
    player = base / "61234567"
    _write(player / loot_settings.LOOT_FILE, {"blacklistTypes": [2, 99], "listType": "whitelist", "whitelistTypes": [5]})
    _write(player / loot_settings.PRICES_FILE, {"customSalePrices": {"7": 100}, "primaryLootValueSources": {"10": "npc", "11": "npc"}})
    (base / "72345678").mkdir()  # nowa postać bez plików
    (base / "logs").mkdir()  # nie-postać: pomijana

    result = loot_settings.install(base, source)
    assert result.characters == 2 and not result.errors

    loot = json.loads((player / loot_settings.LOOT_FILE).read_text())
    assert loot == {"blacklistTypes": [2, 99, 1], "listType": "blacklist", "whitelistTypes": [5]}
    prices = json.loads((player / loot_settings.PRICES_FILE).read_text())
    assert prices == {"customSalePrices": {"7": 100}, "primaryLootValueSources": {"10": "market", "11": "npc"}}
    backup = json.loads((player / (loot_settings.LOOT_FILE + loot_settings.BACKUP_SUFFIX)).read_text())
    assert backup["listType"] == "whitelist"
    assert json.loads((base / "72345678" / loot_settings.LOOT_FILE).read_text())["blacklistTypes"] == [1, 2]
    assert not (base / "logs" / loot_settings.LOOT_FILE).exists()

    # Drugie wgranie nie dubluje wpisów i nie nadpisuje kopii oryginału.
    loot_settings.install(base, source)
    assert json.loads((player / loot_settings.LOOT_FILE).read_text())["blacklistTypes"] == [2, 99, 1]
    backup = json.loads((player / (loot_settings.LOOT_FILE + loot_settings.BACKUP_SUFFIX)).read_text())
    assert backup["listType"] == "whitelist"


def test_broken_file_is_reported_not_fatal(tmp_path):
    source = tmp_path / "qol"
    _write(source / loot_settings.LOOT_FILE, {"blacklistTypes": [1], "listType": "blacklist", "whitelistTypes": []})
    _write(source / loot_settings.PRICES_FILE, {"customSalePrices": {}, "primaryLootValueSources": {}})
    base = tmp_path / "characterdata"
    (base / "1").mkdir(parents=True)
    (base / "1" / loot_settings.LOOT_FILE).write_text("{zepsuty", encoding="utf-8")
    (base / "2").mkdir()

    result = loot_settings.install(base, source)
    assert result.characters == 1
    assert len(result.errors) == 1 and result.errors[0].startswith("1:")
