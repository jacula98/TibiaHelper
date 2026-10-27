"""„Ostatnie raporty graczy” pod bossem i miejscem huntu (z formularza Google).

ReportFeed pobiera arkusz w tle i trzyma raporty dla całego programu.
ReportList pokazuje raporty jednego bossa albo miejsca: 5 najnowszych,
a „Pokaż więcej” rozwija kolejne.
"""

import threading
import time
from html import escape
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from ..core.i18n import tr
from ..core.reports import Report, get_reports, reports_for
from . import theme

FIRST = 5  # tyle raportów widać od razu
MORE = 10  # tyle dochodzi po każdym „Pokaż więcej”


class ReportFeed(QObject):
    """Wspólne raporty dla stron bossów i huntów. Pobieranie w wątku, wynik przez sygnał."""

    changed = Signal()
    _loaded = Signal(object)

    def __init__(self, cache: Path, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._cache = cache
        self.reports: list[Report] = []
        self.ready = False  # False do pierwszego wyniku: lista pokazuje „Wczytuję…”
        self._busy = False
        self._loaded.connect(self._on_loaded)

    def refresh(self) -> None:
        """Wołane przy otwarciu strony. get_reports sam pilnuje, żeby nie pytać częściej niż co 15 min."""
        if self._busy:
            return
        self._busy = True

        def work() -> None:
            # Sygnał przenosi wynik do wątku okna (widżetów Qt nie wolno zmieniać z innego wątku).
            self._loaded.emit(get_reports(self._cache, time.time()))

        threading.Thread(target=work, daemon=True, name="reports").start()

    def _on_loaded(self, reports: list[Report]) -> None:
        self._busy = False
        self.reports = reports
        self.ready = True
        self.changed.emit()


class ReportList(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._feed: ReportFeed | None = None
        self._subject = ""
        self._shown = FIRST
        title = QLabel(tr("OSTATNIE RAPORTY GRACZY"))
        title.setObjectName("sectionTitle")
        self._list = QLabel(wordWrap=True, textFormat=Qt.TextFormat.RichText)
        self._list.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._more = QPushButton()
        self._more.clicked.connect(self._show_more)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(title)
        layout.addWidget(self._list)
        layout.addWidget(self._more, 0, Qt.AlignmentFlag.AlignLeft)
        self.hide()  # bez źródła raportów (np. w testach) lista jest niewidoczna

    def set_feed(self, feed: ReportFeed) -> None:
        self._feed = feed
        feed.changed.connect(self._render)

    def set_subject(self, subject: str) -> None:
        """Nowa strona (boss albo miejsce): od początku 5 raportów i odświeżenie arkusza."""
        self._subject = subject
        self._shown = FIRST
        if self._feed is None:
            return
        self.show()
        self._render()
        self._feed.refresh()

    def _show_more(self) -> None:
        self._shown += MORE
        self._render()

    def _render(self) -> None:
        if self._feed is None:
            return
        reports = reports_for(self._feed.reports, self._subject)
        if not reports:
            text = tr("Wczytuję…") if not self._feed.ready else tr("Brak raportów. Wyślij pierwszy przyciskiem 📨 na dole.")
            self._list.setText(f'<span style="color:{theme.MUTED}">{escape(text)}</span>')
            self._more.hide()
            return
        self._list.setText(reports_html(reports[: self._shown]))
        rest = len(reports) - self._shown
        self._more.setVisible(rest > 0)
        self._more.setText(tr("Pokaż więcej ({count})", count=rest))


def reports_html(reports: list[Report]) -> str:
    """Raporty jako HTML. Wszystko wpisali gracze, więc każdy tekst przez escape."""
    parts = []
    for report in reports:
        who = escape(report.author) if report.author else escape(tr("anonim"))
        head = f'<span style="color:{theme.MUTED}">{escape(report.date)} · {who}</span>'
        # Raport zachowuje swoje linie (Hunt Analyzer ma ich kilkanaście).
        body = escape(report.loot).replace("\n", "<br>")
        comment = f"<br><i>{escape(report.comment)}</i>" if report.comment else ""
        parts.append(f"<p>{head}<br>{body}{comment}</p>")
    note = escape(tr("Raporty wysyłają gracze. Nikt ich nie sprawdza."))
    return "".join(parts) + f'<p style="color:{theme.MUTED}"><small>{note}</small></p>'
