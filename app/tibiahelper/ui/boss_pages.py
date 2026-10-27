"""Zakładka „Bossy”: lista bossów, strona bossa i edytor autora.

Dane podstawowe (HP, exp, żywioły, loot, obrazek) są z bazy potworów (TibiaWiki).
Autor dopisuje po polsku: wymagania, jak dojść i jak bić. Gracz widzi tylko bossy,
które autor dodał i oznaczył jako przejrzane.
"""

import copy
import threading
from datetime import UTC, datetime
from html import escape
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..core import author
from ..core.bosses import (
    ALL_CLASSES,
    BOSSTIARY_KILLS,
    BOSSTIARY_POINTS,
    BOSSTIARY_STAGES,
    NO_CLASS,
    BossEntry,
    boss_entries,
    filter_entries,
    format_cooldown,
)
from ..core.i18n import tr
from ..core.issues import monster_issue_url
from ..core.models import Boss, Monster, Quest, Waypoint
from ..core.monsters import download_missing, sprite_path
from ..core.progress import ProgressStore
from . import theme
from .map_window import MapPanel
from .monster_grid import MonsterGrid
from .monster_pages import PAGE_SPRITE, header_html
from .monster_widgets import AnimatedSprite, ElementBars
from .quest_picker import QUEST_LINK_PREFIX, QuestPicker, requirements_html
from .route_widgets import ROUTE_LINK_PREFIX, RouteEditor, numbered, route_html
from .theme import report_button

ROUTE_MAP_HEIGHT = 320


class BossListPage(QWidget):
    boss_selected = Signal(object)  # BossEntry
    back_requested = Signal()

    def __init__(self, sprites_dir: Path, author_mode: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._author_mode = author_mode
        self._entries: list[BossEntry] = []
        self._search = QLineEdit(placeholderText=tr("Szukaj bossa…"), clearButtonEnabled=True)
        self._class = QComboBox()
        self._class.setToolTip(tr("Klasa w Bosstiary"))
        for name in (ALL_CLASSES, *BOSSTIARY_KILLS, NO_CLASS):
            self._class.addItem(tr(name), name)
        self._grid = MonsterGrid(sprites_dir)
        self._empty = QLabel(alignment=Qt.AlignmentFlag.AlignCenter, wordWrap=True)

        back = QPushButton(tr("← Menu"))
        back.clicked.connect(self.back_requested)
        top = QHBoxLayout()
        top.addWidget(back)
        top.addStretch(1)
        # Tryb autora: domyślnie wszystkie bossy z bazy, żeby dało się dodać każdego.
        self._only_added = QCheckBox("Tylko dodane")
        self._only_added.setVisible(author_mode)
        self._only_added.toggled.connect(self._refresh)
        top.addWidget(self._only_added)
        filters = QHBoxLayout()
        filters.addWidget(self._search, 1)
        filters.addWidget(self._class)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(top)
        layout.addLayout(filters)
        layout.addWidget(self._grid, 1)
        layout.addWidget(self._empty, 1)

        self._search.textChanged.connect(self._refresh)
        self._class.currentIndexChanged.connect(self._refresh)
        self._grid.monster_clicked.connect(self._on_clicked)

    def set_data(self, monsters: dict[str, Monster], bosses: list[Boss]) -> None:
        self._entries = boss_entries(monsters, bosses, self._author_mode)
        self._refresh()

    def _refresh(self) -> None:
        entries = filter_entries(self._entries, self._search.text(), self._class.currentData())
        if self._only_added.isChecked():
            entries = [e for e in entries if e.boss is not None]
        self._shown = {e.monster.id: e for e in entries}
        self._grid.set_monsters([e.monster for e in entries])
        self._empty.setText(
            tr("Autor nie dodał jeszcze żadnego bossa.") if not self._entries
            else tr("Nic nie pasuje do wyszukiwania i filtrów.")
        )
        self._grid.setVisible(bool(entries))
        self._empty.setVisible(not entries)

    def _on_clicked(self, monster: Monster) -> None:
        entry = self._shown.get(monster.id)
        if entry is not None:
            self.boss_selected.emit(entry)


class _Loaded(QObject):
    loaded = Signal(str)  # id potwora


class BossPage(QWidget):
    back_requested = Signal()
    monster_requested = Signal(object)  # „Karta potwora” (loot, mapa)
    quest_requested = Signal(object)  # klik w quest z wymagań
    edit_requested = Signal(object)  # tryb autora: BossEntry

    def __init__(
        self,
        sprites_dir: Path,
        maps_dir: Path,
        progress: ProgressStore,
        author_mode: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._sprites_dir = sprites_dir
        # Postęp questów: wymagane questy są zielone, gdy gracz je odhaczył.
        self._progress = progress
        self._quests: dict[str, Quest] = {}
        self._data_version = 0
        self.entry: BossEntry | None = None
        self._loader = _Loaded(self)
        self._loader.loaded.connect(self._on_sprite_loaded)

        back = QPushButton(tr("← Bossy"))
        back.clicked.connect(self.back_requested)
        top = QHBoxLayout()
        top.addWidget(back)
        top.addStretch(1)
        if author_mode:
            edit = QPushButton("✏ Edytuj")
            edit.clicked.connect(lambda: self.entry and self.edit_requested.emit(self.entry))
            top.addWidget(edit)

        self._sprite = AnimatedSprite(PAGE_SPRITE)
        self._header = _html_label()
        header = QHBoxLayout()
        header.addWidget(self._sprite)
        header.addWidget(self._header, 1)
        self._body = _html_label()
        # Linki „quest:id” obsługujemy sami, inne (TibiaWiki) otwiera przeglądarka.
        self._body.setOpenExternalLinks(False)
        self._body.linkActivated.connect(self._on_link)
        # Trasa: lista punktów (klik przenosi mapę) i mapa z linią między punktami.
        self._route_list = _html_label()
        self._route_list.setOpenExternalLinks(False)
        self._route_list.linkActivated.connect(self._on_link)
        self._route: list[Waypoint] = []
        self._map = MapPanel(maps_dir)
        self._map.setFixedHeight(ROUTE_MAP_HEIGHT)
        self._strategy = _html_label()
        self._elements_title = QLabel(tr("CZYM BIĆ (OBRAŻENIA OD ŻYWIOŁÓW)"))
        self._elements_title.setObjectName("sectionTitle")
        self._elements: QWidget | None = None
        monster_card = QPushButton(tr("Karta potwora: loot i mapa →"))
        monster_card.clicked.connect(lambda: self.entry and self.monster_requested.emit(self.entry.monster))
        self._source = _html_label()

        content = QWidget()
        column = QVBoxLayout(content)
        column.setContentsMargins(0, 0, 4, 0)
        column.addLayout(header)
        column.addWidget(self._body)
        column.addWidget(self._route_list)
        column.addWidget(self._map)
        column.addWidget(self._strategy)
        column.addWidget(self._elements_title)
        self._elements_at = column.count()
        column.addWidget(monster_card, 0, Qt.AlignmentFlag.AlignLeft)
        column.addWidget(self._source)
        column.addStretch(1)
        self._column = column
        scroll = QScrollArea(widgetResizable=True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        self._scroll = scroll

        report = report_button()
        report.clicked.connect(self._report_issue)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(top)
        layout.addWidget(scroll, 1)
        layout.addWidget(report, 0, Qt.AlignmentFlag.AlignRight)

    def set_quests(self, quests: list[Quest], data_version: int) -> None:
        # Tylko questy z listy (graczom: przejrzane), więc link nie prowadzi do ukrytego szkicu.
        self._quests = {quest.id: quest for quest in quests}
        self._data_version = data_version

    def show_boss(self, entry: BossEntry) -> None:
        self.entry = entry
        if self._elements is not None:
            self._elements.deleteLater()
        self._elements = ElementBars(entry.monster)
        self._column.insertWidget(self._elements_at, self._elements)
        self._render()
        self._scroll.verticalScrollBar().setValue(0)
        self._route = numbered(entry.boss.route if entry.boss else [])
        labeled = [point for point in self._route if point.label]
        self._route_list.setVisible(bool(labeled))
        self._map.setVisible(bool(self._route))
        if self._route:
            self._map.show_route(tr("Trasa do bossa"), self._route, labeled[0] if labeled else self._route[0])
            # Po pokazaniu strony mapa ma już swój rozmiar, więc dopiero wtedy da się ją wyśrodkować.
            QTimer.singleShot(0, self._map.recenter)
        monster = entry.monster
        if monster.image_url is not None and sprite_path(self._sprites_dir, monster.id) is None:

            def run() -> None:
                if download_missing(self._sprites_dir, [monster]):
                    self._loader.loaded.emit(monster.id)

            threading.Thread(target=run, daemon=True, name="sprite").start()

    def _render(self) -> None:
        if self.entry is None:
            return
        monster = self.entry.monster
        self._sprite.set_path(sprite_path(self._sprites_dir, monster.id))
        self._header.setText(header_html(monster))
        self._body.setText(boss_html(self.entry, self._quests, self._progress))
        self._route_list.setText(route_html(self.entry.boss.route if self.entry.boss else []))
        self._strategy.setText(strategy_html(self.entry.boss))
        self._source.setText(
            f'<span style="color: {theme.MUTED};">{escape(tr("Dane bossa:"))} '
            f'<a href="{escape(monster.source_url, quote=True)}">TibiaWiki</a> (CC BY-SA 4.0) · '
            f'{escape(tr("opis: autor TibiaHelper"))} · {escape(tr("obrazki © CipSoft"))}</span>'
        )

    def _on_sprite_loaded(self, monster_id: str) -> None:
        if self.entry is not None and self.entry.monster.id == monster_id:
            self._render()

    def _on_link(self, link: str) -> None:
        if link.startswith(ROUTE_LINK_PREFIX):
            index = link.removeprefix(ROUTE_LINK_PREFIX)
            if index.isdigit() and int(index) < len(self._route) and self._route[int(index)].label:
                self._map.show_route(tr("Trasa do bossa"), self._route, self._route[int(index)])
        elif link.startswith(QUEST_LINK_PREFIX):
            quest = self._quests.get(link.removeprefix(QUEST_LINK_PREFIX))
            if quest is not None:
                self.quest_requested.emit(quest)
        else:
            QDesktopServices.openUrl(QUrl(link))

    def _report_issue(self) -> None:
        if self.entry is not None:
            QDesktopServices.openUrl(QUrl(monster_issue_url(self.entry.monster, self._data_version)))


def boss_html(entry: BossEntry, quests: dict[str, Quest], progress: ProgressStore) -> str:
    """Bosstiary, cooldown i opis autora. Każdy tekst z danych przechodzi przez escape."""
    monster, boss = entry.monster, entry.boss
    parts = []
    if boss is None:
        parts.append(_note("Nie dodany: gracze go nie widzą. Kliknij „Edytuj”, żeby dodać."))
    elif not boss.is_visible:
        parts.append(_note("Szkic: gracze go nie widzą, dopóki nie oznaczysz go jako gotowego."))
    parts.append(_section("BOSSTIARY"))
    if monster.bosstiary_class in BOSSTIARY_KILLS:
        kills = BOSSTIARY_KILLS[monster.bosstiary_class]
        points = BOSSTIARY_POINTS[monster.bosstiary_class]
        cells = "".join(
            f'<td style="padding-right: 14px;"><b>{stage}</b><br>{tr("{n} killi", n=k)}<br>'
            f'<span style="color: {theme.MUTED};">+{p} pkt</span></td>'
            for stage, k, p in zip(BOSSTIARY_STAGES, kills, points)
        )
        parts.append(f"{escape(tr('Klasa:'))} <b>{escape(monster.bosstiary_class)}</b>")
        parts.append(f'<table cellspacing="0" cellpadding="2"><tr>{cells}</tr></table>')
        parts.append(
            f'<span style="color: {theme.MUTED};">'
            f'{escape(tr("Do pełnego Bosstiary (Mastery): {n} killi.", n=kills[-1]))}</span>'
        )
    else:
        parts.append(escape(tr("Ten boss nie jest w Bosstiary.")))
    if monster.cooldown_hours:
        parts.append(f"{escape(tr('Cooldown:'))} <b>{escape(format_cooldown(monster.cooldown_hours))}</b>")
    if boss is not None:
        if boss.requirements or boss.quests:
            parts.append(_section(tr("WYMAGANIA")))
            if boss.requirements:
                parts.append(_text(boss.requirements))
            if links := requirements_html(boss.quests, quests, progress):
                parts.append(links)
        if boss.access or boss.route:
            parts.append(_section(tr("JAK DOJŚĆ")))
        if boss.access:
            parts.append(_text(boss.access))
    return "<br>".join(parts)


def strategy_html(boss: Boss | None) -> str:
    if boss is None or not boss.strategy:
        return ""
    return _section(tr("JAK BIĆ")) + "<br>" + _text(boss.strategy)


def _text(value: str) -> str:
    # Autor pisze zwykły tekst; nowe linie zamieniamy na <br>, reszta przez escape.
    return escape(value).replace("\n", "<br>")


def _note(text: str) -> str:
    # Notki tylko w trybie autora, więc bez tłumaczenia (jak cały edytor).
    return f'<span style="color: {theme.ACCENT};">{escape(text)}</span>'


def _section(title: str) -> str:
    return f'<br><span style="color: {theme.MUTED}; font-size: 11px; font-weight: 600;">{escape(title)}</span>'


def _html_label() -> QLabel:
    label = QLabel(wordWrap=True, textFormat=Qt.TextFormat.RichText)
    label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
    label.setOpenExternalLinks(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
    return label


class BossEditor(QDialog):
    """Tryb autora: dodanie albo poprawka bossa. Zapis sprawdza całość (core/author.py)."""

    saved = Signal(str)  # id potwora

    def __init__(
        self,
        entry: BossEntry,
        data_file: Path,
        quests: dict[str, str],
        maps_dir: Path,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Boss: {entry.monster.name}")
        self.resize(460, 820)
        self._data_file = data_file
        self._monster_id = entry.monster.id
        # Kopia bossa jako słownik (jak w quests.json); nowy boss to pusty szkic.
        old = entry.boss.model_dump(mode="json", exclude_defaults=True) if entry.boss else {}
        self._old = copy.deepcopy(old)

        self._requirements = _edit(old.get("requirements"), "Np. zrobiony quest, poziom, dostęp premium…")
        self._access = _edit(old.get("access"), "Skąd wyruszyć i jak dojść do bossa.")
        self._strategy = _edit(old.get("strategy"), "Jak go bić: co robi, gdzie stać, czym bić.")
        self._quests = QuestPicker(quests, old.get("quests", []))
        # Trasa: punkty po kolei, wskazywane kliknięciem na mapie (jak pinezki w edytorze questa).
        self._route = RouteEditor(old.get("route", []), maps_dir, "start, schody, sala bossa")
        self._ready = QCheckBox("Gotowy: pokaż graczom")
        self._ready.setChecked(old.get("status") == "reviewed")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(_title("WYMAGANIA"))
        layout.addWidget(self._requirements)
        layout.addWidget(_title("QUESTY Z WYMAGAŃ (klikalne u graczy)"))
        layout.addWidget(self._quests)
        layout.addWidget(_title("JAK DOJŚĆ"))
        layout.addWidget(self._access)
        layout.addWidget(_title("TRASA (od startu do bossa)"))
        layout.addWidget(self._route)
        layout.addWidget(_title("JAK BIĆ"))
        layout.addWidget(self._strategy)
        layout.addWidget(self._ready)
        layout.addWidget(buttons)

    def boss_dict(self, now: datetime | None = None) -> dict:
        """Boss z pól edytora, w formacie quests.json (puste pola pomijamy)."""
        boss: dict = {"monster": self._monster_id}
        for key, edit in (("requirements", self._requirements), ("access", self._access), ("strategy", self._strategy)):
            text = edit.toPlainText().strip()
            if text:
                boss[key] = text
        if quests := self._quests.requirements():
            boss["quests"] = quests
        if route := self._route.route():
            boss["route"] = route
        if self._ready.isChecked():
            boss["status"] = "reviewed"
            # Data przeglądu zostaje stara, jeśli boss już był gotowy.
            boss["reviewed_at"] = self._old.get("reviewed_at") or (now or datetime.now(UTC)).isoformat(timespec="seconds")
        return boss

    def _save(self) -> None:
        try:
            data = author.load_data(self._data_file)
            author.upsert_boss(data, self.boss_dict())
            author.save_data(data, self._data_file)
        except (OSError, ValueError) as exc:
            # AuthorError to też ValueError: komunikat jest już czytelny dla autora.
            QMessageBox.warning(self, "Edytor", str(exc))
            return
        self.saved.emit(self._monster_id)
        self.accept()


def _edit(text: str | None, placeholder: str) -> QPlainTextEdit:
    edit = QPlainTextEdit(text or "")
    edit.setPlaceholderText(placeholder)
    edit.setMaximumHeight(90)  # zostaje miejsce na listę questów i trasy
    return edit


def _title(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("sectionTitle")
    return label
