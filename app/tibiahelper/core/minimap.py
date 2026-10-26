"""Wgrywanie pełnej minimapy z tibiamaps do klienta Tibii (Quality of life).

tibiamaps (tibia-map-data, kod MIT, „Feel free to use”) udostępnia paczki zip
z minimapą w formacie klienta: folder minimap/ z plikami Minimap_Color_X_Y_Z.png,
Minimap_WaypointCost_X_Y_Z.png i (w wersjach z markerami) minimapmarkers.bin.
Wystarczy je rozpakować do %LOCALAPPDATA%/Tibia/packages/Tibia/minimap.
To ten sam efekt co instalator ze strony tibiamaps.io, tylko bez instalatora.
"""

import io
import os
import re
import shutil
import urllib.request
import zipfile
import zlib
from pathlib import Path

from .storage import write_bytes_atomic

BASE_URL = "https://tibiamaps.github.io/tibia-map-data/"
# (markery, siatka) -> nazwa paczki. Markery: "all" (wszystkie), "poi" (tylko ciekawe miejsca), "none".
# Wersja „tylko POI” istnieje wyłącznie z siatką.
PACKAGES = {
    ("all", False): "minimap-with-markers.zip",
    ("none", False): "minimap-without-markers.zip",
    ("all", True): "minimap-with-grid-overlay-and-markers.zip",
    ("none", True): "minimap-with-grid-overlay-without-markers.zip",
    ("poi", True): "minimap-with-grid-overlay-and-poi-markers.zip",
}
MARKERS_FILE = "minimapmarkers.bin"
BACKUP_NAME = "minimap.tibiahelper-backup"
TIMEOUT_SECONDS = 60
MAX_ZIP_BYTES = 30 * 1024 * 1024  # paczka ma ok. 6,6 MB
MAX_FILE_BYTES = 2 * 1024 * 1024  # pojedynczy plik ma kilka KB, markery ok. 200 KB
MAX_FILES = 5000  # paczka ma ok. 2200 plików
# Tylko pliki minimapy, bez podfolderów i „..”: zip z internetu nie może pisać gdzie indziej.
ALLOWED_NAME = re.compile(r"^minimap/(Minimap_(?:Color|WaypointCost)_\d+_\d+_\d+\.png|minimapmarkers\.bin)$")


def package_url(markers: str, grid: bool) -> str:
    return BASE_URL + PACKAGES[(markers, grid)]


def minimap_dir() -> Path | None:
    """Folder minimapy klienta albo None, gdy to nie Windows z Tibią."""
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return None
    return Path(local) / "Tibia" / "packages" / "Tibia" / "minimap"


def download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "TibiaHelper"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
        data = response.read(MAX_ZIP_BYTES + 1)
    if len(data) > MAX_ZIP_BYTES:
        raise ValueError("Paczka minimapy jest za duża")
    return data


def read_package(data: bytes) -> dict[str, bytes]:
    """Sprawdza zip i zwraca {nazwa pliku: zawartość}. Błąd w paczce to ValueError."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ValueError("Pobrany plik nie jest paczką zip") from exc
    files: dict[str, bytes] = {}
    with archive:
        entries = [info for info in archive.infolist() if not info.is_dir()]
        if len(entries) > MAX_FILES:
            raise ValueError("Za dużo plików w paczce")
        for info in entries:
            match = ALLOWED_NAME.match(info.filename)
            if match is None:
                raise ValueError(f"Nieoczekiwany plik w paczce: {info.filename}")
            # file_size pochodzi z nagłówka zip; read() i tak nie zwróci więcej niż tyle.
            if info.file_size > MAX_FILE_BYTES:
                raise ValueError(f"Za duży plik w paczce: {info.filename}")
            try:
                files[match.group(1)] = archive.read(info)
            except (zipfile.BadZipFile, zlib.error) as exc:  # np. zły CRC po urwanym pobieraniu
                raise ValueError(f"Uszkodzony plik w paczce: {info.filename}") from exc
    if not any(name.startswith("Minimap_Color_") for name in files):
        raise ValueError("W paczce nie ma minimapy")
    return files


def install(target: Path, files: dict[str, bytes]) -> bool:
    """Wgrywa pliki do folderu minimapy. Zwraca True, gdy powstała kopia zapasowa.

    Kopia całego starego folderu powstaje tylko raz (przy pierwszym wgraniu), żeby
    zawsze dało się wrócić do minimapy i własnych markerów gracza sprzed programu.
    Wersja bez markerów nie rusza minimapmarkers.bin, więc markery gracza zostają.
    """
    backup = target.with_name(BACKUP_NAME)
    made_backup = False
    if target.is_dir() and not backup.exists():
        shutil.copytree(target, backup)
        made_backup = True
    for name, content in files.items():
        write_bytes_atomic(target / name, content)
    return made_backup
