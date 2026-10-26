"""Wgrywanie podstawowych ustawień UI i hotkeyów (Quality of life) do klienta Tibii.

Klient trzyma je w jednym pliku dla całego konta:
%LOCALAPPDATA%/Tibia/packages/Tibia/conf/clientoptions.json.
Nasz plik (data/qol/clientoptions.json) to ustawienia autora projektu, oczyszczone
z rzeczy osobistych i zależnych od komputera (logowanie, dźwięk, grafika, okno).
Przy wgraniu podmieniamy tylko te części, które są w naszym pliku; reszta pliku
gracza (np. pozycja okna, e-mail do logowania, głośność) zostaje bez zmian.
"""

import json
import os
from pathlib import Path

from .storage import write_bytes_atomic

FILE_NAME = "clientoptions.json"
BACKUP_SUFFIX = ".tibiahelper-backup"
# Sekcje podmieniane w całości: przyciski na pasku, kolejność ikon stanów, otwarte kanały czatu.
REPLACED_SECTIONS = ("chatOptions", "controlButtonsOptions", "specialConditionsOptions")


def options_file() -> Path | None:
    """Plik ustawień klienta albo None, gdy to nie Windows z Tibią."""
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return None
    return Path(local) / "Tibia" / "packages" / "Tibia" / "conf" / FILE_NAME


def merge(current: dict, ours: dict) -> dict:
    result = dict(current)
    for section in REPLACED_SECTIONS:
        if section in ours:
            result[section] = ours[section]
    # Opcje pojedynczo: nasze nadpisują, opcje, których nie mamy (np. dźwięk), zostają gracza.
    options = dict(current.get("options") or {})
    options.update(ours.get("options", {}))
    result["options"] = options
    # Zestawy hotkeyów po nazwie (Basic, Knight, ...): nasze podmieniają te same nazwy, inne gracza zostają.
    hotkeys = dict(current.get("hotkeyOptions") or {})
    ours_hotkeys = ours.get("hotkeyOptions", {})
    sets = dict(hotkeys.get("hotkeySets") or {})
    sets.update(ours_hotkeys.get("hotkeySets", {}))
    hotkeys.update({key: value for key, value in ours_hotkeys.items() if key != "hotkeySets"})
    hotkeys["hotkeySets"] = sets
    result["hotkeyOptions"] = hotkeys
    result.setdefault("clientOptionsVersion", ours.get("clientOptionsVersion"))
    return result


def install(target: Path, source: Path) -> bool:
    """Wgrywa ustawienia. Zwraca True, gdy powstała kopia zapasowa (tylko przy pierwszym razie).

    Błędy: OSError (zapis/odczyt), ValueError (zepsuty JSON), TypeError (JSON o innym kształcie).
    """
    ours = json.loads(source.read_text(encoding="utf-8"))
    current: dict = {}
    made_backup = False
    if target.exists():
        raw = target.read_bytes()
        backup = target.with_name(target.name + BACKUP_SUFFIX)
        if not backup.exists():
            write_bytes_atomic(backup, raw)
            made_backup = True
        loaded = json.loads(raw.decode("utf-8-sig"))
        if not isinstance(loaded, dict):
            raise TypeError("Plik ustawień Tibii ma nieoczekiwany format")
        current = loaded
    # Wcięcie 4 spacje, tak jak zapisuje klient.
    write_bytes_atomic(target, json.dumps(merge(current, ours), indent=4).encode("utf-8"))
    return made_backup
