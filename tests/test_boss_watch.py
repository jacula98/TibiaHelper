"""Testy powiadomień o bossach: statystyki z TibiaData, lista bossów i timery. Bez sieci."""

import json
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path

from generator.boss_spawns import active_worlds, build, is_world_spawn, plotted_bosses
from tibiahelper.core import boss_watch
from tibiahelper.core.boss_timers import (
    BossTimer,
    due_warnings,
    format_left,
    load_timers,
    make_timer,
    save_timers,
)
from tibiahelper.core.boss_watch import (
    Sighting,
    WatchedBoss,
    check_world,
    clean_world,
    find_sightings,
    load_watched,
    load_worlds,
    parse_killstats,
    stats_day,
)
from tibiahelper.core.settings import Settings, load_settings, save_settings

ROOT = Path(__file__).resolve().parents[1]
NOON = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)
NAMES = {"tyrn": "Tyrn", "white-pale": "White Pale", "ferumbras": "Ferumbras"}


def _stats(*entries):
    rows = [
        {"race": race, "last_day_players_killed": players, "last_day_killed": killed,
         "last_week_players_killed": players, "last_week_killed": killed}
        for race, players, killed in entries
    ]
    return json.dumps({"killstatistics": {"world": "Antica", "entries": rows}}).encode("utf-8")


STATS = _stats(("Tyrn", 2, 1), ("dragons", 5, 900), ("White Pale", 0, 0), ("Ferumbras", 0, 1))


def _fetch(data=STATS, calls=None):
    def fetch(url):
        if calls is not None:
            calls.append(url)
        if isinstance(data, Exception):
            raise data
        return data

    return fetch


def test_parse_killstats_keeps_last_day():
    stats = parse_killstats(STATS)
    assert stats["tyrn"] == (2, 1)
    assert stats["dragons"] == (5, 900)


def test_parse_killstats_rejects_garbage():
    for data in (b"{urwany", b"[]", b'{"killstatistics": {"entries": "x"}}'):
        try:
            parse_killstats(data)
        except ValueError:
            continue
        raise AssertionError(data)


def test_parse_killstats_skips_bad_rows():
    data = json.dumps({"killstatistics": {"entries": [
        {"race": "Tyrn", "last_day_players_killed": "dużo", "last_day_killed": 1},
        {"race": 5}, "x",
        {"race": "Xenia", "last_day_players_killed": 1, "last_day_killed": 0},
    ]}}).encode()
    assert parse_killstats(data) == {"xenia": (1, 0)}


def test_find_sightings_only_bosses_that_did_something():
    found = find_sightings(parse_killstats(STATS), NAMES)
    assert found == [Sighting("ferumbras", "Ferumbras", 0, 1), Sighting("tyrn", "Tyrn", 2, 1)]


def test_clean_world():
    assert clean_world(" antica ") == "Antica"
    assert clean_world("Bona") == "Bona"
    for bad in ("", "An", "Antica/../x", "Antica 2", None, 5):
        assert clean_world(bad) is None


def test_stats_day_changes_at_4_am_berlin():
    # Lato: 4:00 w Berlinie = 2:00 UTC.
    assert stats_day(datetime(2026, 7, 2, 1, 59, tzinfo=timezone.utc)).isoformat() == "2026-07-01"
    assert stats_day(datetime(2026, 7, 2, 2, 0, tzinfo=timezone.utc)).isoformat() == "2026-07-02"
    # Zima: 4:00 w Berlinie = 3:00 UTC.
    assert stats_day(datetime(2026, 12, 2, 2, 59, tzinfo=timezone.utc)).isoformat() == "2026-12-01"


def test_check_world_fetches_once_per_day(tmp_path):
    cache, calls = tmp_path / "boss_watch.json", []
    result, fresh = check_world(cache, "Antica", NAMES, NOON, _fetch(calls=calls))
    assert fresh and [s.monster for s in result.sightings] == ["ferumbras", "tyrn"]
    assert calls == ["https://api.tibiadata.com/v4/killstatistics/Antica"]
    # Ten sam dzień: z pliku, bez sieci i bez drugiego powiadomienia.
    again, fresh = check_world(cache, "Antica", NAMES, NOON + timedelta(hours=5), _fetch(calls=calls))
    assert not fresh and again == result and len(calls) == 1
    # Następny dzień: pyta znowu.
    _, fresh = check_world(cache, "Antica", NAMES, NOON + timedelta(days=1), _fetch(calls=calls))
    assert fresh and len(calls) == 2


def test_check_world_other_world_asks_again(tmp_path):
    cache, calls = tmp_path / "boss_watch.json", []
    check_world(cache, "Antica", NAMES, NOON, _fetch(calls=calls))
    result, fresh = check_world(cache, "Bona", NAMES, NOON, _fetch(calls=calls))
    assert fresh and result.world == "Bona" and len(calls) == 2


def test_check_world_offline_keeps_old_result(tmp_path):
    cache = tmp_path / "boss_watch.json"
    old, _ = check_world(cache, "Antica", NAMES, NOON, _fetch())
    result, fresh = check_world(cache, "Antica", NAMES, NOON + timedelta(days=1), _fetch(urllib.error.URLError("x")))
    assert result == old and not fresh
    # Bez sieci i bez pliku dla tego świata: nic.
    assert check_world(cache, "Bona", NAMES, NOON, _fetch(urllib.error.URLError("x"))) == (None, False)


def test_load_watched(tmp_path):
    path = tmp_path / "boss_spawns.json"
    path.write_text(json.dumps({"bosses": [
        {"monster": "tyrn", "respawn_days": [3, 7]},
        {"monster": "xenia"},
        {"monster": "zly", "respawn_days": [7, 3]},
        {"brak": 1},
    ]}), encoding="utf-8")
    assert load_watched(path) == {"tyrn": WatchedBoss("tyrn", (3, 7)), "xenia": WatchedBoss("xenia")}
    assert load_watched(tmp_path / "brak.json") == {}


def test_bundled_boss_spawns_match_monsters():
    # Każdy boss z listy musi być w bazie potworów, inaczej powiadomienie nie miałoby czego otworzyć.
    watched = load_watched(ROOT / "data" / "boss_spawns.json")
    monsters = {m["id"] for m in json.loads((ROOT / "data" / "quests.json").read_text(encoding="utf-8"))["monsters"]}
    assert "tyrn" in watched and len(watched) > 50
    assert set(watched) <= monsters


def test_is_world_spawn():
    assert is_world_spawn("Raid, Unique")
    assert is_world_spawn("Regular, Unblockable, Unique")
    assert not is_world_spawn("Triggered, Unique")
    assert not is_world_spawn("Regular")
    assert not is_world_spawn("")


def test_build_keeps_author_respawn():
    monsters = [
        {"id": "tyrn", "boss": True, "source_url": "https://tibia.fandom.com/wiki/Tyrn"},
        {"id": "grand-master-oberon", "boss": True, "source_url": "https://tibia.fandom.com/wiki/Grand_Master_Oberon"},
        {"id": "dragon", "source_url": "https://tibia.fandom.com/wiki/Dragon"},
    ]
    pages = {
        "Tyrn": "{{Infobox Creature\n| name = Tyrn\n| spawntype = Raid, Unique\n}}",
        "Grand Master Oberon": "{{Infobox Creature\n| spawntype = Triggered, Unique\n}}",
    }
    old = {"bosses": [{"monster": "tyrn", "respawn_days": [3, 7]}]}
    assert build(monsters, pages, old)["bosses"] == [{"monster": "tyrn", "respawn_days": [3, 7]}]


def test_build_adds_plotted_bosses_with_window():
    monsters = [{"id": "ghazbaran", "name": "Ghazbaran", "boss": True, "source_url": "https://tibia.fandom.com/wiki/Ghazbaran"}]
    pages = {"Ghazbaran": "{{Infobox Creature\n| name = Ghazbaran\n}}"}
    assert build(monsters, pages)["bosses"] == []
    assert build(monsters, pages, plotted={"Ghazbaran"})["bosses"] == [{"monster": "ghazbaran", "respawn_days": [162, 176]}]


def test_timer_window_and_warning():
    timer = make_timer(NOON, 7, 3)  # odwrotna kolejność też działa
    assert (timer.min_days, timer.max_days) == (3, 7)
    assert timer.window_start == NOON + timedelta(days=3)
    timers = {"tyrn": timer}
    assert due_warnings(timers, NOON + timedelta(days=2)) == []
    assert due_warnings(timers, NOON + timedelta(days=3) - timedelta(minutes=30)) == ["tyrn"]
    # Komputer był wyłączony: przypomnienie przy starcie, póki okno trwa.
    assert due_warnings(timers, NOON + timedelta(days=5)) == ["tyrn"]
    assert due_warnings(timers, NOON + timedelta(days=8)) == []
    done = {"tyrn": BossTimer(NOON, 3, 7, notified=True)}
    assert due_warnings(done, NOON + timedelta(days=3)) == []


def test_timers_round_trip(tmp_path):
    path = tmp_path / "boss_timers.json"
    timers = {"tyrn": BossTimer(NOON, 3, 7, notified=True)}
    save_timers(path, timers)
    assert load_timers(path) == timers


def test_broken_timers_are_skipped(tmp_path):
    path = tmp_path / "boss_timers.json"
    path.write_text(json.dumps({"timers": {
        "tyrn": {"killed_at": "2026-10-29T12:00:00+00:00", "min_days": 3, "max_days": 7},
        "bez-strefy": {"killed_at": "2026-10-29T12:00:00", "min_days": 3, "max_days": 7},
        "zly": {"killed_at": "wczoraj", "min_days": 3, "max_days": 7},
    }}), encoding="utf-8")
    assert list(load_timers(path)) == ["tyrn"]
    path.write_text("{urwany", encoding="utf-8")
    assert load_timers(path) == {}


def test_format_left():
    assert format_left(timedelta(days=2, hours=5, minutes=3)) == "2 d 5 h"
    assert format_left(timedelta(hours=3, minutes=20)) == "3 h 20 min"
    assert format_left(timedelta(minutes=15)) == "15 min"
    assert format_left(timedelta(minutes=-5)) == "0 min"


def test_world_in_settings(tmp_path):
    path = tmp_path / "settings.json"
    save_settings(path, Settings(world="antica"))
    assert load_settings(path).world == "Antica"
    path.write_text('{"world": "Antica/../x"}', encoding="utf-8")
    assert load_settings(path).world is None


def test_url_has_only_world_name():
    assert boss_watch.KILLSTATS_URL.startswith("https://api.tibiadata.com/")


def test_bundled_worlds_and_respawn_windows():
    worlds = load_worlds(ROOT / "data" / "boss_spawns.json")
    assert "Antica" in worlds and len(worlds) > 50
    watched = load_watched(ROOT / "data" / "boss_spawns.json")
    assert watched["ferumbras"].respawn_days == (162, 176)
    assert watched["ghazbaran"].respawn_days is not None  # wiki nie ma u niego spawntype, ale ma wykres


def test_plotted_bosses_and_worlds():
    assert plotted_bosses("<gallery>\nSpawn Frequency - The Imperor.png|The Imperor\nFoo.png|Bar\n</gallery>") == {"The Imperor"}
    pages = {
        "Antica": "{{Infobox World\n| name = Antica\n| type = Open PvP\n}}",
        "Tenebra": "{{Infobox World\n| name = Tenebra\n| offline = May 2, 2016\n}}",
    }
    assert active_worlds(pages) == ["Antica"]
