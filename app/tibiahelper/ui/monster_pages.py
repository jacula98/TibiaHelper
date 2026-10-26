"""Zakładka „Potwory”: lista z wyszukiwarką i strona jednego potwora.

Dane są po angielsku, prosto z TibiaWiki (nazwy, loot, miejsca), bo tak
nazywa je gra. Polskie są tylko nagłówki.
"""

import threading
from html import escape
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..core.models import Monster
from ..core.monsters import download_missing, sprite_path
from ..core.spawns import SOURCE_NOTE, Spawns
from .map_window import MapPanel
from .monster_widgets import AnimatedSprite, ElementBars

PAGE_SPRITE = 64
SPAWN_MAP_HEIGHT = 320
RARITY_NAMES = {
    "always": "zawsze",
    "common": "częsty",
    "uncommon": "nieczęsty",
    "semi-rare": "półrzadki",
    "rare": "rzadki",
    "very rare": "bardzo rzadki",
}


def _thousands(value: int) -> str:
    return f"{value:,}".replace(",", " ")


class MonsterListPage(QWidget):
    monster_selected = Signal(object)
    back_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._monsters: list[Monster] = []
        self._search = QLineEdit(placeholderText="Szukaj potwora…", clearButtonEnabled=True)
        self._list = QListWidget()
        self._empty = QLabel(alignment=Qt.AlignmentFlag.AlignCenter, wordWrap=True)

        back = QPushButton("← Menu")
        back.clicked.connect(self.back_requested)
        top = QHBoxLayout()
        top.addWidget(back)
        top.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(top)
        layout.addWidget(self._search)
        layout.addWidget(self._list, 1)
        layout.addWidget(self._empty, 1)

        self._search.textChanged.connect(self._refresh)
        self._list.itemClicked.connect(
            lambda item: self.monster_selected.emit(item.data(Qt.ItemDataRole.UserRole))
        )

    def set_monsters(self, monsters: dict[str, Monster]) -> None:
        self._monsters = sorted(monsters.values(), key=lambda m: m.name.lower())
        self._refresh()

    def _refresh(self) -> None:
        text = self._search.text().strip().lower()
        shown = [m for m in self._monsters if text in m.name.lower()]
        # Przy ~2800 potworach przebudowa listy przy każdej literze jest szybsza bez odświeżania ekranu.
        self._list.setUpdatesEnabled(False)
        self._list.clear()
        for monster in shown:
            boss = " · boss" if monster.boss else ""
            item = QListWidgetItem(f"{monster.name}  (HP {_thousands(monster.hp)}, exp {_thousands(monster.exp)}{boss})")
            item.setData(Qt.ItemDataRole.UserRole, monster)
            self._list.addItem(item)
        self._list.setUpdatesEnabled(True)
        self._empty.setText("Brak potworów w danych." if not self._monsters else "Nic nie pasuje do wyszukiwania.")
        self._list.setVisible(bool(shown))
        self._empty.setVisible(not shown)


class _SpriteLoader(QObject):
    loaded = Signal(str)  # id potwora


class MonsterPage(QWidget):
    """Szczegóły jednego potwora. Przycisk wstecz wraca tam, skąd przyszliśmy (lista albo quest)."""

    back_requested = Signal()

    def __init__(self, sprites_dir: Path, maps_dir: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._sprites_dir = sprites_dir
        self._spawns = Spawns()
        self._monster: Monster | None = None
        self._loader = _SpriteLoader(self)
        self._loader.loaded.connect(self._on_sprite_loaded)

        self._back = QPushButton("← Wstecz")
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
        self._elements_title = QLabel("CZYM BIĆ (OBRAŻENIA OD ŻYWIOŁÓW)")
        self._elements_title.setObjectName("sectionTitle")
        self._elements: QWidget | None = None
        self._top = _html_label()
        self._map_title = QLabel("MAPA WYSTĘPOWANIA")
        self._map_title.setObjectName("sectionTitle")
        self._map = MapPanel(maps_dir)
        self._map.setFixedHeight(SPAWN_MAP_HEIGHT)
        self._bottom = _html_label()

        content = QWidget()
        column = QVBoxLayout(content)
        column.setContentsMargins(0, 0, 4, 0)
        column.addLayout(header)
        column.addWidget(self._elements_title)
        self._elements_at = column.count()  # tu wstawiamy paski żywiołów konkretnego potwora
        column.addWidget(self._top)
        column.addWidget(self._map_title)
        column.addWidget(self._map)
        column.addWidget(self._bottom)
        column.addStretch(1)

        scroll = QScrollArea(widgetResizable=True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        self._scroll = scroll
        self._column = column

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(top)
        layout.addWidget(scroll, 1)

    def set_spawns(self, spawns: Spawns) -> None:
        self._spawns = spawns

    def set_back_text(self, text: str) -> None:
        self._back.setText(text)

    def show_monster(self, monster: Monster) -> None:
        self._monster = monster
        if self._elements is not None:
            self._elements.deleteLater()
        self._elements = ElementBars(monster)
        self._column.insertWidget(self._elements_at, self._elements)
        self._render()
        self._scroll.verticalScrollBar().setValue(0)
        points = self._spawns.of(monster.id)
        self._map_title.setVisible(bool(points))
        self._map.setVisible(bool(points))
        if points:
            self._map.show_spawns(monster.name, points, SOURCE_NOTE)
        if monster.image_url and sprite_path(self._sprites_dir, monster.id) is None:

            def run() -> None:
                if download_missing(self._sprites_dir, [monster]):
                    self._loader.loaded.emit(monster.id)

            threading.Thread(target=run, daemon=True, name="sprite").start()

    def _on_sprite_loaded(self, monster_id: str) -> None:
        if self._monster is not None and self._monster.id == monster_id:
            self._render()

    def _render(self) -> None:
        if self._monster is not None:
            self._sprite.set_path(sprite_path(self._sprites_dir, self._monster.id))
            self._header.setText(header_html(self._monster))
            self._top.setText(monster_html(self._monster))
            self._bottom.setText(loot_html(self._monster))


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
        tags.append("boss")
    if monster.bestiary_class:
        tags.append(escape(monster.bestiary_class))
    if monster.bestiary_level:
        tags.append(f"bestiariusz: {escape(monster.bestiary_level)}")
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
        parts.append(_section("UMIEJĘTNOŚCI"))
        parts.append("<br>".join(f"• {escape(a)}" for a in monster.abilities))
    if monster.location:
        parts.append(_section("GDZIE WYSTĘPUJE"))
        parts.append(escape(monster.location))
    return "<br>".join(parts)


def loot_html(monster: Monster) -> str:
    """Dolna część strony (pod mapą): loot i źródło."""
    parts = []
    if monster.loot:
        parts.append(_section("LOOT"))
        lines = []
        for item in monster.loot:
            amount = f"{escape(item.amount)}× " if item.amount else ""
            rarity = f' <span style="color: #9aa0a6;">({RARITY_NAMES[item.rarity]})</span>' if item.rarity else ""
            lines.append(f"• {amount}{escape(item.name)}{rarity}")
        parts.append("<br>".join(lines))

    parts.append(
        f'<br><span style="color: #9aa0a6;">Źródło: <a href="{escape(monster.source_url, quote=True)}">'
        "TibiaWiki</a> (CC BY-SA 4.0) · obrazek © CipSoft</span>"
    )
    return "<br>".join(parts)


def _section(title: str) -> str:
    return f'<br><span style="color: #9aa0a6; font-size: 11px; font-weight: 600;">{title}</span>'
