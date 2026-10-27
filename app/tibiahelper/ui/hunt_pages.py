"""Zakładka „Hunt/Bestiary zones”: lista miejsc huntów z filtrami i strona jednego miejsca.

Dane są z TibiaWiki (po angielsku, jak w grze): poziom, gwiazdki exp/loot, potwory, wejście.
Autor dopisuje trasę na mapie i uwagi. Przy potworach jest Bestiary: ile killi i charm pointów.
"""

import threading
from html import escape
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QIntValidator
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..core import author
from ..core.hunts import ALL_CITIES, ANY_VOCATION, SORTS, VOCATIONS, bestiary, filter_hunts, hunt_level, sort_hunts, stars
from ..core.i18n import tr
from ..core.issues import hunt_issue_url
from ..core.models import Hunt, Item, Monster, Waypoint
from ..core.monsters import download_missing, sprite_path
from ..core.reports import hunt_report_url, hunt_subject
from . import theme
from .map_window import MapPanel
from .report_list import ReportFeed, ReportList
from .route_widgets import ROUTE_LINK_PREFIX, RouteEditor, numbered, route_html
from .sprites import display_sprite
from .theme import report_button

MAX_LEVEL = 5000
MONSTER_LINK_PREFIX = "monster:"
ITEM_LINK_PREFIX = "item:"
MAP_HEIGHT = 320
ICON = 32


class HuntListPage(QWidget):
    hunt_selected = Signal(object)
    back_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._hunts: list[Hunt] = []
        self._monster_names: dict[str, str] = {}
        self._search = QLineEdit(placeholderText=tr("Szukaj miejsca, miasta albo potwora…"), clearButtonEnabled=True)
        # Pole tekstowe jak w questach: puste = bez filtra poziomu.
        self._level = QLineEdit(placeholderText=tr("mój lvl"), clearButtonEnabled=True)
        self._level.setValidator(QIntValidator(0, MAX_LEVEL, self._level))
        self._level.setFixedWidth(90)
        self._level.setToolTip(tr("Twój level: pokażę miejsca, na które już możesz iść"))
        self._vocation = QComboBox()
        self._vocation.addItem(tr(ANY_VOCATION), None)
        for key, name in VOCATIONS.items():
            self._vocation.addItem(name, key)
        self._city = QComboBox()
        self._sort = QComboBox()
        for name in SORTS:
            self._sort.addItem(tr(name), name)
        self._sort.setToolTip(tr("Sortowanie"))
        self._list = QListWidget()
        self._list.setWordWrap(True)
        self._empty = QLabel(alignment=Qt.AlignmentFlag.AlignCenter, wordWrap=True)

        back = QPushButton(tr("← Menu"))
        back.clicked.connect(self.back_requested)
        top = QHBoxLayout()
        top.addWidget(back)
        top.addStretch(1)
        row1 = QHBoxLayout()
        row1.addWidget(self._search, 1)
        row1.addWidget(self._level)
        row2 = QHBoxLayout()
        row2.addWidget(self._vocation)
        row2.addWidget(self._city)
        row2.addWidget(self._sort)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(top)
        layout.addLayout(row1)
        layout.addLayout(row2)
        layout.addWidget(self._list, 1)
        layout.addWidget(self._empty, 1)

        self._search.textChanged.connect(self._refresh)
        self._level.textChanged.connect(self._refresh)
        for combo in (self._vocation, self._city, self._sort):
            combo.currentIndexChanged.connect(self._refresh)
        self._list.itemClicked.connect(lambda item: self.hunt_selected.emit(item.data(Qt.ItemDataRole.UserRole)))

    def set_hunts(self, hunts: list[Hunt], monsters: dict[str, Monster]) -> None:
        self._hunts = hunts
        self._monster_names = {m.id: m.name for m in monsters.values()}
        current = self._city.currentData()
        # blockSignals: przebudowa listy miast nie ma odświeżać listy przy każdym dodanym mieście.
        self._city.blockSignals(True)
        self._city.clear()
        self._city.addItem(tr(ALL_CITIES), None)
        for city in sorted({h.city for h in hunts if h.city}):
            self._city.addItem(city, city)
        self._city.setCurrentIndex(max(0, self._city.findData(current)))
        self._city.blockSignals(False)
        self._refresh()

    def _refresh(self) -> None:
        level = int(self._level.text()) if self._level.text().isdigit() else None
        vocation = self._vocation.currentData()
        found = filter_hunts(
            self._hunts, self._search.text(), level, vocation, self._city.currentData(), self._monster_names
        )
        shown = sort_hunts(found, self._sort.currentData(), vocation)
        self._list.clear()
        for hunt in shown:
            item = QListWidgetItem(_item_text(hunt, vocation))
            item.setData(Qt.ItemDataRole.UserRole, hunt)
            self._list.addItem(item)
        self._empty.setText(
            tr("Brak miejsc huntów w danych.") if not self._hunts else tr("Nic nie pasuje do wyszukiwania i filtrów.")
        )
        self._list.setVisible(bool(shown))
        self._empty.setVisible(not shown)


def _item_text(hunt: Hunt, vocation: str | None) -> str:
    level = hunt_level(hunt, vocation)
    details = [f"lvl {level}+" if level is not None else "lvl ?", f"exp {stars(hunt.exp_stars)}", f"loot {stars(hunt.loot_stars)}"]
    title = f"{hunt.name} · {hunt.city}" if hunt.city else hunt.name
    return f"{title}\n{'   '.join(details)}"


class _Loaded(QObject):
    loaded = Signal(str)  # id miejsca


class HuntPage(QWidget):
    back_requested = Signal()
    monster_requested = Signal(object)
    item_requested = Signal(object)
    edit_requested = Signal(object)  # tryb autora: Hunt

    def __init__(self, sprites_dir: Path, maps_dir: Path, author_mode: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._sprites_dir = sprites_dir
        self._monsters: dict[str, Monster] = {}
        self._items: dict[str, Item] = {}
        self._data_version = 0
        self.hunt: Hunt | None = None
        self._route: list[Waypoint] = []
        self._loader = _Loaded(self)
        self._loader.loaded.connect(self._on_sprites_loaded)

        self._back = QPushButton(tr("← Lista"))
        self._back.clicked.connect(self.back_requested)
        top = QHBoxLayout()
        top.addWidget(self._back)
        top.addStretch(1)
        if author_mode:
            edit = QPushButton("✏ Edytuj")
            edit.clicked.connect(lambda: self.hunt and self.edit_requested.emit(self.hunt))
            top.addWidget(edit)

        self._top = _html_label()
        self._route_list = _html_label()
        self._map = MapPanel(maps_dir)
        self._map.setFixedHeight(MAP_HEIGHT)
        self._bottom = _html_label()
        for label in (self._top, self._route_list, self._bottom):
            # Linki do potworów, przedmiotów i punktów trasy obsługujemy sami.
            label.setOpenExternalLinks(False)
            label.linkActivated.connect(self._on_link)

        content = QWidget()
        column = QVBoxLayout(content)
        column.setContentsMargins(0, 0, 4, 0)
        column.addWidget(self._top)
        column.addWidget(self._route_list)
        column.addWidget(self._map)
        column.addWidget(self._bottom)
        self._reports = ReportList()
        column.addWidget(self._reports)
        column.addStretch(1)
        self._scroll = QScrollArea(widgetResizable=True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setWidget(content)

        report = report_button()
        report.clicked.connect(self._report_issue)
        # Raport z gry (loot, Hunt Analyzer) idzie przez formularz Google, nie przez GitHub:
        # gracz nie potrzebuje konta, a autor dostaje odpowiedzi w arkuszu.
        send = QPushButton(tr("📨 Wyślij Hunt Analyzer"))
        send.setToolTip(tr("Otwiera formularz w przeglądarce (bez konta). Wklej tam swój raport."))
        send.setCursor(Qt.CursorShape.PointingHandCursor)
        send.clicked.connect(self._send_report)
        bottom = QHBoxLayout()
        bottom.addWidget(send)
        bottom.addStretch(1)
        bottom.addWidget(report)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(top)
        layout.addWidget(self._scroll, 1)
        layout.addLayout(bottom)

    def set_data(self, monsters: dict[str, Monster], items: dict[str, Item], data_version: int) -> None:
        self._monsters, self._items, self._data_version = monsters, items, data_version

    def set_back_text(self, text: str) -> None:
        self._back.setText(text)

    def set_report_feed(self, feed: ReportFeed) -> None:
        self._reports.set_feed(feed)

    def show_hunt(self, hunt: Hunt) -> None:
        self.hunt = hunt
        self._reports.set_subject(hunt_subject(hunt))
        self._route = numbered(hunt.route)
        self._render()
        self._scroll.verticalScrollBar().setValue(0)
        labeled = [p for p in self._route if p.label]
        if self._route:
            self._map.show_route(tr("Trasa"), self._route, labeled[0] if labeled else self._route[0])
        elif hunt.entrance is not None:
            entrance = hunt.entrance.model_copy(update={"label": tr("Wejście")})
            self._map.show_points([entrance], entrance)
        self._map.setVisible(bool(self._route) or hunt.entrance is not None)
        if self._map.isVisibleTo(self):
            # Po pokazaniu strony mapa ma już swój rozmiar, więc dopiero wtedy da się ją wyśrodkować.
            QTimer.singleShot(0, self._map.recenter)
        missing = [
            self._monsters[m] for m in hunt.monster_ids()
            if m in self._monsters and self._monsters[m].image_url and sprite_path(self._sprites_dir, m) is None
        ]
        if missing:

            def run() -> None:
                if download_missing(self._sprites_dir, missing):
                    self._loader.loaded.emit(hunt.id)

            threading.Thread(target=run, daemon=True, name="sprite").start()

    def _on_sprites_loaded(self, hunt_id: str) -> None:
        if self.hunt is not None and self.hunt.id == hunt_id:
            self._render()

    def _render(self) -> None:
        if self.hunt is None:
            return
        self._top.setText(hunt_header_html(self.hunt))
        self._route_list.setText(route_html(self.hunt.route))
        self._route_list.setVisible(any(p.label for p in self.hunt.route))
        self._bottom.setText(
            hunt_monsters_html(self.hunt, self._monsters, lambda m: display_sprite(self._sprites_dir, m))
            + hunt_footer_html(self.hunt, self._items)
        )

    def _on_link(self, link: str) -> None:
        if link.startswith(ROUTE_LINK_PREFIX):
            index = link.removeprefix(ROUTE_LINK_PREFIX)
            if index.isdigit() and int(index) < len(self._route) and self._route[int(index)].label:
                self._map.show_route(tr("Trasa"), self._route, self._route[int(index)])
        elif link.startswith(MONSTER_LINK_PREFIX):
            monster = self._monsters.get(link.removeprefix(MONSTER_LINK_PREFIX))
            if monster is not None:
                self.monster_requested.emit(monster)
        elif link.startswith(ITEM_LINK_PREFIX):
            item = self._items.get(link.removeprefix(ITEM_LINK_PREFIX).lower())
            if item is not None:
                self.item_requested.emit(item)
        else:
            QDesktopServices.openUrl(QUrl(link))

    def _report_issue(self) -> None:
        if self.hunt is not None:
            QDesktopServices.openUrl(QUrl(hunt_issue_url(self.hunt, self._data_version)))

    def _send_report(self) -> None:
        if self.hunt is not None:
            QDesktopServices.openUrl(QUrl(hunt_report_url(self.hunt)))


def hunt_header_html(hunt: Hunt) -> str:
    """Nazwa, miasto, poziom dla profesji, gwiazdki, opis i uwagi autora. Teksty z danych przez escape."""
    parts = [f'<span style="font-size: 18px; font-weight: 600;">{escape(hunt.name)}</span>']
    if hunt.city:
        parts.append(f'<span style="color: {theme.MUTED};">{escape(hunt.city)}</span>')
    levels = " · ".join(f"{escape(VOCATIONS[voc])} <b>{lvl}+</b>" for voc, lvl in hunt.levels.items())
    if levels:
        parts.append(levels)
    parts.append(f"exp <b>{stars(hunt.exp_stars)}</b> · loot <b>{stars(hunt.loot_stars)}</b>")
    if hunt.location:
        parts.append(_section(tr("GDZIE")))
        parts.append(escape(hunt.location))
    if hunt.notes:
        parts.append(_section(tr("UWAGI")))
        parts.append(escape(hunt.notes).replace("\n", "<br>"))
    if hunt.route:
        parts.append(_section(tr("TRASA")))
    return "<br>".join(parts)


def hunt_monsters_html(hunt: Hunt, monsters: dict[str, Monster], sprite=lambda monster_id: None) -> str:
    """Każdy potwór raz: obrazek, nazwa (link), HP/exp i Bestiary; pod spodem w której części miejsca jest."""
    rows = []
    for monster_id in hunt.monster_ids():
        monster = monsters.get(monster_id)
        if monster is None:
            continue
        path = sprite(monster_id)
        image = f'<img src="{path.as_uri()}" width="{ICON}" height="{ICON}">' if path else ""
        info = f"HP {monster.hp:,} · exp {monster.exp:,}".replace(",", " ")
        entry = bestiary(monster)
        if entry is not None:
            (first, second, full), charms = entry
            info += " · " + tr("Bestiary: {kills} killi, {charms} charm", kills=f"{first}/{second}/{full}", charms=charms)
        rows.append(
            f'<tr><td width="{ICON + 6}" style="vertical-align: middle">{image}</td>'
            f'<td style="vertical-align: middle"><a href="{MONSTER_LINK_PREFIX}{escape(monster.id, quote=True)}" '
            f'style="color: {theme.TEXT};">{escape(monster.name)}</a><br>'
            f'<span style="color: {theme.MUTED};">{escape(info)}</span></td></tr>'
        )
    if not rows:
        return ""
    parts = [_section(tr("POTWORY I BESTIARY")), f'<table cellspacing="0" cellpadding="1">{"".join(rows)}</table>']
    # Części miejsca (np. piętra) krótko, bez powtarzania całych wierszy potworów.
    named = [area for area in hunt.areas if area.name]
    if named:
        parts.append(_section(tr("GDZIE W MIEJSCU")))
        for area in named:
            names = ", ".join(escape(monsters[m].name) for m in area.monsters if m in monsters)
            parts.append(f"<b>{escape(area.name)}:</b> {names}")
    return "<br>".join(parts)


def hunt_footer_html(hunt: Hunt, items: dict[str, Item]) -> str:
    parts = []
    if hunt.best_loot:
        parts.append(_section(tr("NAJLEPSZY LOOT")))
        names = []
        for name in hunt.best_loot:
            if name.lower() in items:
                names.append(f'<a href="{ITEM_LINK_PREFIX}{escape(name, quote=True)}" style="color: {theme.TEXT};">{escape(name)}</a>')
            else:
                names.append(escape(name))
        parts.append(", ".join(names))
    parts.append(
        f'<br><span style="color: {theme.MUTED};">{escape(tr("Źródło:"))} '
        f'<a href="{escape(hunt.source_url, quote=True)}">TibiaWiki</a> (CC BY-SA 4.0) · '
        f'{escape(tr("obrazki © CipSoft"))}</span>'
    )
    return "<br>".join(parts)


def _section(title: str) -> str:
    return f'<br><span style="color: {theme.MUTED}; font-size: 11px; font-weight: 600;">{escape(title)}</span>'


def _html_label() -> QLabel:
    label = QLabel(wordWrap=True, textFormat=Qt.TextFormat.RichText)
    label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
    return label


class HuntEditor(QDialog):
    """Tryb autora: trasa i uwagi do miejsca huntu. Dane z wiki zostają bez zmian."""

    saved = Signal(str)  # id miejsca

    def __init__(self, hunt: Hunt, data_file: Path, maps_dir: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Hunt: {hunt.name}")
        self.resize(440, 520)
        self._hunt_id = hunt.id
        self._data_file = data_file
        self._notes = QPlainTextEdit(hunt.notes or "")
        self._notes.setPlaceholderText("Np. gdzie najlepiej expić, na co uważać, jaki set.")
        self._notes.setMaximumHeight(120)
        self._route = RouteEditor(
            [p.model_dump(mode="json", exclude_defaults=True) for p in hunt.route], maps_dir, "wejście, schody, respawn"
        )
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        for title, widget in (("UWAGI", self._notes), ("TRASA (do miejsca albo po miejscu)", self._route)):
            label = QLabel(title)
            label.setObjectName("sectionTitle")
            layout.addWidget(label)
            layout.addWidget(widget)
        layout.addWidget(buttons)

    def _save(self) -> None:
        if self._route.is_busy():
            # Zapis teraz dałby na tych odcinkach prostą linię zamiast drogi po mapie.
            QMessageBox.information(self, "Edytor", "Droga po mapie jeszcze się liczy. Spróbuj za chwilę.")
            return
        try:
            data = author.load_data(self._data_file)
            hunt = next((h for h in data.get("hunts", []) if h.get("id") == self._hunt_id), None)
            if hunt is None:
                raise author.AuthorError(f"Nie ma miejsca {self._hunt_id!r} w pliku.")
            # Puste pola usuwamy z pliku, żeby nie trzymać pustych list i tekstów.
            for key, value in (("notes", self._notes.toPlainText().strip()), ("route", self._route.route())):
                if value:
                    hunt[key] = value
                else:
                    hunt.pop(key, None)
            author.save_data(data, self._data_file)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Edytor", str(exc))
            return
        self.saved.emit(self._hunt_id)
        self.accept()
