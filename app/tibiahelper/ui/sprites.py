"""Obrazki potworów przycięte do samej postaci.

Obrazki z wiki mają 64x64 px, a mały potwór zajmuje tylko róg tego pola.
W tekście kroku wyglądałby wtedy jak kropka, więc wycinamy przezroczyste
brzegi i zapisujemy wynik obok oryginału (liczy się tylko raz).
"""

import logging
from pathlib import Path

from PySide6.QtCore import QRect
from PySide6.QtGui import QBitmap, QImage, QPainter, QRegion

from ..core.monsters import sprite_path

log = logging.getLogger(__name__)


def opaque_rect(image: QImage) -> QRect:
    """Najmniejszy prostokąt z nieprzezroczystymi pikselami.

    Maska przezroczystości i QRegion liczą to w C++ (Qt), a nie w pętli Pythona
    piksel po pikselu: przy siatce potworów to różnica między płynnym a szarpanym przewijaniem.
    """
    if not image.hasAlphaChannel():
        return image.rect()
    box = QRegion(QBitmap.fromImage(image.createAlphaMask())).boundingRect()
    return box if box.isValid() else image.rect()  # cały przezroczysty: zostawiamy jak jest


def display_sprite(sprites_dir: Path, monster_id: str) -> Path | None:
    """Przycięty, kwadratowy obrazek do pokazania albo None, gdy oryginału jeszcze nie ma."""
    original = sprite_path(sprites_dir, monster_id)
    if original is None:
        return None
    cropped = sprites_dir / f"{monster_id}-crop.png"
    if cropped.exists():
        return cropped
    image = QImage(str(original)).convertToFormat(QImage.Format.Format_ARGB32)
    if image.isNull():
        return original
    box = opaque_rect(image)
    # Kwadrat: obrazek w tekście ma stałą szerokość i wysokość, więc nie może się rozciągać.
    side = max(box.width(), box.height())
    square = QImage(side, side, QImage.Format.Format_ARGB32)
    square.fill(0)
    part = image.copy(box)
    # Postać przy dolnej krawędzi i na środku, jak stoi w grze.
    painter = QPainter(square)
    painter.drawImage((side - box.width()) // 2, side - box.height(), part)
    painter.end()
    if not square.save(str(cropped)):
        log.info("Nie udało się zapisać %s", cropped)
        return original
    return cropped
