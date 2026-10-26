"""Wgrywanie ustawień lootu i cen (Quality of life) do klienta Tibii.

Klient trzyma ustawienia każdej postaci w osobnym folderze:
%LOCALAPPDATA%/Tibia/packages/Tibia/characterdata/<ID postaci>/.
Podmieniamy w nim tylko dwa pliki, które klient sam umie wczytać:
- lootBlackWhitelist.json: przedmioty pomijane przy zbieraniu lootu (śmieci),
- itemprices.json: przedmioty liczone po cenie z Marketu (delivery taski, imbu).

Nie dotykamy gry ani jej pamięci, to tylko pliki ustawień. Ustawienia gracza
nie giną: listy łączymy z tym, co już ma, a oryginał zostaje w kopii zapasowej.
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from .storage import write_bytes_atomic

LOOT_FILE = "lootBlackWhitelist.json"
PRICES_FILE = "itemprices.json"
# Kopia oryginału robiona tylko raz, przy pierwszym wgraniu (kolejne wgrania jej nie nadpisują).
BACKUP_SUFFIX = ".tibiahelper-backup"


def characterdata_dir() -> Path | None:
    """Folder z ustawieniami postaci albo None, gdy to nie Windows z Tibią."""
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return None
    return Path(local) / "Tibia" / "packages" / "Tibia" / "characterdata"


def character_dirs(base: Path) -> list[Path]:
    # Podfoldery to numery ID postaci; inne foldery (gdyby były) pomijamy.
    if not base.is_dir():
        return []
    return sorted(p for p in base.iterdir() if p.is_dir() and p.name.isdigit())


def merge_loot(current: dict, ours: dict) -> dict:
    """Czarna lista gracza + nasza; tryb „blacklist”, żeby śmieci były pomijane."""
    result = dict(current)
    blacklist = list(current.get("blacklistTypes") or [])
    known = set(blacklist)
    blacklist += [item for item in ours.get("blacklistTypes", []) if item not in known]
    result["blacklistTypes"] = blacklist
    result["listType"] = "blacklist"
    result.setdefault("whitelistTypes", [])
    return result


def merge_prices(current: dict, ours: dict) -> dict:
    """Nasze „licz po cenie z Marketu” nadpisują wybór gracza; jego własne ceny zostają."""
    result = dict(current)
    sources = dict(current.get("primaryLootValueSources") or {})
    sources.update(ours.get("primaryLootValueSources", {}))
    result["primaryLootValueSources"] = sources
    result.setdefault("customSalePrices", {})
    return result


MERGERS = {LOOT_FILE: merge_loot, PRICES_FILE: merge_prices}


@dataclass
class InstallResult:
    characters: int = 0
    errors: list[str] = field(default_factory=list)


def install(base: Path, source_dir: Path) -> InstallResult:
    """Wgrywa oba pliki do każdej postaci. Błąd jednej postaci nie zatrzymuje reszty."""
    ours = {name: json.loads((source_dir / name).read_text(encoding="utf-8")) for name in MERGERS}
    result = InstallResult()
    for folder in character_dirs(base):
        try:
            for name, merge in MERGERS.items():
                _install_file(folder / name, ours[name], merge)
            result.characters += 1
        except (OSError, ValueError) as exc:
            result.errors.append(f"{folder.name}: {exc}")
    return result


def _install_file(path: Path, ours: dict, merge) -> None:
    current: dict = {}
    if path.exists():
        raw = path.read_bytes()
        backup = path.with_name(path.name + BACKUP_SUFFIX)
        if not backup.exists():
            write_bytes_atomic(backup, raw)
        loaded = json.loads(raw.decode("utf-8-sig"))
        if isinstance(loaded, dict):
            current = loaded
    # Wcięcie 4 spacje, tak jak zapisuje klient.
    write_bytes_atomic(path, json.dumps(merge(current, ours), indent=4).encode("utf-8"))
