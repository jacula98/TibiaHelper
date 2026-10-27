"""Zakładka „Potwory”: lista z wyszukiwarką i strona jednego potwora.

Dane są po angielsku, prosto z TibiaWiki (nazwy, loot, miejsca), bo tak
nazywa je gra. Polskie są tylko nagłówki.
"""

import threading
from collections.abc import Callable
from html import escape
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QImage, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QComboBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..core.i18n import N_, tr
from ..core.models import Item, Monster
from ..core.filters import hide_groups
from ..core.monsters import MONSTER_FILTERS, SORTS, download_items, download_missing, image_path, item_key, sort_monsters, sprite_path
from ..core.issues import monster_issue_url
from ..core.mapdata import floor_label
from ..core.spawns import SOURCE_NOTE, Place, Spawns, places
from .map_window import MapPanel, spawn_icon
from .filter_button import FilterButton
from .monster_grid import MonsterGrid
from .monster_widgets import AnimatedSprite, ElementBars
from .sprites import display_sprite
from . import theme
from .theme import report_button

PAGE_SPRITE = 64
ITEM_LINK_PREFIX = "item:"
LOOT_ICON = 32  # obrazki przedmiotów z wiki mają 32x32 px
SPAWN_MAP_HEIGHT = 320
# N_: tłumaczymy dopiero przy pokazaniu, tr(RARITY_NAMES[...]) (zob. core/i18n.py).
RARITY_NAMES = {
    "always": N_("zawsze"),
    "common": N_("częsty"),
    "uncommon": N_("nieczęsty"),
    "semi-rare": N_("półrzadki"),
    "rare": N_("rzadki"),
    "very rare": N_("bardzo rzadki"),
}


def _thousands(value: int) -> str:
    return f"{value:,}".replace(",", " ")


class MonsterListPage(QWidget):
    monster_selected = Signal(object)
    back_requested = Signal()

    def __init__(self, sprites_dir: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.monsters: list[Monster] = []
        self._search = QLineEdit(placeholderText=tr("Szukaj potwora…"), clearButtonEnabled=True)
        self._sort = QComboBox()
        # Na liście tłumaczenie, a w danych pozycji polska nazwa, po której szuka sort_monsters.
        for name in SORTS:
            self._sort.addItem(tr(name), name)
        self._sort.setToolTip(tr("Sortowanie"))
        self._grid = MonsterGrid(sprites_dir)
        self._empty = QLabel(alignment=Qt.AlignmentFlag.AlignCenter, wordWrap=True)

        back = QPushButton(tr("← Menu"))
        back.clicked.connect(self.back_requested)
        top = QHBoxLayout()
        top.addWidget(back)
        top.addStretch(1)
        self._filters = FilterButton(list(MONSTER_FILTERS))
        self._filters.changed.connect(self._refresh)
        top.addWidget(self._filters)
        filters = QHBoxLayout()
        filters.addWidget(self._search, 1)
        filters.addWidget(self._sort)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(top)
        layout.addLayout(filters)
        layout.addWidget(self._grid, 1)
        layout.addWidget(self._empty, 1)

        self._search.textChanged.connect(self._refresh)
        self._sort.currentIndexChanged.connect(self._refresh)
        self._grid.monster_clicked.connect(self.monster_selected)

    def set_monsters(self, monsters: dict[str, Monster]) -> None:
        self.monsters = list(monsters.values())
        self._refresh()

    def _refresh(self) -> None:
        text = self._search.text().strip().lower()
        found = [m for m in self.monsters if text in m.name.lower()]
        shown = sort_monsters(hide_groups(found, MONSTER_FILTERS, self._filters.shown()), self._sort.currentData())
        self._grid.set_monsters(shown)
        self._empty.setText(
            tr("Brak potworów w danych.") if not self.monsters else tr("Nic nie pasuje do wyszukiwania i filtrów.")
        )
        self._grid.setVisible(bool(shown))
        self._empty.setVisible(not shown)


class _SpriteLoader(QObject):
    loaded = Signal(str)  # id potwora


class MonsterPage(QWidget):
    """Szczegóły jednego potwora. Przycisk wstecz wraca tam, skąd przyszliśmy (lista albo quest)."""

    back_requested = Signal()
    item_requested = Signal(object)  # klik w przedmiot z lootu

    def __init__(self, sprites_dir: Path, maps_dir: Path, items_dir: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._sprites_dir = sprites_dir
        self._items_dir = items_dir
        self._items: dict[str, Item] = {}
        self._data_version = 0
        self._spawns = Spawns()
        self.monster: Monster | None = None
        self._loader = _SpriteLoader(self)
        self._loader.loaded.connect(self._on_sprite_loaded)

        self._back = QPushButton(tr("← Wstecz"))
        self._back.clicked.connect(self.back_requested)
        top = QHBoxLayout()
        top.addWidget(self._back)
        top.addStretch(1)

        # Strona: nagłówek z animacją / żywioły (paski) / opis (HTML) / mapa / loot i źródło (HTML).
        self._sprite = AnimatedSprite(PAGE_SPRITE)
        self._header = _html_label()
        header = QHBoxLayout()
        header.addWidget(self._sprite)
        header.addWidget(self._header, 1)
        self._elements_title = QLabel(tr("CZYM BIĆ (OBRAŻENIA OD ŻYWIOŁÓW)"))
        self._elements_title.setObjectName("sectionTitle")
        self._elements: QWidget | None = None
        self._top = _html_label()
        self._map_title = QLabel(tr("MAPA WYSTĘPOWANIA"))
        self._map_title.setObjectName("sectionTitle")
        # Wybór expowiska: potwór bywa w wielu miejscach, mapa pokazuje to wybrane.
        self._places = QComboBox()
        self._places.setToolTip(tr("Miejsca od tego, gdzie jest najwięcej tych potworów"))
        self._places.currentIndexChanged.connect(self._on_place_selected)
        self._place_list: list[Place] = []
        self._map = MapPanel(maps_dir)
        self._map.setFixedHeight(SPAWN_MAP_HEIGHT)
        self._bottom = _html_label()
        # Loot ma linki do stron przedmiotów, więc linki obsługujemy sami (_on_link).
        self._bottom.setOpenExternalLinks(False)
        self._bottom.linkActivated.connect(self._on_link)

        content = QWidget()
        column = QVBoxLayout(content)
        column.setContentsMargins(0, 0, 4, 0)
        column.addLayout(header)
        column.addWidget(self._elements_title)
        self._elements_at = column.count()  # tu wstawiamy paski żywiołów konkretnego potwora
        column.addWidget(self._top)
        column.addWidget(self._map_title)
        column.addWidget(self._places)
        column.addWidget(self._map)
        column.addWidget(self._bottom)
        column.addStretch(1)

        scroll = QScrollArea(widgetResizable=True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        self._scroll = scroll
        self._column = column

        report = report_button()
        report.clicked.connect(self._report_issue)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(top)
        layout.addWidget(scroll, 1)
        layout.addWidget(report, 0, Qt.AlignmentFlag.AlignRight)

    def set_data_version(self, data_version: int) -> None:
        self._data_version = data_version

    def _report_issue(self) -> None:
        if self.monster is not None:
            QDesktopServices.openUrl(QUrl(monster_issue_url(self.monster, self._data_version)))

    def set_items(self, items: dict[str, Item]) -> None:
        self._items = items

    def set_spawns(self, spawns: Spawns) -> None:
        self._spawns = spawns

    def set_back_text(self, text: str) -> None:
        self._back.setText(text)

    def show_monster(self, monster: Monster) -> None:
        self.monster = monster
        if self._elements is not None:
            self._elements.deleteLater()
        self._elements = ElementBars(monster)
        self._column.insertWidget(self._elements_at, self._elements)
        self._render()
        self._scroll.verticalScrollBar().setValue(0)
        points = self._spawns.of(monster.id)
        for widget in (self._map_title, self._places, self._map):
            widget.setVisible(bool(points))
        if points:
            self._map.show_spawns(monster.name, points, tr(SOURCE_NOTE), self._spawn_icon())
            self._place_list = places(points)
            # blockSignals: wypełnianie listy nie ma przesuwać mapy przy każdym dodanym miejscu.
            self._places.blockSignals(True)
            self._places.clear()
            for number, place in enumerate(self._place_list, start=1):
                self._places.addItem(
                    tr(
                        "{number}. okolice {city} · {count} miejsc · piętro {floor}",
                        number=number,
                        city=place.city,
                        count=place.count,
                        floor=floor_label(place.z),
                    )
                )
            self._places.blockSignals(False)
            self._on_place_selected(0)
        need_sprite = monster.image_url is not None and sprite_path(self._sprites_dir, monster.id) is None
        # Obrazki przedmiotów z lootu tego potwora, których jeszcze nie ma na dysku.
        items = {
            loot.name: self._items[loot.name.lower()].image_url
            for loot in monster.loot
            if self._item_url(loot.name) and image_path(self._items_dir, item_key(loot.name)) is None
        }
        if need_sprite or items:

            def run() -> None:
                # Najpierw potwór (widać go na górze strony), potem przedmioty.
                if need_sprite and download_missing(self._sprites_dir, [monster]):
                    self._loader.loaded.emit(monster.id)
                if items and download_items(self._items_dir, items):
                    self._loader.loaded.emit(monster.id)

            threading.Thread(target=run, daemon=True, name="sprite").start()

    def _on_sprite_loaded(self, monster_id: str) -> None:
        if self.monster is not None and self.monster.id == monster_id:
            self._render()
            self._map.set_spawn_icon(self._spawn_icon())

    def _on_place_selected(self, index: int) -> None:
        if 0 <= index < len(self._place_list):
            place = self._place_list[index]
            self._map.focus_on(place.x, place.y, place.z)

    def _spawn_icon(self) -> QPixmap | None:
        """Obrazek potwora do mapy albo None (wtedy mapa ma same kropki)."""
        path = display_sprite(self._sprites_dir, self.monster.id) if self.monster else None
        image = QImage(str(path)) if path else QImage()
        return None if image.isNull() else spawn_icon(image)

    def _render(self) -> None:
        if self.monster is not None:
            self._sprite.set_path(sprite_path(self._sprites_dir, self.monster.id))
            self._header.setText(header_html(self.monster))
            self._top.setText(monster_html(self.monster))
            self._bottom.setText(loot_html(self.monster, self._item_icon, lambda name: name.lower() in self._items))

    def _item_url(self, name: str) -> str | None:
        item = self._items.get(name.lower())
        return item.image_url if item else None

    def _item_icon(self, name: str) -> Path | None:
        return image_path(self._items_dir, item_key(name)) if self._item_url(name) else None

    def _on_link(self, link: str) -> None:
        # Linki „item:N” to przedmioty z lootu; inne (np. TibiaWiki) otwiera przeglądarka.
        if link.startswith(ITEM_LINK_PREFIX):
            index = link.removeprefix(ITEM_LINK_PREFIX)
            if self.monster is not None and index.isdigit() and int(index) < len(self.monster.loot):
                item = self._items.get(self.monster.loot[int(index)].name.lower())
                if item is not None:
                    self.item_requested.emit(item)
        else:
            QDesktopServices.openUrl(QUrl(link))


def _html_label() -> QLabel:
    label = QLabel(wordWrap=True, textFormat=Qt.TextFormat.RichText)
    label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
    label.setOpenExternalLinks(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
    return label


def header_html(monster: Monster) -> str:
    """Nazwa, rodzaj i statystyki obok animacji. Każdy tekst z danych przechodzi przez escape."""
    tags = []
    if monster.boss:
        tags.append(escape(tr("boss")))
    if monster.bestiary_class:
        tags.append(escape(monster.bestiary_class))
    if monster.bestiary_level:
        tags.append(escape(tr("bestiariusz: {level}", level=monster.bestiary_level)))
    stats = [f"HP <b>{_thousands(monster.hp)}</b>", f"exp <b>{_thousands(monster.exp)}</b>"]
    if monster.armor is not None:
        stats.append(f"armor <b>{monster.armor}</b>")
    if monster.speed is not None:
        stats.append(f"speed <b>{monster.speed}</b>")
    return (
        f'<span style="font-size: 18px; font-weight: 600;">{escape(monster.name)}</span><br>'
        f'<span style="color: #9aa0a6;">{" · ".join(tags)}</span><br>{" · ".join(stats)}'
    )


def monster_html(monster: Monster) -> str:
    """Umiejętności i opis miejsc (pod paskami żywiołów)."""
    parts = []
    if monster.abilities:
        parts.append(_section(tr("UMIEJĘTNOŚCI")))
        parts.append("<br>".join(f"• {escape(a)}" for a in monster.abilities))
    if monster.location:
        parts.append(_section(tr("GDZIE WYSTĘPUJE")))
        parts.append(escape(monster.location))
    return "<br>".join(parts)


def loot_html(
    monster: Monster,
    icon: Callable[[str], Path | None] = lambda name: None,
    known: Callable[[str], bool] = lambda name: False,
) -> str:
    """Dolna część strony (pod mapą): loot z obrazkami przedmiotów i źródło.

    Przedmioty, które mamy w danych (known), są linkami „item:N” do ich strony.
    """
    parts = []
    if monster.loot:
        parts.append(_section("LOOT"))
        # Tabela: obrazek w pierwszej kolumnie, opis w drugiej, więc nazwy stoją równo.
        rows = []
        for index, item in enumerate(monster.loot):
            amount = f"{escape(item.amount)}× " if item.amount else ""
            name = escape(item.name)
            if known(item.name):
                name = f'<a href="{ITEM_LINK_PREFIX}{index}" style="color: {theme.TEXT};">{name}</a>'
            rarity = f' <span style="color: #9aa0a6;">({escape(tr(RARITY_NAMES[item.rarity]))})</span>' if item.rarity else ""
            path = icon(item.name)
            image = f'<img src="{path.as_uri()}" width="{LOOT_ICON}" height="{LOOT_ICON}">' if path else ""
            rows.append(
                f'<tr><td width="{LOOT_ICON + 6}" style="vertical-align: middle">{image}</td>'
                f'<td style="vertical-align: middle">{amount}{name}{rarity}</td></tr>'
            )
        parts.append(f'<table cellspacing="0" cellpadding="1">{"".join(rows)}</table>')

    parts.append(
        f'<span style="color: #9aa0a6;">{escape(tr("Źródło:"))} '
        f'<a href="{escape(monster.source_url, quote=True)}">TibiaWiki</a> (CC BY-SA 4.0) · '
        f'{escape(tr("obrazki © CipSoft"))}</span>'
    )
    return "<br>".join(parts)


def _section(title: str) -> str:
    return f'<br><span style="color: #9aa0a6; font-size: 11px; font-weight: 600;">{escape(title)}</span>'
