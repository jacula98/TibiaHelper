"""Zakładka „Przedmioty”: lista z wyszukiwarką i strona przedmiotu.

Strona przedmiotu odpowiada na pytania gracza: komu to sprzedać i za ile
(z NPC na mapie), gdzie to kupić i z jakich potworów to wypada.
Dane są z TibiaWiki, nazwy po angielsku (tak jak w grze).
"""

import threading
from html import escape
from pathlib import Path

from PySide6.QtCore import QAbstractListModel, QModelIndex, QObject, QRectF, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont, QPainter
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QPushButton,
    QScrollArea,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from ..core.issues import item_issue_url
from ..core.filters import hide_groups
from ..core.items import ITEM_FILTERS, ITEM_SORTS, Drop, effective_price, sort_items
from ..core.models import Item, MapPoint, Monster, Npc, Trade
from ..core.monsters import download_items, image_path, item_key
from . import theme
from .map_window import MapPanel
from .filter_button import FilterButton
from .monster_grid import SpriteAnimator
from .monster_pages import RARITY_NAMES
from .monster_widgets import AnimatedSprite
from .sprites import display_sprite
from .theme import report_button

ROW_HEIGHT = 46
ICON_SIZE = 32  # obrazki przedmiotów z wiki mają 32x32 px
NPC_SPRITE = 36
MAP_HEIGHT = 300
FRAME_MS = 150
DROP_LINK_PREFIX = "mon:"


def _gp(value: int | None) -> str:
    return f"{value:,} gp".replace(",", " ") if value is not None else "?"


def item_subtitle(item: Item) -> str:
    """Druga linia na liście: najważniejsze dla gracza, czyli komu i za ile sprzedać."""
    if item.sell_to:
        names = ", ".join(t.npc for t in item.sell_to[:3]) + (" …" if len(item.sell_to) > 3 else "")
        return f"sprzedasz za {_gp(item.value)}: {names}"
    if item.buy_from:
        return f"kupisz za {_gp(item.price)}"
    return item.category or ""


class ItemModel(QAbstractListModel):
    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._items: list[Item] = []

    def set_items(self, items: list[Item]) -> None:
        self.beginResetModel()
        self._items = items
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802, B008 (nazwa i domyślny argument jak w Qt)
        return 0 if parent.isValid() else len(self._items)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid():
            return None
        item = self._items[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return item.name
        if role == Qt.ItemDataRole.UserRole:
            return item
        return None


class ItemDelegate(QStyledItemDelegate):
    """Wiersz listy: obrazek, nazwa i „sprzedasz za … : NPC”."""

    def __init__(self, animator: SpriteAnimator, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._animator = animator

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:  # noqa: N802 (nazwa z Qt)
        return QSize(option.rect.width(), ROW_HEIGHT)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        item: Item = index.data(Qt.ItemDataRole.UserRole)
        row = QRectF(option.rect).adjusted(0, 2, -2, -2)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        hovered = option.state & QStyle.StateFlag.State_MouseOver
        painter.setPen(QColor(theme.ACCENT if hovered else theme.BORDER))
        painter.setBrush(QColor(theme.SURFACE))
        painter.drawRoundedRect(row, 6, 6)

        icon_box = QRectF(row.left() + 6, row.center().y() - ICON_SIZE / 2, ICON_SIZE, ICON_SIZE)
        frame = self._animator.frame(item_key(item.name), item.image_url)
        if frame is None:
            painter.setPen(QColor(theme.MUTED))
            painter.drawText(icon_box, Qt.AlignmentFlag.AlignCenter, "🎒")
        else:
            scale = min(ICON_SIZE / frame.width(), ICON_SIZE / frame.height(), 1.0)
            w, h = frame.width() * scale, frame.height() * scale
            painter.drawImage(QRectF(icon_box.center().x() - w / 2, icon_box.center().y() - h / 2, w, h), frame)

        text_left = icon_box.right() + 8
        width = int(row.right() - text_left - 6)
        font = QFont(option.font)
        font.setPixelSize(13)
        painter.setFont(font)
        painter.setPen(QColor(theme.TEXT))
        name = painter.fontMetrics().elidedText(item.name, Qt.TextElideMode.ElideRight, width)
        painter.drawText(QRectF(text_left, row.top() + 4, width, 18), Qt.AlignmentFlag.AlignVCenter, name)
        font.setPixelSize(11)
        painter.setFont(font)
        painter.setPen(QColor(theme.MUTED))
        sub = painter.fontMetrics().elidedText(item_subtitle(item), Qt.TextElideMode.ElideRight, width)
        painter.drawText(QRectF(text_left, row.top() + 22, width, 16), Qt.AlignmentFlag.AlignVCenter, sub)
        painter.restore()


class ItemListPage(QWidget):
    item_selected = Signal(object)
    back_requested = Signal()

    def __init__(self, items_dir: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._items: list[Item] = []
        self._search = QLineEdit(placeholderText="Szukaj przedmiotu, np. fish fin…", clearButtonEnabled=True)
        self._sort = QComboBox()
        self._sort.addItems(list(ITEM_SORTS))
        self._sort.setToolTip("Sortowanie i filtr")
        self._animator = SpriteAnimator(items_dir, self)
        self._model = ItemModel(self)
        self._list = QListView()
        self._list.setModel(self._model)
        self._list.setItemDelegate(ItemDelegate(self._animator, self))
        self._list.setUniformItemSizes(True)
        self._list.setMouseTracking(True)
        self._list.setFrameShape(QListView.Shape.NoFrame)
        self._list.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self._list.setStyleSheet("QListView { background: transparent; }")
        # Wiersze mieszczą się w szerokości okna (długie nazwy są ucinane), poziomy pasek tylko przeszkadza.
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.clicked.connect(lambda index: self.item_selected.emit(index.data(Qt.ItemDataRole.UserRole)))
        self._animator.loaded.connect(self._list.viewport().update)
        # Część obrazków to animacje; odświeżamy widoczne wiersze, ale tylko gdy lista jest na ekranie.
        self._timer = QTimer(self, interval=FRAME_MS)
        self._timer.timeout.connect(self._list.viewport().update)
        self._timer.timeout.connect(self._animator.forget_unused)
        self._empty = QLabel(alignment=Qt.AlignmentFlag.AlignCenter, wordWrap=True)

        back = QPushButton("← Menu")
        back.clicked.connect(self.back_requested)
        top = QHBoxLayout()
        top.addWidget(back)
        top.addStretch(1)
        self._filters = FilterButton(list(ITEM_FILTERS))
        self._filters.changed.connect(self._refresh)
        top.addWidget(self._filters)
        filters = QHBoxLayout()
        filters.addWidget(self._search, 1)
        filters.addWidget(self._sort)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(top)
        layout.addLayout(filters)
        layout.addWidget(self._list, 1)
        layout.addWidget(self._empty, 1)

        self._search.textChanged.connect(self._refresh)
        self._sort.currentTextChanged.connect(self._refresh)

    def set_items(self, items: dict[str, Item]) -> None:
        self._items = list(items.values())
        self._refresh()

    def _refresh(self) -> None:
        text = self._search.text().strip().lower()
        found = [i for i in self._items if text in i.name.lower()]
        shown = sort_items(hide_groups(found, ITEM_FILTERS, self._filters.shown()), self._sort.currentText())
        self._model.set_items(shown)
        self._list.scrollToTop()
        self._empty.setText("Brak przedmiotów w danych." if not self._items else "Nic nie pasuje do wyszukiwania i filtrów.")
        self._list.setVisible(bool(shown))
        self._empty.setVisible(not shown)

    def showEvent(self, event) -> None:  # noqa: N802 (nazwa z Qt)
        super().showEvent(event)
        self._timer.start()

    def hideEvent(self, event) -> None:  # noqa: N802 (nazwa z Qt)
        super().hideEvent(event)
        self._timer.stop()


class _TradeRow(QFrame):
    """NPC, który kupuje albo sprzedaje: postać, imię i miasto, cena. Klik pokazuje go na mapie."""

    clicked = Signal(object)

    def __init__(self, trade: Trade, npc: Npc | None, price: int | None, image: Path | None) -> None:
        super().__init__()
        self.setObjectName("tradeRow")
        self.npc = npc
        self._sprite = AnimatedSprite(NPC_SPRITE)
        self._sprite.set_path(image)
        where = f" · {npc.city}" if npc and npc.city else ""
        name = QLabel(f"{trade.npc}{where}", textFormat=Qt.TextFormat.PlainText)
        price_label = QLabel(_gp(price), textFormat=Qt.TextFormat.PlainText)
        price_label.setStyleSheet(f"color: {theme.ACCENT}; font-weight: 600;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 8, 2)
        layout.addWidget(self._sprite)
        layout.addWidget(name, 1)
        if npc is None:
            hint = QLabel("brak na mapie", objectName="muted")
            layout.addWidget(hint)
        else:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setToolTip("Kliknij, żeby zobaczyć, gdzie stoi")
        layout.addWidget(price_label)

    def set_image(self, image: Path | None) -> None:
        self._sprite.set_path(image)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (nazwa z Qt)
        if event.button() == Qt.MouseButton.LeftButton and self.npc is not None:
            self.clicked.emit(self.npc)


class _Loader(QObject):
    loaded = Signal(str)  # nazwa przedmiotu, dla którego pobierano obrazki


class ItemPage(QWidget):
    back_requested = Signal()
    monster_requested = Signal(object)

    def __init__(
        self, items_dir: Path, npcs_dir: Path, sprites_dir: Path, maps_dir: Path, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._items_dir = items_dir
        self._npcs_dir = npcs_dir
        self._sprites_dir = sprites_dir
        self._npcs: dict[str, Npc] = {}
        self._monsters: dict[str, Monster] = {}
        self._drops: dict[str, list[Drop]] = {}
        self._data_version = 0
        self.item: Item | None = None
        self._rows: list[_TradeRow] = []
        self._loader = _Loader(self)
        self._loader.loaded.connect(self._on_images_loaded)

        self._back = QPushButton("← Wstecz")
        self._back.clicked.connect(self.back_requested)
        top = QHBoxLayout()
        top.addWidget(self._back)
        top.addStretch(1)

        self._sprite = AnimatedSprite(48)
        self._header = QLabel(wordWrap=True, textFormat=Qt.TextFormat.RichText)
        header = QHBoxLayout()
        header.addWidget(self._sprite)
        header.addWidget(self._header, 1)

        # Sekcje NPC budujemy od nowa dla każdego przedmiotu, w tym miejscu kolumny.
        self._trades = QVBoxLayout()
        self._trades.setSpacing(4)
        self._map = MapPanel(maps_dir)
        self._map.setFixedHeight(MAP_HEIGHT)
        self._map.hide()
        self._drops_label = QLabel(wordWrap=True, textFormat=Qt.TextFormat.RichText)
        self._drops_label.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
        self._drops_label.linkActivated.connect(self._on_drop_link)
        self._source = QLabel(wordWrap=True, textFormat=Qt.TextFormat.RichText)
        self._source.setOpenExternalLinks(True)

        content = QWidget()
        column = QVBoxLayout(content)
        column.setContentsMargins(0, 0, 4, 0)
        column.addLayout(header)
        column.addLayout(self._trades)
        column.addWidget(self._map)
        column.addWidget(self._drops_label)
        column.addWidget(self._source)
        column.addStretch(1)

        self._scroll = QScrollArea(widgetResizable=True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setWidget(content)

        report = report_button()
        report.clicked.connect(self._report_issue)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(top)
        layout.addWidget(self._scroll, 1)
        layout.addWidget(report, 0, Qt.AlignmentFlag.AlignRight)

    def set_data(
        self, npcs: dict[str, Npc], monsters: dict[str, Monster], drops: dict[str, list[Drop]], data_version: int
    ) -> None:
        self._npcs, self._monsters, self._drops, self._data_version = npcs, monsters, drops, data_version

    def set_back_text(self, text: str) -> None:
        self._back.setText(text)

    def show_item(self, item: Item) -> None:
        self.item = item
        self._sprite.set_path(image_path(self._items_dir, item_key(item.name)))
        self._header.setText(header_html(item))
        self._build_trades(item)
        self._map.hide()
        self._drops_label.setText(drops_html(self._drops.get(item.name.lower(), []), self._monster_icon))
        self._source.setText(
            f'<span style="color: {theme.MUTED};">Źródło: <a href="{escape(item.source_url, quote=True)}">'
            "TibiaWiki</a> (CC BY-SA 4.0) · obrazki © CipSoft</span>"
        )
        self._scroll.verticalScrollBar().setValue(0)
        self._load_images(item)

    # --- komu sprzedać / gdzie kupić ------------------------------------------------

    def _build_trades(self, item: Item) -> None:
        while self._trades.count():
            widget = self._trades.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        self._rows = []
        sections = (
            ("SPRZEDASZ U NPC (NPC KUPUJE)", item.sell_to, item.value),
            ("KUPISZ U NPC", item.buy_from, item.price),
        )
        if not item.sell_to and not item.buy_from:
            self._trades.addWidget(_section_label("NPC"))
            self._trades.addWidget(QLabel("Żaden NPC tego nie kupuje ani nie sprzedaje.", objectName="muted"))
        for title, trades, default in sections:
            if not trades:
                continue
            self._trades.addWidget(_section_label(title))
            # Najlepsza cena na górze: przy sprzedaży najwyższa, przy kupnie najniższa.
            ordered = sorted(trades, key=lambda t: effective_price(t, default) or 0, reverse=trades is item.sell_to)
            for trade in ordered:
                npc = self._npcs.get(trade.npc.lower())
                row = _TradeRow(trade, npc, effective_price(trade, default), self._npc_image(npc))
                row.clicked.connect(lambda npc, trades=trades: self._show_npc(npc, trades))
                self._rows.append(row)
                self._trades.addWidget(row)

    def _npc_image(self, npc: Npc | None) -> Path | None:
        return image_path(self._npcs_dir, item_key(npc.name)) if npc and npc.image_url else None

    def _show_npc(self, npc: Npc, trades: list[Trade]) -> None:
        """Mapa z wszystkimi NPC z tej sekcji; wyśrodkowana na klikniętym."""
        points = []
        for trade in trades:
            other = self._npcs.get(trade.npc.lower())
            if other is not None:
                points.append(MapPoint(x=other.x, y=other.y, z=other.z, label=other.name, kind="npc"))
        focus = next(p for p in points if p.label == npc.name)
        self._map.show()
        self._map.show_points(points, focus)
        # Po pokazaniu mapy przewijamy tak, żeby była widoczna.
        QTimer.singleShot(0, lambda: self._scroll.ensureWidgetVisible(self._map))

    # --- skąd wypada ------------------------------------------------------------------

    def _monster_icon(self, monster_id: str) -> Path | None:
        return display_sprite(self._sprites_dir, monster_id)

    def _on_drop_link(self, link: str) -> None:
        monster = self._monsters.get(link.removeprefix(DROP_LINK_PREFIX))
        if monster is not None:
            self.monster_requested.emit(monster)

    # --- obrazki w tle ------------------------------------------------------------------

    def _load_images(self, item: Item) -> None:
        wanted_items = {item.name: item.image_url} if item.image_url else {}
        npcs = {}
        for trade in (*item.sell_to, *item.buy_from):
            npc = self._npcs.get(trade.npc.lower())
            if npc is not None and npc.image_url and self._npc_image(npc) is None:
                npcs[npc.name] = npc.image_url
        if image_path(self._items_dir, item_key(item.name)) is not None:
            wanted_items = {}
        if not wanted_items and not npcs:
            return

        def run() -> None:
            done = download_items(self._items_dir, wanted_items) if wanted_items else []
            done += download_items(self._npcs_dir, npcs) if npcs else []
            if done:
                self._loader.loaded.emit(item.name)

        threading.Thread(target=run, daemon=True, name="item-images").start()

    def _on_images_loaded(self, name: str) -> None:
        if self.item is None or self.item.name != name:
            return
        self._sprite.set_path(image_path(self._items_dir, item_key(name)))
        for row in self._rows:
            row.set_image(self._npc_image(row.npc))

    def _report_issue(self) -> None:
        if self.item is not None:
            QDesktopServices.openUrl(QUrl(item_issue_url(self.item, self._data_version)))


def _section_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("sectionTitle")
    return label


def header_html(item: Item) -> str:
    """Nazwa, rodzaj i waga. Tekst z danych przechodzi przez escape."""
    details = []
    if item.category:
        details.append(escape(item.category))
    if item.weight is not None:
        details.append(f"{item.weight:.2f} oz")
    return (
        f'<span style="font-size: 18px; font-weight: 600;">{escape(item.name)}</span><br>'
        f'<span style="color: {theme.MUTED};">{" · ".join(details)}</span>'
    )


def drops_html(drops: list[Drop], icon) -> str:
    """„Wypada z”: potwory jako linki (klik otwiera stronę potwora), od najczęstszego dropu."""
    if not drops:
        return ""
    lines = []
    for drop in drops:
        path = icon(drop.monster.id)
        image = f'<img src="{path.as_uri()}" width="24" height="24"> ' if path else ""
        rarity = f' <span style="color: {theme.MUTED};">({RARITY_NAMES[drop.rarity]})</span>' if drop.rarity else ""
        link = f'<a href="{DROP_LINK_PREFIX}{escape(drop.monster.id, quote=True)}">{escape(drop.monster.name)}</a>'
        lines.append(f"{image}{link}{rarity}")
    title = f'<span style="color: {theme.MUTED}; font-size: 11px; font-weight: 600;">WYPADA Z POTWORÓW</span>'
    return title + "<br>" + "<br>".join(lines)
