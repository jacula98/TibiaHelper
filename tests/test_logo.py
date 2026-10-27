"""Logo i ikona programu: pliki są na miejscu, a .ico ma rozmiary potrzebne Windowsowi."""

import struct
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "app" / "tibiahelper" / "ui" / "assets"


def test_logo_svg_exists():
    assert (ASSETS / "logo.svg").read_text(encoding="utf-8").startswith("<svg")


def test_logo_ico_has_windows_sizes():
    data = (ASSETS / "logo.ico").read_bytes()
    reserved, kind, count = struct.unpack_from("<HHH", data)
    assert (reserved, kind) == (0, 1)
    # Szerokość 0 w nagłówku ICO oznacza 256 px.
    sizes = {data[6 + 16 * i] or 256 for i in range(count)}
    assert {16, 32, 48, 256} <= sizes
