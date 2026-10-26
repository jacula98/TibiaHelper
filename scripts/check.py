"""Lokalne sprawdzenie przed PR: ruff, pytest i walidacja data/quests.json.

Zamiast płatnego CI uruchamiamy to u siebie: python scripts/check.py
Kod wyjścia 0 = wszystko OK.
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(name: str, cmd: list[str]) -> bool:
    print(f"\n== {name} ==")
    ok = subprocess.run(cmd, check=False, cwd=ROOT).returncode == 0
    print("OK" if ok else "BŁĄD")
    return ok


def check_quests() -> bool:
    print("\n== Walidacja data/quests.json ==")
    sys.path.insert(0, str(ROOT / "app"))
    try:
        from tibiahelper.core.repository import QuestFileError, load_quest_file
    except ImportError as exc:
        print(f"Pominięto: brak modułu walidacji ({exc})")
        return True

    try:
        result = load_quest_file(ROOT / "data" / "quests.json")
    except QuestFileError as exc:
        print(exc)
        print("BŁĄD")
        return False

    # repository.py pomija złe questy, żeby aplikacja działała dalej.
    # Tutaj traktujemy je jako błąd, bo nie powinny trafić do repo.
    errors = list(result.errors)
    spawns_file = ROOT / "data" / "spawns.json"
    if spawns_file.is_file():
        from tibiahelper.core.spawns import load_spawns

        spawns = load_spawns(spawns_file)
        unknown = sorted(set(spawns.monsters) - set(result.monsters))
        if unknown:
            errors.append(f"spawns.json: potwory spoza quests.json: {unknown[:10]}")
        print(f"Spawny: {len(spawns.monsters)} potworów")
    npcs_file = ROOT / "data" / "npcs.json"
    if npcs_file.is_file():
        import json

        from tibiahelper.core.npcs import load_npcs

        # load_npcs pomija błędne wpisy; tu każdy pominięty to błąd w repo.
        total = len(json.loads(npcs_file.read_text(encoding="utf-8")).get("npcs", []))
        valid = len(load_npcs(npcs_file))
        if valid != total:
            errors.append(f"npcs.json: {total - valid} błędnych wpisów")
        print(f"NPC: {valid}, obrazki przedmiotów: {len(result.item_images)}")

    for message in errors:
        print(message)
    print(f"Questy: {len(result.quests)}, potwory: {len(result.monsters)}, błędy: {len(errors)}")
    print("OK" if not errors else "BŁĄD")
    return not errors


def main() -> int:
    results = []

    # ruff jest opcjonalny: pip install ruff
    # Reguły podane wprost (E/F to realne błędy: nieużyte importy, literówki w nazwach),
    # żeby wynik nie zależał od wersji ruffa ani konfiguracji na danym komputerze.
    if importlib.util.find_spec("ruff"):
        ruff = [sys.executable, "-m", "ruff", "check", "--isolated", "--select", "E4,E7,E9,F", "."]
        results.append(run("ruff", ruff))
    else:
        print("\n== ruff ==\nPominięto: zainstaluj przez `pip install ruff`")

    if (ROOT / "tests").is_dir():
        results.append(run("pytest", [sys.executable, "-m", "pytest", "-q"]))

    if (ROOT / "data" / "quests.json").is_file():
        results.append(check_quests())

    print("\nWynik:", "wszystko OK" if all(results) else "są błędy")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
