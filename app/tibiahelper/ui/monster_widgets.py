"""Widżety potworów: animowany obrazek i paski odporności na żywioły."""

from pathlib import Path

from PySide6.QtCore import QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QImage, QMovie, QPainter
from PySide6.QtWidgets import QGridLayout, QLabel, QSizePolicy, QWidget

from ..core.models import ELEMENTS, Monster
from ..core.monsters import ELEMENT_NAMES
from . import theme

ELEMENT_ICONS = {
    "physical": "⚔",
    "earth": "🌿",
    "fire": "🔥",
    "energy": "⚡",
    "ice": "❄",
    "holy": "✨",
    "death": "💀",
}
WEAK_COLOR = "#81c784"  # potwór słaby na żywioł: tym warto bić
STRONG_COLOR = "#ef5350"  # odporny: tym nie bić
BAR_MAX = 200  # pasek pokazuje 0-200%; 100% to zwykłe obrażenia

# Prostokąt postaci (bez przezroczystych brzegów) dla każdego pliku, liczony raz.
_crop_cache: dict[str, QRect] = {}


def _opaque_rect(image: QImage) -> QRect:
    left, top, right, bottom = image.width(), image.height(), -1, -1
    for y in range(image.height()):
        for x in range(image.width()):
            if image.pixelColor(x, y).alpha() > 0:
                left, top = min(left, x), min(top, y)
                right, bottom = max(right, x), max(bottom, y)
    if right < 0:
        return image.rect()
    return QRect(left, top, right - left + 1, bottom - top + 1)


def _animation_crop(path: Path) -> QRect:
    """Wspólny prostokąt postaci ze wszystkich klatek, żeby obrazek nie „skakał” w animacji."""
    key = str(path)
    if key not in _crop_cache:
        movie = QMovie(key)
        box = QRect()
        for frame in range(max(movie.frameCount(), 1)):
            movie.jumpToFrame(frame)
            image = movie.currentImage().convertToFormat(QImage.Format.Format_ARGB32)
            if not image.isNull():
                box = box.united(_opaque_rect(image))
        _crop_cache[key] = box if box.isValid() else QRect(0, 0, 64, 64)
    return _crop_cache[key]


class AnimatedSprite(QWidget):
    """Animowany obrazek potwora (GIF z wiki), przycięty do postaci i powiększony do rozmiaru widżetu.

    QMovie odtwarza GIF-a; my tylko rysujemy jego bieżącą klatkę. Bez wygładzania,
    bo to grafika pikselowa i po rozmyciu wyglądałaby gorzej.
    """

    def __init__(self, size: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._movie: QMovie | None = None
        self._crop = QRect()
        # Przezroczysty dla myszy: klik i dymek obsługuje rodzic (np. kafelek).
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def set_path(self, path: Path | None) -> None:
        if self._movie is not None:
            self._movie.stop()
            self._movie.deleteLater()
            self._movie = None
        if path is not None:
            self._crop = _animation_crop(path)
            self._movie = QMovie(str(path), parent=self)
            self._movie.frameChanged.connect(self.update)
            self._movie.start()
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802 (nazwa z Qt)
        return self.size()

    def paintEvent(self, event) -> None:  # noqa: N802 (nazwa z Qt)
        painter = QPainter(self)
        if self._movie is None:
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "🐾")
            return
        frame = self._movie.currentImage().copy(self._crop)
        if frame.isNull():
            return
        scale = min(self.width() / frame.width(), self.height() / frame.height())
        w, h = frame.width() * scale, frame.height() * scale
        # Postać na środku i przy dolnej krawędzi, jak stoi w grze.
        target = QRectF((self.width() - w) / 2, self.height() - h, w, h)
        painter.drawImage(target, frame)


class _Bar(QWidget):
    """Pasek 0-200% z kreską na 100% (zwykłe obrażenia)."""

    def __init__(self, percent: int, color: str) -> None:
        super().__init__()
        self._percent = percent
        self._color = QColor(color)
        self.setFixedHeight(10)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def paintEvent(self, event) -> None:  # noqa: N802 (nazwa z Qt)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.SURFACE))
        painter.drawRoundedRect(QRectF(self.rect()), 4, 4)
        width = self.width() * min(self._percent, BAR_MAX) / BAR_MAX
        if width > 0:
            painter.setBrush(self._color)
            painter.drawRoundedRect(QRectF(0, 0, width, self.height()), 4, 4)
        middle = self.width() / 2
        painter.setBrush(QColor(theme.TEXT))
        painter.drawRect(QRectF(middle - 0.5, 0, 1, self.height()))


def element_verdict(percent: int) -> tuple[str, str]:
    """(opis, kolor) dla procentu obrażeń od żywiołu."""
    if percent > 100:
        return f"+{percent - 100}% · słaby", WEAK_COLOR
    if percent == 0:
        return "odporny (0%)", STRONG_COLOR
    if percent < 100:
        return f"−{100 - percent}% · mocny", STRONG_COLOR
    return "normalnie", theme.MUTED


class ElementBars(QWidget):
    """Żywioły od najlepszego do najgorszego: ikona, nazwa, pasek i opis słowami."""

    def __init__(self, monster: Monster) -> None:
        super().__init__()
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(4)
        rows = sorted(ELEMENTS, key=lambda e: -monster.elements.get(e, 100))
        best = rows[0]
        if monster.elements.get(best, 100) > 100:
            hint = QLabel(f"Najlepiej bić: {ELEMENT_ICONS[best]} {ELEMENT_NAMES[best]}")
            hint.setStyleSheet(f"color: {WEAK_COLOR}; font-weight: 600;")
            grid.addWidget(hint, 0, 0, 1, 3)
        for row, element in enumerate(rows, start=1):
            percent = monster.elements.get(element, 100)
            text, color = element_verdict(percent)
            name = QLabel(f"{ELEMENT_ICONS[element]} {ELEMENT_NAMES[element]}")
            verdict = QLabel(text)
            verdict.setStyleSheet(f"color: {color};")
            grid.addWidget(name, row, 0)
            grid.addWidget(_Bar(percent, color if percent != 100 else theme.MUTED), row, 1)
            grid.addWidget(verdict, row, 2)
        grid.setColumnStretch(1, 1)
