"""Robi ikonę programu (logo.ico) z logo.svg. Uruchamia autor po zmianie logo:

    python scripts/make_icon.py

Plik .ico to kilka obrazków PNG w różnych rozmiarach w jednym pliku. Windows
sam wybiera rozmiar: 16 px na pasku zadań, 32/48 px na pulpicie, 256 px w dużych ikonach.
Rysujemy przez Qt (PySide6 i tak jest w zależnościach), więc nie trzeba Pillow.
"""

import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ASSETS = Path(__file__).resolve().parent.parent / "app" / "tibiahelper" / "ui" / "assets"
SIZES = (16, 24, 32, 48, 64, 128, 256)


def render_png(renderer: QSvgRenderer, size: int) -> bytes:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter)
    painter.end()
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(data)


def build_ico(pngs: dict[int, bytes]) -> bytes:
    # Nagłówek ICO: 0, typ 1 (ikona), liczba obrazków. Potem 16 bajtów opisu na obrazek.
    header = struct.pack("<HHH", 0, 1, len(pngs))
    offset = len(header) + 16 * len(pngs)
    entries, blobs = b"", b""
    for size, png in pngs.items():
        side = size % 256  # w formacie ICO 0 oznacza 256 px
        entries += struct.pack("<BBBBHHII", side, side, 0, 0, 1, 32, len(png), offset)
        blobs += png
        offset += len(png)
    return header + entries + blobs


def main() -> int:
    app = QGuiApplication(sys.argv)  # noqa: F841  Qt potrzebuje aplikacji do rysowania
    renderer = QSvgRenderer(str(ASSETS / "logo.svg"))
    if not renderer.isValid():
        print("Nie udało się wczytać logo.svg")
        return 1
    ico = build_ico({size: render_png(renderer, size) for size in SIZES})
    (ASSETS / "logo.ico").write_bytes(ico)
    print(f"Zapisano logo.ico ({len(ico)} B, rozmiary: {', '.join(map(str, SIZES))})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
