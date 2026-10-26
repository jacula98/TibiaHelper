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
from ..core.models import Monster, Quest
from ..core.paths import items_dir, maps_dir, sprites_dir
from ..core.spawns import Spawns
from ..core.repository import QuestFileError, load_quest_file
from ..core.progress import ProgressStore
from ..core.settings import load_settings, save_settings
from .home_page import HomePage
from .monster_pages import MonsterListPage, MonsterPage
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
        self._quest_view = QuestView(progress, maps_dir(), sprites_dir(), editable=author_file is not None)
        self._stack = QStackedWidget()
        self._stack.addWidget(self._home)
        self._stack.addWidget(self._list_page)
        self._stack.addWidget(self._quest_view)
        self._monster_list = MonsterListPage(sprites_dir())
        self._monster_page = MonsterPage(sprites_dir(), maps_dir(), items_dir())
        self._stack.addWidget(self._monster_list)
        self._stack.addWidget(self._monster_page)
        # Strona, do której wraca „← Wstecz” na stronie potwora (lista potworów albo quest).
        self._monster_return: QWidget = self._monster_list

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
        self._monster_list.monster_selected.connect(lambda m: self._open_monster(m, self._monster_list))
        self._quest_view.monster_requested.connect(lambda m: self._open_monster(m, self._quest_view))
        self._monster_page.back_requested.connect(lambda: self._stack.setCurrentWidget(self._monster_return))
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
        item_images: dict[str, str] | None = None,
    ) -> None:
        self._data_version = data_version
        self._monster_page.set_item_images(item_images or {})
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
        self.set_quests(result.quests, result.data_version, result.monsters, result.item_images)
        quest = next((q for q in result.quests if q.id == quest_id), None)
        if quest is not None:
            self._open_quest(quest)

    def _open_quest(self, quest: Quest) -> None:
        self._quest_view.show_quest(quest)
        self._stack.setCurrentWidget(self._quest_view)

    def _open_monster(self, monster: Monster, came_from: QWidget) -> None:
        self._monster_return = came_from
        self._monster_page.set_back_text("← Quest" if came_from is self._quest_view else "← Lista")
        self._monster_page.show_monster(monster)
        self._stack.setCurrentWidget(self._monster_page)

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
