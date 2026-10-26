"""Siatka potworów: animowane obrazki po kilka w rzędzie.

Potworów jest ok. 2200, więc nie robimy widżetu na każdego. QListView rysuje
tylko widoczne kafelki (delegat), a SpriteAnimator trzyma animacje (QMovie)
tylko dla tych, które są teraz na ekranie. Brakujące obrazki pobiera w tle.
"""

import threading
import time
from collections import deque
from pathlib import Path

from PySide6.QtCore import QAbstractListModel, QModelIndex, QObject, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QImage, QMovie, QPainter
from PySide6.QtWidgets import QListView, QStyle, QStyledItemDelegate, QStyleOptionViewItem

from ..core.models import Monster
from ..core.monsters import describe, ensure_image, image_path
from . import theme
from .monster_widgets import animation_crop

COLUMNS = 4
TILE_HEIGHT = 122
SPRITE_SIZE = 56
FRAME_MS = 100  # co tyle odświeżamy widoczne kafelki (GIF-y z wiki mają klatki co 100-200 ms)
FORGET_AFTER = 3.0  # sekundy: animacja kafelka, którego nie widać, jest zwalniana


class _Loaded(QObject):
    loaded = Signal()


class SpriteAnimator(QObject):
    """Bieżące klatki animacji obrazków (potworów, przedmiotów) widocznych na ekranie.

    Obrazek to plik folder/<key>.gif; brakujący pobieramy w tle z podanego adresu.
    """

    def __init__(self, folder: Path, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._folder = folder
        self._movies: dict[str, tuple[QMovie, QRect]] = {}
        self._used: dict[str, float] = {}
        # Pobieranie: kolejka i zbiór „już zlecone”, żeby nie pobierać dwa razy (ani bez końca po błędzie).
        self._queue: deque[tuple[str, str]] = deque()
        self._requested: set[str] = set()
        self._lock = threading.Lock()
        self._worker: threading.Thread | None = None
        self._signals = _Loaded(self)
        self.loaded = self._signals.loaded

    def frame(self, key: str, url: str | None) -> QImage | None:
        """Bieżąca klatka (przycięta do postaci) albo None, gdy obrazka jeszcze nie ma."""
        self._used[key] = time.monotonic()
        entry = self._movies.get(key)
        if entry is None:
            path = image_path(self._folder, key)
            if path is None:
                self._request(key, url)
                return None
            movie = QMovie(str(path), parent=self)
            movie.start()
            entry = self._movies[key] = (movie, animation_crop(path))
        movie, crop = entry
        image = movie.currentImage()
        return None if image.isNull() else image.copy(crop)

    def forget_unused(self) -> None:
        """Zwalnia animacje kafelków, których dawno nie rysowaliśmy (przewinięte poza ekran)."""
        now = time.monotonic()
        for monster_id in [i for i, t in self._used.items() if now - t > FORGET_AFTER]:
            del self._used[monster_id]
            entry = self._movies.pop(monster_id, None)
            if entry is not None:
                entry[0].stop()
                entry[0].deleteLater()

    def _request(self, key: str, url: str | None) -> None:
        if url is None or key in self._requested:
            return
        self._requested.add(key)
        with self._lock:
            self._queue.append((key, url))
            if self._worker is None or not self._worker.is_alive():
                # daemon=True: zamknięcie programu nie czeka na pobieranie.
                self._worker = threading.Thread(target=self._download_all, daemon=True, name="sprites")
                self._worker.start()

    def _download_all(self) -> None:
        while True:
            with self._lock:
                if not self._queue:
                    self._worker = None
                    return
                # Najpierw ostatnio zlecone: to te, które użytkownik właśnie ogląda.
                key, url = self._queue.pop()
            try:
                ensure_image(self._folder, key, url)
            except (OSError, ValueError):
                continue  # brak obrazka: zostaje łapka, drugi raz nie próbujemy (_requested)
            self.loaded.emit()  # sygnał z wątku w tle trafia do okna przez kolejkę Qt


class MonsterModel(QAbstractListModel):
    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._monsters: list[Monster] = []

    def set_monsters(self, monsters: list[Monster]) -> None:
        self.beginResetModel()
        self._monsters = monsters
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802, B008 (nazwa i domyślny argument jak w Qt)
        return 0 if parent.isValid() else len(self._monsters)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid():
            return None
        monster = self._monsters[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return monster.name
        if role == Qt.ItemDataRole.UserRole:
            return monster
        if role == Qt.ItemDataRole.ToolTipRole:
            return "\n".join([monster.name, *describe(monster)])
        return None


def short_number(value: int) -> str:
    """Krótki zapis do małego kafelka: 950, 8.2k, 82k, 1.5M."""
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}".rstrip("0").rstrip(".") + "M"
    if value >= 10_000:
        return f"{value // 1000}k"
    if value >= 1000:
        return f"{value / 1000:.1f}".rstrip("0").rstrip(".") + "k"
    return str(value)


class MonsterDelegate(QStyledItemDelegate):
    """Rysuje kafelek: animowany potwór, nazwa i HP/exp."""

    def __init__(self, animator: SpriteAnimator, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._animator = animator

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:  # noqa: N802 (nazwa z Qt)
        # Kafelek wypełnia całe pole siatki (jej szerokość zależy od szerokości okna).
        grid = self.parent().gridSize() if isinstance(self.parent(), QListView) else QSize()
        return grid if grid.isValid() else QSize(SPRITE_SIZE + 16, TILE_HEIGHT)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        monster: Monster = index.data(Qt.ItemDataRole.UserRole)
        tile = QRectF(option.rect).adjusted(3, 3, -3, -3)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        hovered = option.state & QStyle.StateFlag.State_MouseOver
        painter.setPen(QColor(theme.ACCENT if hovered else theme.BORDER))
        painter.setBrush(QColor(theme.SURFACE))
        painter.drawRoundedRect(tile, 8, 8)

        sprite = QRectF(tile.center().x() - SPRITE_SIZE / 2, tile.top() + 6, SPRITE_SIZE, SPRITE_SIZE)
        frame = self._animator.frame(monster.id, monster.image_url)
        if frame is None:
            painter.setPen(QColor(theme.MUTED))
            painter.drawText(sprite, Qt.AlignmentFlag.AlignCenter, "🐾")
        else:
            scale = min(sprite.width() / frame.width(), sprite.height() / frame.height())
            w, h = frame.width() * scale, frame.height() * scale
            # Postać na środku i przy dolnej krawędzi pola, jak stoi w grze.
            painter.drawImage(QRectF(sprite.center().x() - w / 2, sprite.bottom() - h, w, h), frame)

        font = QFont(option.font)
        font.setPixelSize(11)
        painter.setFont(font)
        text_box = QRectF(tile.left() + 4, sprite.bottom() + 4, tile.width() - 8, 16)
        name = painter.fontMetrics().elidedText(monster.name, Qt.TextElideMode.ElideRight, int(text_box.width()))
        painter.setPen(QColor(theme.TEXT))
        painter.drawText(text_box, Qt.AlignmentFlag.AlignCenter, name)
        font.setPixelSize(10)
        painter.setFont(font)
        painter.setPen(QColor(theme.MUTED))
        painter.drawText(text_box.translated(0, 15), Qt.AlignmentFlag.AlignCenter, f"HP {short_number(monster.hp)}")
        painter.drawText(text_box.translated(0, 28), Qt.AlignmentFlag.AlignCenter, f"exp {short_number(monster.exp)}")
        painter.restore()


class MonsterGrid(QListView):
    """Siatka COLUMNS kafelków w rzędzie; szerokość kafelka dopasowuje się do okna."""

    monster_clicked = Signal(object)

    def __init__(self, sprites_dir: Path, parent=None) -> None:
        super().__init__(parent)
        self.animator = SpriteAnimator(sprites_dir, self)
        self.animator.loaded.connect(self.viewport().update)
        self._model = MonsterModel(self)
        self.setModel(self._model)
        self.setItemDelegate(MonsterDelegate(self.animator, self))
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setMovement(QListView.Movement.Static)
        self.setUniformItemSizes(True)
        self.setMouseTracking(True)  # podświetlenie kafelka pod myszą
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self.verticalScrollBar().setSingleStep(24)
        self.setFrameShape(QListView.Shape.NoFrame)
        self.setStyleSheet("QListView { background: transparent; }")
        self.clicked.connect(lambda index: self.monster_clicked.emit(index.data(Qt.ItemDataRole.UserRole)))

        # Odświeżanie animacji tylko wtedy, gdy siatka jest na ekranie.
        self._timer = QTimer(self, interval=FRAME_MS)
        self._timer.timeout.connect(self.viewport().update)
        self._cleanup = QTimer(self, interval=1000)
        self._cleanup.timeout.connect(self.animator.forget_unused)

    def set_monsters(self, monsters: list[Monster]) -> None:
        self._model.set_monsters(monsters)
        self.scrollToTop()

    def resizeEvent(self, event) -> None:  # noqa: N802 (nazwa z Qt)
        super().resizeEvent(event)
        # -1: przy równym podziale Qt potrafi zmieścić tylko COLUMNS - 1 kafelków w rzędzie.
        width = max((self.viewport().width() - 1) // COLUMNS, 60)
        self.setGridSize(QSize(width, TILE_HEIGHT))

    def showEvent(self, event) -> None:  # noqa: N802 (nazwa z Qt)
        super().showEvent(event)
        self._timer.start()
        self._cleanup.start()

    def hideEvent(self, event) -> None:  # noqa: N802 (nazwa z Qt)
        super().hideEvent(event)
        self._timer.stop()
        self._cleanup.stop()
