"""Przycisk „Stream” z kropką: zielona = autor nadaje na Kick, szara = offline albo nie wiadomo."""

import threading

from PySide6.QtCore import QEasingCurve, QObject, Qt, QTimer, QUrl, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QToolButton

from ..core import stream
from ..core.i18n import tr

LIVE_COLOR = "#53c43b"  # zieleń podobna do Kick
OFF_COLOR = "#8b9099"
PULSE_MS = 2400  # jeden cykl ramki: przygaśnięcie i powrót


class _Result(QObject):
    """Przenosi wynik z wątku w tle do wątku okna (okna Qt zmieniamy tylko w głównym wątku)."""

    checked = Signal(object)  # True / False / None


class StreamButton(QToolButton):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setText(" Stream")
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(stream.CHANNEL_URL)))
        self._result = _Result(self)
        self._result.checked.connect(self.set_live)
        self._busy = False

        # Gdy stream trwa, zielona ramka płynnie przygasa i wraca (krycie 25% -> 100% -> 25%).
        self._pulse = QVariantAnimation(self, duration=PULSE_MS, loopCount=-1)
        self._pulse.setKeyValueAt(0.0, 0.25)
        self._pulse.setKeyValueAt(0.5, 1.0)
        self._pulse.setKeyValueAt(1.0, 0.25)
        self._pulse.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._pulse.valueChanged.connect(self._set_border)
        self.set_live(None)

        # Pierwsze sprawdzenie od razu, potem co kilka minut.
        self._timer = QTimer(self, interval=stream.CHECK_EVERY_MS)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        QTimer.singleShot(0, self.refresh)

    def refresh(self) -> None:
        if self._busy:  # poprzednie pytanie jeszcze trwa (wolny internet)
            return
        self._busy = True
        # Zapytanie w tle, żeby okno nie zamarzło. daemon=True: zamknięcie okna nie czeka.
        threading.Thread(target=lambda: self._result.checked.emit(stream.is_live()), daemon=True, name="stream").start()

    def set_live(self, live: bool | None) -> None:
        self._busy = False
        self.setIcon(_dot(LIVE_COLOR if live else OFF_COLOR))
        if live:
            # Sprawdzenie co 3 minuty nie restartuje trwającej animacji (bez skoku jasności).
            if self._pulse.state() != QVariantAnimation.State.Running:
                self._pulse.start()
            self.setToolTip(tr("Stream trwa na Kick. Kliknij, żeby oglądać."))
            return
        # Bez streamu animacja stoi (nie zużywa procesora), a ramka wraca do koloru z motywu.
        self._pulse.stop()
        self.setStyleSheet("")
        if live is False:
            self.setToolTip(tr("Stream offline. Kliknij, żeby otworzyć kanał na Kick."))
        else:
            self.setToolTip(tr("Nie udało się sprawdzić, czy stream trwa. Kliknij, żeby otworzyć kanał na Kick."))

    def _set_border(self, opacity: float) -> None:
        # Tylko ramka: tło, zaokrąglenie i odstępy zostają z motywu (style się łączą).
        color = QColor(LIVE_COLOR)
        self.setStyleSheet(f"border: 2px solid rgba({color.red()}, {color.green()}, {color.blue()}, {opacity:.2f});")


def _dot(color: str) -> QIcon:
    pixmap = QPixmap(16, 16)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))
    painter.drawEllipse(3, 3, 10, 10)
    painter.end()
    return QIcon(pixmap)
