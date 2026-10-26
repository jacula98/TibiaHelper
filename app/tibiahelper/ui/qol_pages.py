"""Zakładka „Quality of life”: drobne ułatwienia (mapa Tibii, ustawienia lootu i cen)."""

from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

from ..core import loot_settings
from . import theme

TIBIA_MAPS_URL = "https://tibiamaps.io/"
YUUKICIU_URL = "https://www.youtube.com/watch?v=4fIlbgTtXMg"


class QolPage(QWidget):
    back_requested = Signal()
    loot_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addLayout(_top_bar("← Menu", self.back_requested))

        maps = _small_button("🗺  Mapa Tibii", "Otwiera tibiamaps.io w przeglądarce")
        maps.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(TIBIA_MAPS_URL)))
        layout.addWidget(maps)

        # „&&”, bo pojedynczy „&” Qt traktuje jako skrót klawiszowy i go nie pokazuje.
        loot = _small_button("💰  Loot filter && market", "Pomijanie śmieci i ceny z Marketu")
        loot.clicked.connect(self.loot_requested)
        layout.addWidget(loot)
        layout.addStretch(1)


class LootSettingsPage(QWidget):
    back_requested = Signal()

    def __init__(self, source_dir: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._source_dir = source_dir

        title = QLabel("Loot filter & market")
        title.setObjectName("title")
        upload = QPushButton("Wgraj")
        upload.setObjectName("primary")
        upload.setCursor(Qt.CursorShape.PointingHandCursor)
        upload.clicked.connect(self._upload)
        info = QLabel(
            "Kliknięcie przycisku „Wgraj” sprawi, że na każdą postać na koncie zostaną wgrane "
            "ustawienia skipowania typowych śmieci oraz ustawienia Market Price na itemach, "
            "które są do delivery tasków lub imbu.<br><br>"
            "Przed wgraniem zamknij Tibię. Twoje dotychczasowe listy zostają (dopisujemy do nich), "
            f"a oryginalne pliki trafiają do kopii z końcówką „{loot_settings.BACKUP_SUFFIX}”.",
            wordWrap=True,
        )
        info.setObjectName("muted")
        source = QLabel(
            f'Źródło: <a href="{YUUKICIU_URL}" style="color: {theme.ACCENT};">Yuukiciu</a> (YouTube)',
            openExternalLinks=True,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addLayout(_top_bar("← Quality of life", self.back_requested))
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
                self, "Wgraj", "Nie znalazłem postaci Tibii na tym komputerze.\n"
                "Zaloguj się raz każdą postacią w kliencie i spróbuj ponownie."
            )
            return
        # Klient zapisuje swoje ustawienia przy zamknięciu, więc przy włączonej Tibii by je nadpisał.
        answer = QMessageBox.question(
            self, "Wgraj", f"Znalazłem postacie: {len(folders)}.\nCzy Tibia jest zamknięta? Wgrać ustawienia?"
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            result = loot_settings.install(base, self._source_dir)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Wgraj", f"Nie udało się wczytać ustawień do wgrania:\n{exc}")
            return
        text = f"Gotowe. Wgrano na postacie: {result.characters}."
        if result.errors:
            text += "\n\nNie udało się dla:\n" + "\n".join(result.errors)
        QMessageBox.information(self, "Wgraj", text)


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
