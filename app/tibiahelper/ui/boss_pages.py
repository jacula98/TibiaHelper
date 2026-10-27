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

from PySide6.QtCore import QObject, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
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
from ..core.models import Boss, Monster, Quest
from ..core.monsters import download_missing, sprite_path
from . import theme
from .monster_grid import MonsterGrid
from .monster_pages import PAGE_SPRITE, header_html
from .monster_widgets import AnimatedSprite, ElementBars
from .theme import report_button

QUEST_LINK_PREFIX = "quest:"


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

    def __init__(self, sprites_dir: Path, author_mode: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._sprites_dir = sprites_dir
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
        self._body.setText(boss_html(self.entry, self._quests))
        self._source.setText(
            f'<span style="color: {theme.MUTED};">{escape(tr("Dane bossa:"))} '
            f'<a href="{escape(monster.source_url, quote=True)}">TibiaWiki</a> (CC BY-SA 4.0) · '
            f'{escape(tr("opis: autor TibiaHelper"))} · {escape(tr("obrazki © CipSoft"))}</span>'
        )

    def _on_sprite_loaded(self, monster_id: str) -> None:
        if self.entry is not None and self.entry.monster.id == monster_id:
            self._render()

    def _on_link(self, link: str) -> None:
        if link.startswith(QUEST_LINK_PREFIX):
            quest = self._quests.get(link.removeprefix(QUEST_LINK_PREFIX))
            if quest is not None:
                self.quest_requested.emit(quest)
        else:
            QDesktopServices.openUrl(QUrl(link))

    def _report_issue(self) -> None:
        if self.entry is not None:
            QDesktopServices.openUrl(QUrl(monster_issue_url(self.entry.monster, self._data_version)))


def boss_html(entry: BossEntry, quests: dict[str, Quest]) -> str:
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
            links = []
            for quest_id in boss.quests:
                quest = quests.get(quest_id)
                if quest is None:
                    continue
                links.append(f'📜 <a href="{QUEST_LINK_PREFIX}{escape(quest.id, quote=True)}" '
                             f'style="color: {theme.ACCENT};">{escape(quest.name)}</a>')
            if links:
                parts.append("<br>".join(links))
        if boss.access:
            parts.append(_section(tr("JAK DOJŚĆ")))
            parts.append(_text(boss.access))
        if boss.strategy:
            parts.append(_section(tr("JAK BIĆ")))
            parts.append(_text(boss.strategy))
    return "<br>".join(parts)


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

    def __init__(self, entry: BossEntry, data_file: Path, quests: dict[str, str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Boss: {entry.monster.name}")
        self.resize(460, 640)
        self._data_file = data_file
        self._monster_id = entry.monster.id
        # Kopia bossa jako słownik (jak w quests.json); nowy boss to pusty szkic.
        old = entry.boss.model_dump(mode="json", exclude_defaults=True) if entry.boss else {}
        self._old = copy.deepcopy(old)

        self._requirements = _edit(old.get("requirements"), "Np. zrobiony quest, poziom, dostęp premium…")
        self._access = _edit(old.get("access"), "Skąd wyruszyć i jak dojść do bossa.")
        self._strategy = _edit(old.get("strategy"), "Jak go bić: co robi, gdzie stać, czym bić.")
        self._quest_search = QLineEdit(placeholderText="Szukaj questa…", clearButtonEnabled=True)
        self._quest_list = QListWidget()
        self._quest_list.setMinimumHeight(200)
        chosen = set(old.get("quests", []))
        # Zaznaczone questy na górze, żeby od razu było widać wymagania.
        for quest_id, name in sorted(quests.items(), key=lambda q: (q[0] not in chosen, q[1].lower())):
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, quest_id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if quest_id in chosen else Qt.CheckState.Unchecked)
            self._quest_list.addItem(item)
        self._quest_search.textChanged.connect(self._filter_quests)
        self._ready = QCheckBox("Gotowy: pokaż graczom")
        self._ready.setChecked(old.get("status") == "reviewed")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(_title("WYMAGANIA"))
        layout.addWidget(self._requirements)
        layout.addWidget(_title("QUESTY Z WYMAGAŃ (klikalne u graczy)"))
        layout.addWidget(self._quest_search)
        layout.addWidget(self._quest_list)
        layout.addWidget(_title("JAK DOJŚĆ"))
        layout.addWidget(self._access)
        layout.addWidget(_title("JAK BIĆ"))
        layout.addWidget(self._strategy)
        layout.addWidget(self._ready)
        layout.addWidget(buttons)

    def _filter_quests(self, text: str) -> None:
        text = text.strip().lower()
        for row in range(self._quest_list.count()):
            item = self._quest_list.item(row)
            item.setHidden(text not in item.text().lower())

    def boss_dict(self, now: datetime | None = None) -> dict:
        """Boss z pól edytora, w formacie quests.json (puste pola pomijamy)."""
        boss: dict = {"monster": self._monster_id}
        for key, edit in (("requirements", self._requirements), ("access", self._access), ("strategy", self._strategy)):
            text = edit.toPlainText().strip()
            if text:
                boss[key] = text
        quests = [
            self._quest_list.item(row).data(Qt.ItemDataRole.UserRole)
            for row in range(self._quest_list.count())
            if self._quest_list.item(row).checkState() == Qt.CheckState.Checked
        ]
        if quests:
            boss["quests"] = quests
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
    return edit


def _title(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("sectionTitle")
    return label
