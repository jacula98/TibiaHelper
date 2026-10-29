"""Powiadomienia o bossach: „boss na serwerze” (statystyki z TibiaData) i timery respawnu.

BossWatcher co jakiś czas sprawdza statystyki wybranego świata (w wątku w tle) i timery
ustawione przez gracza. Powiadomienie to okienko w programie (nad grą) z krótkim dźwiękiem.
Przycisk „Pokaż bossa” otwiera bossa w zakładce Bossy.
"""

import threading
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..core.boss_timers import BossTimer, due_warnings, format_left, load_timers, make_timer, save_timers
from ..core.boss_watch import Sighting, WatchedBoss, WatchResult, check_world, is_current
from ..core.i18n import tr
from ..core.models import Monster

# Statystyki zmieniają się raz na dobę: co 30 minut sprawdzamy tylko, czy zaczął się nowy dzień
# (TibiaData pytamy dopiero wtedy). Timery sprawdzamy co minutę, bo to tylko liczenie.
STATS_EVERY_MS = 30 * 60 * 1000
TIMERS_EVERY_MS = 60 * 1000
DEFAULT_RESPAWN = (3, 7)  # gdy autor nie podał okna respawnu; gracz może je zmienić


def sighting_text(sighting: Sighting) -> str:
    """„Tyrn: zabił graczy: 2, zabity: 1×”. Nazwa jest z wiki, ale i tak przechodzi przez escape tam, gdzie HTML."""
    parts = []
    if sighting.players_killed:
        parts.append(tr("zabił graczy: {n}", n=sighting.players_killed))
    if sighting.killed:
        parts.append(tr("zabity: {n}×", n=sighting.killed))
    return f"{sighting.name}: {', '.join(parts)}"


class _Signals(QObject):
    # Wynik z wątku w tle: Qt dostarcza sygnał w głównym wątku, gdzie wolno zmieniać okno.
    result = Signal(str, object, bool)  # (świat, o który pytaliśmy, wynik, czy nowy)


class BossWatcher(QObject):
    alert = Signal(str, str, str)  # (tytuł, tekst, id potwora do otwarcia)
    changed = Signal()  # nowe statystyki albo zmiana timerów: strona bossa odświeża się

    def __init__(self, watch_cache: Path, timers_file: Path, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._cache = watch_cache
        self._timers_file = timers_file
        self._timers: dict[str, BossTimer] = load_timers(timers_file)
        self._names: dict[str, str] = {}  # id -> nazwa bossów do sprawdzania
        self._watched: dict[str, WatchedBoss] = {}
        self._monsters: dict[str, Monster] = {}
        self._world: str | None = None
        self._result: WatchResult | None = None
        self._busy = False
        self._signals = _Signals(self)
        self._signals.result.connect(self._on_result)
        self._stats_timer = QTimer(self, interval=STATS_EVERY_MS)
        self._stats_timer.timeout.connect(self._check_stats)
        self._timers_timer = QTimer(self, interval=TIMERS_EVERY_MS)
        self._timers_timer.timeout.connect(self._check_timers)

    # --- dane ---

    def set_bosses(self, monsters: dict[str, Monster], watched: dict[str, WatchedBoss]) -> None:
        self._monsters = monsters
        self._watched = watched
        self._names = {mid: monsters[mid].name for mid in watched if mid in monsters}

    def set_world(self, world: str | None) -> None:
        if world == self._world:
            return
        self._world = world
        self._result = None
        self.changed.emit()
        self._check_stats()

    @property
    def world(self) -> str | None:
        return self._world

    def start(self) -> None:
        """Pierwsze sprawdzenie od razu. Osobno od __init__, żeby testy nie łączyły się z siecią."""
        self._check_stats()
        self._check_timers()
        self._stats_timer.start()
        self._timers_timer.start()

    def default_respawn(self, monster_id: str) -> tuple[int, int]:
        boss = self._watched.get(monster_id)
        return boss.respawn_days if boss and boss.respawn_days else DEFAULT_RESPAWN

    def has_known_respawn(self, monster_id: str) -> bool:
        boss = self._watched.get(monster_id)
        return boss is not None and boss.respawn_days is not None

    def sighting(self, monster_id: str) -> Sighting | None:
        if self._result is None:
            return None
        return next((s for s in self._result.sightings if s.monster == monster_id), None)

    def timer(self, monster_id: str) -> BossTimer | None:
        return self._timers.get(monster_id)

    def set_timer(self, monster_id: str, killed_at: datetime, min_days: int, max_days: int) -> None:
        self._timers[monster_id] = make_timer(killed_at, min_days, max_days)
        save_timers(self._timers_file, self._timers)
        self.changed.emit()
        self._check_timers()

    def clear_timer(self, monster_id: str) -> None:
        if self._timers.pop(monster_id, None) is not None:
            save_timers(self._timers_file, self._timers)
            self.changed.emit()

    # --- sprawdzanie ---

    def _check_stats(self) -> None:
        world = self._world
        now = datetime.now(timezone.utc)
        if world is None or not self._names or self._busy or is_current(self._result, world, now):
            return
        self._busy = True
        names = dict(self._names)

        def work() -> None:
            result, fresh = check_world(self._cache, world, names, datetime.now(timezone.utc))
            self._signals.result.emit(world, result, fresh)

        # daemon=True: zamknięcie programu nie czeka na pobieranie.
        threading.Thread(target=work, daemon=True, name="boss-watch").start()

    def _on_result(self, world: str, result: WatchResult | None, fresh: bool) -> None:
        self._busy = False
        if world != self._world:
            # W międzyczasie gracz zmienił świat: od razu pytamy o nowy, zamiast czekać 30 minut.
            self._check_stats()
            return
        if result is None:
            return
        self._result = result
        self.changed.emit()
        if fresh and result.sightings:
            names = "\n".join(sighting_text(s) for s in result.sightings)
            title = tr("Bossy na {world} (ostatnia doba)", world=result.world)
            self._notify(title, names, result.sightings[0].monster)

    def _check_timers(self) -> None:
        now = datetime.now(timezone.utc)
        due = due_warnings(self._timers, now)
        if not due:
            return
        for monster_id in due:
            timer = self._timers[monster_id]
            self._timers[monster_id] = BossTimer(timer.killed_at, timer.min_days, timer.max_days, notified=True)
        save_timers(self._timers_file, self._timers)
        self.changed.emit()
        names = ", ".join(self._monster_name(mid) for mid in due)
        self._notify(tr("Boss może się zaraz pojawić"), tr("Kończy się timer: {names}", names=names), due[0])

    def _monster_name(self, monster_id: str) -> str:
        monster = self._monsters.get(monster_id)
        return monster.name if monster else monster_id

    # --- powiadomienie ---

    def _notify(self, title: str, text: str, monster_id: str) -> None:
        # Krótki dźwięk systemu (na Windows ten sam co przy komunikatach); okienko pokazuje główne okno.
        QApplication.beep()
        self.alert.emit(title, text, monster_id)


class AlertPopup(QDialog):
    """Okienko „Bossy na Antica…” nad oknem programu, z przyciskami Pokaż bossa / Zamknij.

    Bez blokowania programu (nie modalne) i zawsze na wierzchu, jak całe okno, żeby nie schowało się pod grą.
    """

    open_requested = Signal(str)  # id potwora

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("TibiaHelper")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setModal(False)
        self.setMinimumWidth(300)
        self._target = ""
        # PlainText: nazwy bossów są z danych, więc nie dajemy Qt zgadywać, czy to HTML.
        self._title = QLabel(wordWrap=True, textFormat=Qt.TextFormat.PlainText)
        self._title.setObjectName("sectionTitle")
        self._text = QLabel(wordWrap=True, textFormat=Qt.TextFormat.PlainText)
        close = QPushButton(tr("Zamknij"))
        close.clicked.connect(self.hide)
        show = QPushButton(tr("Pokaż bossa"))
        show.setObjectName("primary")
        show.setDefault(True)
        show.clicked.connect(self._open)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(close)
        buttons.addWidget(show)
        layout = QVBoxLayout(self)
        layout.addWidget(self._title)
        layout.addWidget(self._text)
        layout.addLayout(buttons)

    def show_alert(self, title: str, text: str, monster_id: str) -> None:
        # Nowe powiadomienie, gdy stare jest jeszcze otwarte: podmieniamy treść zamiast drugiego okienka.
        self._target = monster_id
        self._title.setText(title)
        self._text.setText(text)
        self.adjustSize()
        self.show()
        self.raise_()

    def _open(self) -> None:
        self.hide()
        self.open_requested.emit(self._target)


class BossTimerBox(QFrame):
    """Na stronie bossa: co mówią statystyki świata i timer „zabity” z oknem respawnu."""

    def __init__(self, watcher: BossWatcher, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._watcher = watcher
        self._monster_id: str | None = None
        title = QLabel(tr("NA SERWERZE I TIMER RESPAWNU"))
        title.setObjectName("sectionTitle")
        self._seen = QLabel(wordWrap=True, textFormat=Qt.TextFormat.PlainText)
        self._status = QLabel(wordWrap=True, textFormat=Qt.TextFormat.RichText)
        self._min = QSpinBox(minimum=1, maximum=400, suffix=tr(" d"))
        self._max = QSpinBox(minimum=1, maximum=400, suffix=tr(" d"))
        self._hint = QLabel(wordWrap=True)
        self._hint.setObjectName("muted")
        window = QHBoxLayout()
        window.addWidget(QLabel(tr("Respawn za:")))
        window.addWidget(self._min)
        window.addWidget(QLabel("–"))
        window.addWidget(self._max)
        window.addStretch(1)
        now = QPushButton(tr("Zabity teraz"))
        now.clicked.connect(lambda: self._start(timedelta(0)))
        yesterday = QPushButton(tr("Zabity wczoraj"))
        yesterday.setToolTip(tr("Np. gdy statystyki pokazały, że boss zginął w ostatniej dobie."))
        yesterday.clicked.connect(lambda: self._start(timedelta(days=1)))
        self._clear = QPushButton(tr("Usuń timer"))
        self._clear.clicked.connect(lambda: self._monster_id and self._watcher.clear_timer(self._monster_id))
        buttons = QHBoxLayout()
        buttons.addWidget(now)
        buttons.addWidget(yesterday)
        buttons.addWidget(self._clear)
        buttons.addStretch(1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.addWidget(title)
        layout.addWidget(self._seen)
        layout.addWidget(self._status)
        layout.addLayout(window)
        layout.addWidget(self._hint)
        layout.addLayout(buttons)
        watcher.changed.connect(self.refresh)
        # Co minutę odświeżamy „za ile”, gdy strona jest otwarta.
        self._tick = QTimer(self, interval=TIMERS_EVERY_MS)
        self._tick.timeout.connect(self.refresh)
        self._tick.start()

    def show_boss(self, monster_id: str) -> None:
        self._monster_id = monster_id
        timer = self._watcher.timer(monster_id)
        low, high = (timer.min_days, timer.max_days) if timer else self._watcher.default_respawn(monster_id)
        self._min.setValue(low)
        self._max.setValue(high)
        self._hint.setText(
            tr("Okno respawnu z wykresów TibiaWiki (dane GuildStats.eu). Możesz je zmienić.")
            if self._watcher.has_known_respawn(monster_id)
            else tr("Okno respawnu nie jest znane: wpisz je sam (np. z opisu bossa na wiki).")
        )
        self.refresh()

    def refresh(self) -> None:
        if self._monster_id is None:
            return
        world = self._watcher.world
        sighting = self._watcher.sighting(self._monster_id)
        if world is None:
            self._seen.setText(tr("Wybierz świat w ustawieniach (⚙), żeby dostawać powiadomienia o bossach."))
        elif sighting is None:
            self._seen.setText(tr("Ostatnia doba na {world}: brak w statystykach.", world=world))
        else:
            self._seen.setText(tr("Ostatnia doba na {world}: {info}", world=world, info=sighting_text(sighting)))
        timer = self._watcher.timer(self._monster_id)
        self._clear.setVisible(timer is not None)
        self._status.setText(timer_html(timer, datetime.now(timezone.utc)))

    def _start(self, ago: timedelta) -> None:
        if self._monster_id is not None:
            killed_at = datetime.now(timezone.utc) - ago
            self._watcher.set_timer(self._monster_id, killed_at, self._min.value(), self._max.value())


def timer_html(timer: BossTimer | None, now: datetime) -> str:
    """Stan timera po ludzku: „może się pojawić za 2 d 5 h” / „okno respawnu trwa” / „po oknie”."""
    if timer is None:
        return escape(tr("Timer nie jest ustawiony."))

    def local(moment: datetime) -> str:
        return moment.astimezone().strftime("%d.%m %H:%M")

    window = tr("okno: {start} – {end}", start=local(timer.window_start), end=local(timer.window_end))
    if now < timer.window_start:
        state = tr("Może się pojawić za {left}", left=format_left(timer.window_start - now))
    elif now < timer.window_end:
        state = tr("Okno respawnu trwa: boss może już być (koniec za {left})", left=format_left(timer.window_end - now))
    else:
        state = tr("Okno respawnu minęło: boss powinien już być.")
    killed = tr("Zabity: {when}", when=local(timer.killed_at))
    return f"<b>{escape(state)}</b><br>{escape(killed)} · {escape(window)}"
