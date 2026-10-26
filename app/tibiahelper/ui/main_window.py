"""Główne okno: nagłówek z trybikiem, pasek aktualizacji i strony (lista / quest)."""

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..core import author
from ..core.items import build_drops
from ..core.models import Item, Monster, Npc, Quest
from ..core.paths import bundled_qol_dir, items_dir, maps_dir, npcs_dir, sprites_dir
from ..core.spawns import Spawns
from ..core.repository import QuestFileError, load_quest_file
from ..core.progress import ProgressStore
from ..core.settings import load_settings, save_settings
from .home_page import HomePage
from .item_pages import ItemListPage, ItemPage
from .monster_pages import MonsterListPage, MonsterPage
from .qol_pages import LootSettingsPage, MinimapPage, QolPage, UiHotkeysPage
from .quest_editor import QuestEditor
from .quest_list import QuestListPage
from .quest_view import QuestView
from .settings_dialog import SettingsDialog


class MainWindow(QMainWindow):
    def __init__(
        self,
        progress: ProgressStore,
        settings_path: Path,
        author_file: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("TibiaHelper")
        # Okno zawsze nad grą.
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.resize(380, 560)
        self._data_version = 0

        # Kilka "stron" w jednym oknie zamiast wielu okien: mniej miejsca obok gry.
        self._home = HomePage()
        self._list_page = QuestListPage(progress)
        # author_file: plik quests.json edytowany w trybie autora (None = zwykły tryb).
        self._author_file = author_file
        self._editor: QuestEditor | None = None
        self._quest_view = QuestView(progress, maps_dir(), sprites_dir(), npcs_dir(), editable=author_file is not None)
        self._stack = QStackedWidget()
        self._stack.addWidget(self._home)
        self._stack.addWidget(self._list_page)
        self._stack.addWidget(self._quest_view)
        self._monster_list = MonsterListPage(sprites_dir())
        self._monster_page = MonsterPage(sprites_dir(), maps_dir(), items_dir())
        self._item_list = ItemListPage(items_dir())
        self._item_page = ItemPage(items_dir(), npcs_dir(), sprites_dir(), maps_dir())
        self._qol = QolPage()
        self._loot_settings = LootSettingsPage(bundled_qol_dir())
        self._minimap = MinimapPage()
        self._ui_hotkeys = UiHotkeysPage(bundled_qol_dir() / "clientoptions.json")
        pages = (
            self._monster_list,
            self._monster_page,
            self._item_list,
            self._item_page,
            self._qol,
            self._loot_settings,
            self._minimap,
            self._ui_hotkeys,
        )
        for page in pages:
            self._stack.addWidget(page)
        # Historia stron szczegółów (potwór, przedmiot), żeby „← Wstecz” wracał krok po kroku,
        # np. quest -> potwór -> przedmiot -> (wstecz) potwór -> (wstecz) quest.
        self._history: list[tuple[str, object]] = []

        self._banner = UpdateBanner()
        self._banner.hide()

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(12, 8, 12, 12)
        layout.addLayout(self._build_header())
        layout.addWidget(self._banner)
        layout.addWidget(self._stack, 1)
        self.setCentralWidget(central)

        self._home.quests_requested.connect(self._show_list)
        self._list_page.back_requested.connect(lambda: self._stack.setCurrentWidget(self._home))
        self._home.monsters_requested.connect(lambda: self._stack.setCurrentWidget(self._monster_list))
        self._monster_list.back_requested.connect(lambda: self._stack.setCurrentWidget(self._home))
        self._home.items_requested.connect(lambda: self._stack.setCurrentWidget(self._item_list))
        self._item_list.back_requested.connect(lambda: self._stack.setCurrentWidget(self._home))
        self._home.qol_requested.connect(lambda: self._stack.setCurrentWidget(self._qol))
        self._qol.back_requested.connect(lambda: self._stack.setCurrentWidget(self._home))
        self._qol.loot_requested.connect(lambda: self._stack.setCurrentWidget(self._loot_settings))
        self._loot_settings.back_requested.connect(lambda: self._stack.setCurrentWidget(self._qol))
        self._qol.maps_requested.connect(lambda: self._stack.setCurrentWidget(self._minimap))
        self._minimap.back_requested.connect(lambda: self._stack.setCurrentWidget(self._qol))
        self._qol.ui_requested.connect(lambda: self._stack.setCurrentWidget(self._ui_hotkeys))
        self._ui_hotkeys.back_requested.connect(lambda: self._stack.setCurrentWidget(self._qol))
        self._monster_list.monster_selected.connect(lambda m: self._open_detail("monster", m))
        self._quest_view.monster_requested.connect(lambda m: self._open_detail("monster", m))
        self._item_list.item_selected.connect(lambda i: self._open_detail("item", i))
        self._monster_page.item_requested.connect(lambda i: self._open_detail("item", i))
        self._item_page.monster_requested.connect(lambda m: self._open_detail("monster", m))
        self._monster_page.back_requested.connect(self._back)
        self._item_page.back_requested.connect(self._back)
        self._list_page.quest_selected.connect(self._open_quest)
        self._quest_view.edit_requested.connect(self._edit_quest)
        if author_file is not None:
            self.setWindowTitle("TibiaHelper – tryb autora")
        self._quest_view.back_requested.connect(self._show_list)
        self._quest_view.progress_changed.connect(self._list_page.refresh_progress)

        self._settings_path = settings_path
        self._settings = load_settings(settings_path)
        self.setWindowOpacity(self._settings.opacity)
        if self._settings.geometry:
            # Qt sam pilnuje, żeby okno nie wylądowało poza ekranem (np. po odłączeniu monitora).
            self.restoreGeometry(QByteArray.fromBase64(self._settings.geometry.encode("ascii")))

    def set_quests(
        self,
        quests: list[Quest],
        data_version: int,
        monsters: dict[str, Monster] | None = None,
        items: dict[str, Item] | None = None,
        npcs: dict[str, Npc] | None = None,
    ) -> None:
        monsters, items, npcs = monsters or {}, items or {}, npcs or {}
        self._data_version = data_version
        self._quest_view.set_npcs(npcs)
        self._monster_page.set_items(items)
        self._monster_page.set_data_version(data_version)
        self._item_list.set_items(items)
        self._item_page.set_data(npcs, monsters, build_drops(monsters), data_version)
        self._list_page.set_quests(quests)
        self._quest_view.set_data_version(data_version)
        self._quest_view.set_monsters(monsters or {})
        self._monster_list.set_monsters(monsters or {})

    def set_spawns(self, spawns: Spawns) -> None:
        self._monster_page.set_spawns(spawns)

    def offer_update(self, data_version: int, on_accept: Callable[[], None]) -> None:
        """Pokazuje pasek „są nowsze poradniki”. Dane zmieniają się dopiero po kliknięciu."""
        self._banner.show_offer(data_version, on_accept)

    def _build_header(self) -> QHBoxLayout:
        name = QLabel("TibiaHelper")
        name.setObjectName("appName")
        gear = QToolButton(text="⚙")
        gear.setObjectName("icon")
        gear.setToolTip("Ustawienia")
        gear.setCursor(Qt.CursorShape.PointingHandCursor)
        gear.clicked.connect(self._open_settings)

        header = QHBoxLayout()
        header.addWidget(name)
        header.addStretch(1)
        header.addWidget(gear)
        return header

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self._settings.opacity, self._data_version, self)
        dialog.opacity_changed.connect(self._set_opacity)
        dialog.exec()
        # Zapis po zamknięciu dialogu, a nie przy każdym ruchu suwaka.
        self._save_settings()

    def _set_opacity(self, opacity: float) -> None:
        self._settings.opacity = opacity
        self.setWindowOpacity(opacity)

    def _save_settings(self) -> None:
        self._settings.geometry = bytes(self.saveGeometry().toBase64()).decode("ascii")
        save_settings(self._settings_path, self._settings)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 (nazwa z Qt)
        self._save_settings()
        super().closeEvent(event)

    def _edit_quest(self, quest: Quest) -> None:
        if self._author_file is None:
            return
        try:
            raw = author.find_quest(author.load_data(self._author_file), quest.id)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Edytor", f"Nie można wczytać {self._author_file}:\n{exc}")
            return
        if raw is None:
            QMessageBox.warning(self, "Edytor", f"Nie ma questa {quest.id!r} w pliku.")
            return
        if self._editor is not None:
            self._editor.close()
        self._editor = QuestEditor(raw, self._author_file, maps_dir(), self)
        self._editor.saved.connect(self._reload_after_edit)
        self._editor.show()

    def _reload_after_edit(self, quest_id: str) -> None:
        """Po zapisie w edytorze wczytuje plik od nowa i pokazuje poprawiony quest."""
        try:
            result = load_quest_file(self._author_file)
        except QuestFileError as exc:
            QMessageBox.warning(self, "Edytor", str(exc))
            return
        # W trybie autora widać też szkice.
        self.set_quests(result.quests, result.data_version, result.monsters, result.items, result.npcs)
        quest = next((q for q in result.quests if q.id == quest_id), None)
        if quest is not None:
            self._open_quest(quest)

    def _open_quest(self, quest: Quest) -> None:
        self._quest_view.show_quest(quest)
        self._stack.setCurrentWidget(self._quest_view)

    def _open_detail(self, kind: str, target: object) -> None:
        """Otwiera stronę potwora albo przedmiotu i zapamiętuje, skąd przyszliśmy."""
        current = self._stack.currentWidget()
        if current is self._monster_page and self._monster_page.monster is not None:
            self._history.append(("monster", self._monster_page.monster))
        elif current is self._item_page and self._item_page.item is not None:
            self._history.append(("item", self._item_page.item))
        else:
            # Ze zwykłej strony (lista, quest) zaczynamy historię od nowa.
            self._history = [("page", current)]
        self._show_detail(kind, target)

    def _show_detail(self, kind: str, target: object) -> None:
        previous_kind, previous = self._history[-1]
        if previous_kind == "monster":
            back = "← Potwór"
        elif previous_kind == "item":
            back = "← Przedmiot"
        else:
            back = "← Quest" if previous is self._quest_view else "← Lista"
        page = self._monster_page if kind == "monster" else self._item_page
        page.set_back_text(back)
        if kind == "monster":
            self._monster_page.show_monster(target)
        else:
            self._item_page.show_item(target)
        self._stack.setCurrentWidget(page)

    def _back(self) -> None:
        if not self._history:
            self._stack.setCurrentWidget(self._home)
            return
        kind, target = self._history.pop()
        if kind == "page":
            self._stack.setCurrentWidget(target)
        else:
            self._show_detail(kind, target)

    def _show_list(self) -> None:
        self._stack.setCurrentWidget(self._list_page)


class UpdateBanner(QFrame):
    """Pasek nad listą: „Są nowsze poradniki” + Zaktualizuj / Później."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("banner")
        self._on_accept: Callable[[], None] | None = None

        self._text = QLabel(wordWrap=True)
        later = QPushButton("Później")
        later.clicked.connect(self.hide)
        accept = QPushButton("Zaktualizuj")
        accept.setObjectName("primary")
        accept.clicked.connect(self._accept)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(later)
        buttons.addWidget(accept)

        layout = QVBoxLayout(self)
        layout.addWidget(self._text)
        layout.addLayout(buttons)

    def show_offer(self, data_version: int, on_accept: Callable[[], None]) -> None:
        self._on_accept = on_accept
        self._text.setText(f"Są nowsze poradniki (wersja {data_version}). Zaktualizować?")
        self.show()

    def _accept(self) -> None:
        self.hide()
        if self._on_accept is not None:
            self._on_accept()
