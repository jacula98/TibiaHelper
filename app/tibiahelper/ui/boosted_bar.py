"""Pasek pod nagłówkiem: dzisiejszy boosted potwór i boosted boss (z TibiaWiki).

Kliknięcie otwiera kartę potwora albo bossa w programie. Dane i obrazki
pobieramy w wątku w tle, żeby okno nie zamarzało przy wolnym internecie.
"""

import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QObject, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QHBoxLayout, QLabel, QToolButton, QWidget

from ..core.boosted import Boosted, get_boosted, is_current
from ..core.i18n import tr
from ..core.models import Monster
from ..core.monsters import ensure_sprite, sprite_path
from .sprites import display_sprite

log = logging.getLogger(__name__)

# Co 15 minut sprawdzamy, czy nie zaczął się nowy dzień Tibii (program bywa otwarty cały dzień).
# Wiki pytamy tylko wtedy, gdy mamy dane z poprzedniego dnia, więc to kilka zapytań na dobę.
CHECK_EVERY_MS = 15 * 60 * 1000
ICON_SIZE = 22


class _Signals(QObject):
    # Okna Qt wolno zmieniać tylko z głównego wątku; sygnał z wątku w tle Qt dostarcza w głównym.
    boosted = Signal(object)
    sprite = Signal(str)


class BoostedBar(QWidget):
    monster_requested = Signal(object)  # Monster

    def __init__(self, sprites_dir: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._sprites_dir = sprites_dir
        self._cache: Path | None = None
        self._boosted: Boosted | None = None
        self._by_name: dict[str, Monster] = {}
        self._busy = False
        self._downloading: set[str] = set()  # id potworów, których obrazek właśnie się pobiera
        self._targets: dict[QToolButton, Monster | None] = {}  # przycisk -> karta do otwarcia
        self._signals = _Signals(self)
        self._signals.boosted.connect(self._on_boosted)
        self._signals.sprite.connect(self._on_sprite)

        title = QLabel(tr("Boosted dziś:"))
        title.setObjectName("muted")
        self._creature = self._button()
        self._boss = self._button()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(title)
        layout.addWidget(self._creature)
        layout.addWidget(self._boss)
        layout.addStretch(1)
        self._timer = QTimer(self, interval=CHECK_EVERY_MS)
        self._timer.timeout.connect(self._tick)
        self.hide()  # do pierwszego wyniku nie ma czego pokazać

    def _button(self) -> QToolButton:
        button = QToolButton()
        button.setObjectName("boosted")
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        button.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(lambda: self._open(button))
        button.hide()
        return button

    def start(self, cache: Path) -> None:
        """Pierwsze sprawdzenie od razu, potem co 15 minut (tylko gdy dane są z poprzedniego dnia)."""
        self._cache = cache
        self._check()
        self._timer.start()

    def _tick(self) -> None:
        self._render()  # o server save chowa wczorajsze nazwy, zanim przyjdą nowe
        self._check()

    def set_monsters(self, monsters: dict[str, Monster]) -> None:
        # Wiki podaje nazwę („Werelioness”), a program szuka potworów po id; łączymy po nazwie.
        self._by_name = {m.name.lower(): m for m in monsters.values()}
        self._render()

    def _check(self) -> None:
        if self._cache is None or self._busy or is_current(self._boosted, datetime.now(timezone.utc)):
            return
        self._busy = True
        cache = self._cache

        def work() -> None:
            self._signals.boosted.emit(get_boosted(cache, datetime.now(timezone.utc)))

        # daemon=True: zamknięcie programu nie czeka na pobieranie.
        threading.Thread(target=work, daemon=True, name="boosted").start()

    def _on_boosted(self, boosted: Boosted | None) -> None:
        self._busy = False
        if boosted is not None:
            self._boosted = boosted
        self._render()

    def _render(self) -> None:
        boosted = self._boosted
        # Wczorajszych nazw nie pokazujemy jako dzisiejszych: pasek wraca, gdy wiki się zmieni.
        current = is_current(boosted, datetime.now(timezone.utc))
        if not current or not (boosted.creature or boosted.boss):
            self.hide()
            return
        self._fill(self._creature, boosted.creature, tr("Boosted potwór dnia: {name}", name=boosted.creature))
        self._fill(self._boss, boosted.boss, tr("Boosted boss dnia: {name}", name=boosted.boss))
        self.show()

    def _fill(self, button: QToolButton, name: str | None, tooltip: str) -> None:
        button.setVisible(name is not None)
        if name is None:
            return
        monster = self._by_name.get(name.lower())
        button.setText(name)
        self._targets[button] = monster
        # Nowy potwór, którego nie ma jeszcze w danych programu: nazwa bez klikania.
        button.setEnabled(monster is not None)
        hint = tooltip
        if monster is not None:
            hint += "\n" + tr("Kliknij, żeby otworzyć kartę.")
        button.setToolTip(hint)
        button.setIcon(self._icon(monster))

    def _icon(self, monster: Monster | None) -> QIcon:
        if monster is None or monster.image_url is None:
            return QIcon()
        if sprite_path(self._sprites_dir, monster.id) is None:
            self._download(monster)
            return QIcon()
        path = display_sprite(self._sprites_dir, monster.id)
        return QIcon(str(path)) if path else QIcon()

    def _download(self, monster: Monster) -> None:
        if monster.id in self._downloading:
            return
        self._downloading.add(monster.id)

        def work() -> None:
            try:
                ensure_sprite(self._sprites_dir, monster)
            except (OSError, ValueError) as exc:
                log.info("Nie udało się pobrać obrazka %s: %s", monster.id, exc)
            # Także po błędzie: bez tego kolejne odświeżenie nie spróbowałoby drugi raz.
            self._signals.sprite.emit(monster.id)

        threading.Thread(target=work, daemon=True, name="boosted-sprite").start()

    def _on_sprite(self, monster_id: str) -> None:
        self._downloading.discard(monster_id)
        if sprite_path(self._sprites_dir, monster_id) is not None:
            self._render()

    def _open(self, button: QToolButton) -> None:
        monster = self._targets.get(button)
        if monster is not None:
            self.monster_requested.emit(monster)
