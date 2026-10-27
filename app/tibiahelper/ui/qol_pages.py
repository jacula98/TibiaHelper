"""Zakładka „Quality of life”: drobne ułatwienia (minimapa Tibii, loot filter i ceny, UI i hotkeye)."""

import threading
from html import escape
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..core import client_options, loot_settings, minimap
from ..core.i18n import tr
from . import theme

TIBIA_MAPS_URL = "https://tibiamaps.io/"
YUUKICIU_URL = "https://www.youtube.com/watch?v=4fIlbgTtXMg"


class QolPage(QWidget):
    back_requested = Signal()
    loot_requested = Signal()
    maps_requested = Signal()
    ui_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addLayout(_top_bar(tr("← Menu"), self.back_requested))

        maps = _small_button("🗺  TibiaMaps", tr("Pełna minimapa z tibiamaps.io wgrana do Tibii"))
        maps.clicked.connect(self.maps_requested)
        layout.addWidget(maps)

        # „&&”, bo pojedynczy „&” Qt traktuje jako skrót klawiszowy i go nie pokazuje.
        loot = _small_button("💰  Loot filter && market", tr("Pomijanie śmieci i ceny z Marketu"))
        loot.clicked.connect(self.loot_requested)
        layout.addWidget(loot)

        ui = _small_button("⌨  UI + Hotkeys", tr("Czyste UI bez zbędnych animacji, podstawowe hotkeye"))
        ui.clicked.connect(self.ui_requested)
        layout.addWidget(ui)
        layout.addStretch(1)


class _InstallWorker(QObject):
    # Sygnały Qt przenoszą wynik z wątku pobierania do wątku okna (tylko tam wolno ruszać widżety).
    finished = Signal(bool)  # czy powstała kopia zapasowa
    failed = Signal(str)


class MinimapPage(QWidget):
    back_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        title = QLabel("TibiaMaps")
        title.setObjectName("title")

        self._markers = QCheckBox(tr("Markery"))
        self._markers.setChecked(True)
        self._grid = QCheckBox(tr("Siatka (grid overlay)"))
        self._upload = QPushButton(tr("Wgraj mapę"))
        self._upload.setObjectName("primary")
        self._upload.setCursor(Qt.CursorShape.PointingHandCursor)
        self._upload.clicked.connect(self._start)
        self._status = QLabel(wordWrap=True)
        info = QLabel(
            tr(
                "Program sam pobierze pełną minimapę z tibiamaps.io (ok. 7 MB) i wgra ją do Tibii. "
                "Na minimapie w grze zobaczysz od razu całą mapę świata.<br><br>"
                "Przed wgraniem zamknij Tibię. Przy pierwszym wgraniu stara minimapa (razem z Twoimi "
                "markerami) trafia do kopii w folderze „{folder}”. "
                "Bez zaznaczonych „Markerów” Twoje markery zostają, z nimi są podmieniane.",
                folder=minimap.BACKUP_NAME,
            ),
            wordWrap=True,
        )
        info.setObjectName("muted")
        source = QLabel(
            escape(tr("Źródło:")) + f' <a href="{TIBIA_MAPS_URL}" style="color: {theme.ACCENT};">tibiamaps.io</a>',
            openExternalLinks=True,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addLayout(_top_bar(tr("← Quality of life"), self.back_requested))
        layout.addWidget(title)
        layout.addWidget(self._markers)
        layout.addWidget(self._grid)
        layout.addWidget(self._upload)
        layout.addWidget(self._status)
        layout.addWidget(info)
        layout.addWidget(source)
        layout.addStretch(1)

        self._worker = _InstallWorker()
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)

    def _start(self) -> None:
        target = minimap.minimap_dir()
        if target is None or not target.parent.is_dir():
            QMessageBox.warning(self, tr("Wgraj mapę"), tr("Nie znalazłem Tibii na tym komputerze."))
            return
        # Klient zapisuje minimapę przy zamknięciu, więc przy włączonej Tibii nadpisałby nową.
        answer = QMessageBox.question(
            self, tr("Wgraj mapę"), tr("Czy Tibia jest zamknięta? Pobrać i wgrać minimapę?")
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        url = minimap.package_url(self._markers.isChecked(), self._grid.isChecked())
        self._upload.setEnabled(False)
        self._status.setText(tr("Pobieram i wgrywam minimapę…"))
        # daemon=True: zamknięcie programu nie czeka na pobieranie.
        threading.Thread(target=self._run, args=(url, target), daemon=True, name="minimap").start()

    def _run(self, url: str, target: Path) -> None:
        try:
            files = minimap.read_package(minimap.download(url))
            made_backup = minimap.install(target, files)
        # Szeroko: nieobsłużony błąd w wątku zostawiłby wyłączony przycisk i wiszący napis.
        except Exception as exc:  # noqa: BLE001
            self._worker.failed.emit(str(exc))
            return
        self._worker.finished.emit(made_backup)

    def _on_finished(self, made_backup: bool) -> None:
        self._upload.setEnabled(True)
        text = tr("Gotowe. Uruchom Tibię, minimapa jest już pełna.")
        if made_backup:
            text += " " + tr("Stara minimapa jest w folderze „{folder}”.", folder=minimap.BACKUP_NAME)
        self._status.setText(text)

    def _on_failed(self, error: str) -> None:
        self._upload.setEnabled(True)
        self._status.setText(tr("Nie udało się wgrać minimapy: {error}", error=error))


class LootSettingsPage(QWidget):
    back_requested = Signal()

    def __init__(self, source_dir: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._source_dir = source_dir

        title = QLabel("Loot filter & market")
        title.setObjectName("title")
        upload = QPushButton(tr("Wgraj"))
        upload.setObjectName("primary")
        upload.setCursor(Qt.CursorShape.PointingHandCursor)
        upload.clicked.connect(self._upload)
        info = QLabel(
            tr(
                "Kliknięcie przycisku „Wgraj” sprawi, że na każdą postać na koncie zostaną wgrane "
                "ustawienia skipowania typowych śmieci oraz ustawienia Market Price na itemach, "
                "które są do delivery tasków lub imbu.<br><br>"
                "Przed wgraniem zamknij Tibię. Twoje dotychczasowe listy zostają (dopisujemy do nich), "
                "a oryginalne pliki trafiają do kopii z końcówką „{suffix}”.",
                suffix=loot_settings.BACKUP_SUFFIX,
            ),
            wordWrap=True,
        )
        info.setObjectName("muted")
        source = QLabel(
            escape(tr("Źródło:")) + f' <a href="{YUUKICIU_URL}" style="color: {theme.ACCENT};">Yuukiciu</a> (YouTube)',
            openExternalLinks=True,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addLayout(_top_bar(tr("← Quality of life"), self.back_requested))
        layout.addWidget(title)
        layout.addWidget(upload)
        layout.addWidget(info)
        layout.addWidget(source)
        layout.addStretch(1)

    def _upload(self) -> None:
        base = loot_settings.characterdata_dir()
        folders = loot_settings.character_dirs(base) if base else []
        if not folders:
            QMessageBox.warning(
                self,
                tr("Wgraj"),
                tr(
                    "Nie znalazłem postaci Tibii na tym komputerze.\n"
                    "Zaloguj się raz każdą postacią w kliencie i spróbuj ponownie."
                ),
            )
            return
        # Klient zapisuje swoje ustawienia przy zamknięciu, więc przy włączonej Tibii by je nadpisał.
        answer = QMessageBox.question(
            self,
            tr("Wgraj"),
            tr("Znalazłem postacie: {n}.\nCzy Tibia jest zamknięta? Wgrać ustawienia?", n=len(folders)),
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            result = loot_settings.install(base, self._source_dir)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, tr("Wgraj"), tr("Nie udało się wczytać ustawień do wgrania:\n{error}", error=exc))
            return
        text = tr("Gotowe. Wgrano na postacie: {n}.", n=result.characters)
        if result.errors:
            text += "\n\n" + tr("Nie udało się dla:") + "\n" + "\n".join(result.errors)
        QMessageBox.information(self, tr("Wgraj"), text)


class UiHotkeysPage(QWidget):
    back_requested = Signal()

    def __init__(self, source: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._source = source

        title = QLabel("UI + Hotkeys")
        title.setObjectName("title")
        upload = QPushButton(tr("Wgraj"))
        upload.setObjectName("primary")
        upload.setCursor(Qt.CursorShape.PointingHandCursor)
        upload.clicked.connect(self._upload)
        info = QLabel(
            tr(
                "Kliknięcie „Wgraj” ustawi w Tibii oczyszczone UI z nadmiaru animacji i komunikatów, "
                "podstawowe hotkeye (zestawy Basic, Knight, Paladin, Sorcerer, Druid, Monk), przyciski "
                "na pasku i action bary (m.in. czary i podróże statkiem).<br><br>"
                "Ustawienia dotyczą całego konta. Twoje logowanie, dźwięk, grafika i pozycja okna zostają. "
                "Zestawy hotkeyów o tych samych nazwach zostaną podmienione, inne zostają. Przed wgraniem "
                "zamknij Tibię. Oryginalny plik trafia do kopii z końcówką „{suffix}”.",
                suffix=client_options.BACKUP_SUFFIX,
            ),
            wordWrap=True,
        )
        info.setObjectName("muted")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addLayout(_top_bar(tr("← Quality of life"), self.back_requested))
        layout.addWidget(title)
        layout.addWidget(upload)
        layout.addWidget(info)
        layout.addStretch(1)

    def _upload(self) -> None:
        target = client_options.options_file()
        # Folder Tibii (packages/Tibia) musi istnieć; sam plik może jeszcze nie istnieć.
        if target is None or not target.parent.parent.is_dir():
            QMessageBox.warning(self, tr("Wgraj"), tr("Nie znalazłem Tibii na tym komputerze."))
            return
        # Klient zapisuje ustawienia przy zamknięciu, więc przy włączonej Tibii by je nadpisał.
        answer = QMessageBox.question(self, tr("Wgraj"), tr("Czy Tibia jest zamknięta? Wgrać UI i hotkeye?"))
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            made_backup = client_options.install(target, self._source)
        except (OSError, ValueError, TypeError) as exc:
            QMessageBox.warning(self, tr("Wgraj"), tr("Nie udało się wgrać ustawień:\n{error}", error=exc))
            return
        text = tr("Gotowe. Uruchom Tibię, UI i hotkeye są ustawione.")
        if made_backup:
            text += "\n" + tr("Stary plik: {name}", name=target.name + client_options.BACKUP_SUFFIX)
        QMessageBox.information(self, tr("Wgraj"), text)


def _top_bar(text: str, signal: Signal) -> QHBoxLayout:
    back = QPushButton(text)
    back.clicked.connect(signal)
    top = QHBoxLayout()
    top.addWidget(back)
    top.addStretch(1)
    return top


def _small_button(text: str, hint: str) -> QPushButton:
    # Jak przyciski w menu głównym, tylko mniejsze (styl „submenu” w theme.py).
    button = QPushButton(f"{text}\n{hint}")
    button.setObjectName("submenu")
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button
