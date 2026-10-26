"""Testy wgrywania minimapy z tibiamaps (Quality of life)."""

import io
import zipfile

import pytest

from tibiahelper.core import minimap


def _zip(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_every_choice_has_a_package():
    assert minimap.package_url(True, False).endswith("/minimap-with-markers.zip")
    assert minimap.package_url(False, True).endswith("/minimap-with-grid-overlay-without-markers.zip")
    assert len(minimap.PACKAGES) == 4
    assert all(url.startswith("https://tibiamaps.github.io/") for url in map(minimap.BASE_URL.__add__, minimap.PACKAGES.values()))


def test_read_package_accepts_only_minimap_files():
    data = _zip({
        "minimap/Minimap_Color_32000_31000_7.png": b"c",
        "minimap/Minimap_WaypointCost_32000_31000_7.png": b"w",
        "minimap/minimapmarkers.bin": b"m",
    })
    files = minimap.read_package(data)
    assert set(files) == {"Minimap_Color_32000_31000_7.png", "Minimap_WaypointCost_32000_31000_7.png", "minimapmarkers.bin"}

    for bad in ("minimap/../evil.png", "evil.exe", "minimap/sub/Minimap_Color_1_2_3.png"):
        with pytest.raises(ValueError):
            minimap.read_package(_zip({"minimap/Minimap_Color_1_2_3.png": b"c", bad: b"x"}))
    with pytest.raises(ValueError):
        minimap.read_package(b"to nie zip")
    with pytest.raises(ValueError):
        minimap.read_package(_zip({"minimap/minimapmarkers.bin": b"m"}))
    broken = data.replace(b"c", b"X", 1)  # zmieniona zawartość = zły CRC
    with pytest.raises(ValueError):
        minimap.read_package(broken)


def test_install_backs_up_once_and_keeps_markers_without_new_ones(tmp_path):
    target = tmp_path / "Tibia" / "minimap"
    target.mkdir(parents=True)
    (target / "minimapmarkers.bin").write_bytes(b"moje")
    (target / "Minimap_Color_1_2_7.png").write_bytes(b"stare")

    assert minimap.install(target, {"Minimap_Color_1_2_7.png": b"nowe", "Minimap_Color_3_4_7.png": b"n"}) is True
    assert (target / "Minimap_Color_1_2_7.png").read_bytes() == b"nowe"
    assert (target / "minimapmarkers.bin").read_bytes() == b"moje"  # wersja bez markerów ich nie rusza
    backup = target.with_name(minimap.BACKUP_NAME)
    assert (backup / "Minimap_Color_1_2_7.png").read_bytes() == b"stare"

    assert minimap.install(target, {"minimapmarkers.bin": b"tibiamaps"}) is False
    assert (backup / "minimapmarkers.bin").read_bytes() == b"moje"  # kopia oryginału zostaje
