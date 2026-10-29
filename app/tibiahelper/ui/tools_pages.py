"""Zakładka „Narzędzia”: cena ze Store, podział lootu, stamina i skille (logika w core/calculators.py)."""

from datetime import datetime, timedelta
from html import escape

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..core.calculators import (
    BONUS_STAMINA,
    LOW_STAMINA,
    MAX_STAMINA,
    StoreRow,
    format_gold,
    format_minutes,
    offline_minutes_needed,
    parse_party_analyzer,
    parse_stamina,
    skill_plan,
    split_loot,
    store_rows,
)
from ..core.i18n import N_, tr
from ..core.items import cheapest_buy_price
from ..core.models import Item
from . import theme
from .qol_pages import _small_button, _top_bar


class ToolsPage(QWidget):
    back_requested = Signal()
    store_requested = Signal()
    party_requested = Signal()
    stamina_requested = Signal()
    skills_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addLayout(_top_bar(tr("← Menu"), self.back_requested))

        store = _small_button("🪙  " + tr("Cena ze Store"), tr("Ile goldów i pieniędzy kosztuje rzecz za Tibia Coins"))
        store.clicked.connect(self.store_requested)
        layout.addWidget(store)

        party = _small_button("⚖  " + tr("Podział lootu"), tr("Kto komu ile przelewa po huncie w party"))
        party.clicked.connect(self.party_requested)
        layout.addWidget(party)

        stamina = _small_button("⏳  " + tr("Stamina"), tr("Ile być offline do pełnej staminy"))
        stamina.clicked.connect(self.stamina_requested)
        layout.addWidget(stamina)

        skills = _small_button("🏋  " + tr("Skille"), tr("Ile exercise weapons do wybranego skilla"))
        skills.clicked.connect(self.skills_requested)
        layout.addWidget(skills)
        layout.addStretch(1)


# Kategorie Store (klucze z core/calculators.py) -> napis na przycisku. None = wszystkie.
_STORE_FILTERS = (
    (None, N_("Wszystkie")),
    ("potions", "Potions"),
    ("kegs", "Kegs"),
    ("casks", "Casks"),
    ("runes", "Runes"),
    ("other", N_("Inne")),
)


class StorePricePage(QWidget):
    back_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._npc_prices: dict[str, int] = {}
        self._category: str | None = None
        title = QLabel(tr("Cena ze Store"))
        title.setObjectName("title")

        # QSpinBox zamiast wolnego tekstu: gracz nie wpisze liter, a lista liczy się od razu.
        self._coin_gold = QSpinBox(minimum=1, maximum=10_000_000, singleStep=1_000, value=40_000, suffix=" gp")
        self._coin_gold.setGroupSeparatorShown(True)
        self._coin_gold.valueChanged.connect(self._refresh)
        form = QFormLayout()
        form.addRow(tr("Cena 1 Tibia Coina:"), self._coin_gold)

        # Filtry jako przełączane przyciski w grupie: zawsze zaznaczony dokładnie jeden.
        chips = QHBoxLayout()
        chips.setSpacing(3)
        group = QButtonGroup(self)
        for index, (key, label) in enumerate(_STORE_FILTERS):
            chip = QPushButton(tr(label))
            chip.setObjectName("chip")
            chip.setCheckable(True)
            chip.setChecked(index == 0)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.clicked.connect(lambda _=False, k=key: self._set_category(k))
            group.addButton(chip)
            chips.addWidget(chip)
        chips.addStretch(1)

        self._rows = QVBoxLayout()
        self._rows.setSpacing(6)
        box = QWidget()
        box_layout = QVBoxLayout(box)
        box_layout.setContentsMargins(0, 0, 0, 0)
        box_layout.addLayout(self._rows)
        box_layout.addStretch(1)
        scroll = QScrollArea(widgetResizable=True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(box)
        info = QLabel(
            tr(
                "Cena TC na Markecie zmienia się codziennie: wpisz aktualną z gry. "
                "Zielona cena NPC: w Store taniej, czerwona: u NPC taniej. Ceny Store z TibiaWiki."
            ),
            wordWrap=True,
        )
        info.setObjectName("muted")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addLayout(_top_bar(tr("← Narzędzia"), self.back_requested))
        layout.addWidget(title)
        layout.addLayout(form)
        layout.addLayout(chips)
        layout.addWidget(scroll, 1)
        layout.addWidget(info)
        self._refresh()

    def set_items(self, items: dict[str, Item]) -> None:
        """Ceny u NPC do porównania (najtańszy NPC dla każdego przedmiotu)."""
        self._npc_prices = {name: p for name, item in items.items() if (p := cheapest_buy_price(item))}
        self._refresh()

    def _set_category(self, category: str | None) -> None:
        self._category = category
        self._refresh()

    def _refresh(self) -> None:
        while self._rows.count():
            widget = self._rows.takeAt(0).widget()
            if widget is not None:
                # hide() od razu: deleteLater() usuwa widżet dopiero w pętli zdarzeń, a do tego czasu byłby widoczny.
                widget.hide()
                widget.deleteLater()
        for row in store_rows(self._coin_gold.value(), self._npc_prices, self._category):
            self._rows.addWidget(_offer_row(row))


def _offer_row(row: StoreRow) -> QFrame:
    frame = QFrame()
    frame.setObjectName("offer")
    grid = QGridLayout(frame)
    grid.setContentsMargins(10, 6, 10, 6)
    grid.setHorizontalSpacing(8)
    grid.setVerticalSpacing(0)
    name = QLabel(f"<b>{escape(row.offer.name)}</b>")
    amount = tr("x{n} · {coins} TC", n=row.offer.amount, coins=row.offer.coins)
    if row.offer.unit:
        # Cask i keg napełniają potiony, więc „za sztukę” to cena jednego potionu.
        amount = tr("napełnia {n} · {coins} TC", n=row.offer.amount, coins=row.offer.coins)
    details = QLabel(amount)
    details.setObjectName("muted")
    gold = QLabel(f"<b>{format_gold(row.gold)} gp</b>")
    gold.setAlignment(Qt.AlignmentFlag.AlignRight)
    per_unit = tr("{gold} gp / szt.", gold=_per_unit(row.per_unit)) if row.offer.amount > 1 else ""
    if row.npc_per_unit is not None:
        color = theme.GOOD if row.cheaper_in_store else theme.BAD
        npc = escape(tr("NPC: {gold} gp", gold=format_gold(row.npc_per_unit)))
        per_unit = f"{per_unit}  <span style='color: {color};'>{npc}</span>".strip()
    unit = QLabel(per_unit)
    unit.setAlignment(Qt.AlignmentFlag.AlignRight)
    grid.addWidget(name, 0, 0)
    grid.addWidget(details, 1, 0)
    grid.addWidget(gold, 0, 1)
    grid.addWidget(unit, 1, 1)
    grid.setColumnStretch(0, 1)
    return frame


def _per_unit(value: float) -> str:
    # Poniżej 10 gp pokazujemy jedno miejsce po przecinku, inaczej pełne gp (jak 36.7 -> 37).
    return f"{value:,.1f}" if value < 10 else format_gold(round(value))


class PartyLootPage(QWidget):
    back_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        title = QLabel(tr("Podział lootu"))
        title.setObjectName("title")
        info = QLabel(
            tr("W Tibii otwórz Party Hunt Analyzer, kliknij „Copy to clipboard” i wklej tekst tutaj."),
            wordWrap=True,
        )
        info.setObjectName("muted")

        self._input = QPlainTextEdit(placeholderText=tr("Tekst z Party Hunt Analyzera"))
        self._input.setFixedHeight(110)
        self._input.textChanged.connect(self._update)
        paste = QPushButton(tr("Wklej ze schowka"))
        paste.setObjectName("primary")
        paste.setCursor(Qt.CursorShape.PointingHandCursor)
        paste.clicked.connect(self._paste)
        clear = QPushButton(tr("Wyczyść"))
        clear.clicked.connect(self._input.clear)
        buttons = QHBoxLayout()
        buttons.addWidget(paste)
        buttons.addWidget(clear)
        buttons.addStretch(1)

        self._summary = QLabel(wordWrap=True)
        self._summary.setTextFormat(Qt.TextFormat.RichText)
        # Przelewy w osobnym, przewijanym pudełku: przy 5+ graczach nie wypchną okna poza ekran.
        self._transfers = QVBoxLayout()
        self._transfers.setSpacing(6)
        box = QWidget()
        box_layout = QVBoxLayout(box)
        box_layout.setContentsMargins(0, 0, 0, 0)
        box_layout.addLayout(self._transfers)
        box_layout.addStretch(1)
        scroll = QScrollArea(widgetResizable=True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(box)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addLayout(_top_bar(tr("← Narzędzia"), self.back_requested))
        layout.addWidget(title)
        layout.addWidget(info)
        layout.addWidget(self._input)
        layout.addLayout(buttons)
        layout.addWidget(self._summary)
        layout.addWidget(scroll, 1)
        self._update()

    def _paste(self) -> None:
        self._input.setPlainText(QGuiApplication.clipboard().text())

    def _update(self) -> None:
        while self._transfers.count():
            widget = self._transfers.takeAt(0).widget()
            if widget is not None:
                # hide() od razu: deleteLater() usuwa widżet dopiero w pętli zdarzeń, a do tego czasu byłby widoczny.
                widget.hide()
                widget.deleteLater()
        members = parse_party_analyzer(self._input.toPlainText())
        if not self._input.toPlainText().strip():
            self._summary.setText("")
            return
        if len(members) < 2:
            self._summary.setText(tr("Nie widzę co najmniej dwóch graczy. Skopiuj cały Party Hunt Analyzer."))
            return
        split = split_loot(members)
        # Nazwy postaci pochodzą z wklejonego tekstu, więc escape przed wstawieniem do HTML.
        rows = [
            f"{escape(m.name)}{' 👑' if m.leader else ''}: {format_gold(m.balance)} gp" for m in members
        ]
        lines = [
            tr("Balans party: <b>{gold} gp</b>", gold=format_gold(split.total)),
            tr("Na gracza ({n}): <b>{gold} gp</b>", n=len(members), gold=format_gold(split.share)),
            "",
            *rows,
        ]
        if split.share < 0:
            lines.insert(2, tr("Hunt na minusie: każdy dokłada tyle samo."))
        self._summary.setText("<br>".join(lines))
        if not split.transfers:
            self._transfers.addWidget(QLabel(tr("Nikt nie musi nic przelewać.")))
            return
        heading = QLabel(tr("Przelewy u bankiera (kliknij „Kopiuj” i wklej w czacie NPC):"), wordWrap=True)
        heading.setObjectName("muted")
        self._transfers.addWidget(heading)
        for transfer in split.transfers:
            self._transfers.addWidget(self._transfer_row(transfer))

    def _transfer_row(self, transfer) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        # PlainText: nazwa z wklejonego tekstu nie może zostać zinterpretowana jako HTML.
        label = QLabel(
            tr("{sender} → {receiver}: {gold} gp", sender=transfer.sender, receiver=transfer.receiver,
               gold=format_gold(transfer.amount)),
            wordWrap=True,
        )
        label.setTextFormat(Qt.TextFormat.PlainText)
        copy = QPushButton(tr("Kopiuj"))
        copy.setCursor(Qt.CursorShape.PointingHandCursor)
        copy.setToolTip(transfer.command)
        copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(transfer.command))
        layout.addWidget(label, 1)
        layout.addWidget(copy)
        return row


class StaminaPage(QWidget):
    back_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        title = QLabel(tr("Stamina"))
        title.setObjectName("title")
        # Tekst „hh:mm”, bo tak gracz widzi staminę w kliencie i tak ją przepisze.
        self._current = QLineEdit(placeholderText=tr("np. 38:15"))
        self._target = QLineEdit(format_minutes(MAX_STAMINA))
        self._current.textChanged.connect(self._update)
        self._target.textChanged.connect(self._update)
        form = QFormLayout()
        form.addRow(tr("Twoja stamina:"), self._current)
        form.addRow(tr("Chcesz mieć:"), self._target)

        self._result = QLabel(wordWrap=True)
        self._result.setTextFormat(Qt.TextFormat.RichText)
        info = QLabel(
            tr(
                "Offline odnawia się 1 minuta staminy co 3 minuty, a powyżej 39:00 co 6 minut. "
                "Regeneracja rusza po 10 minutach od wylogowania. "
                "Od 39:00 premium ma +50% expa, poniżej 14:00 jest połowa expa i brak lootu."
            ),
            wordWrap=True,
        )
        info.setObjectName("muted")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addLayout(_top_bar(tr("← Narzędzia"), self.back_requested))
        layout.addWidget(title)
        layout.addLayout(form)
        layout.addWidget(self._result)
        layout.addWidget(info)
        layout.addStretch(1)
        self._update()

    def _update(self) -> None:
        current = parse_stamina(self._current.text())
        target = parse_stamina(self._target.text())
        if current is None or target is None:
            self._result.setText(tr("Wpisz staminę jako godziny:minuty, od 00:00 do 42:00."))
            return
        minutes = offline_minutes_needed(current, target)
        if minutes == 0:
            self._result.setText(tr("Masz już tyle staminy."))
            return
        ready = datetime.now() + timedelta(minutes=minutes)
        lines = [
            tr("Bądź offline: <b>{time}</b> (godz:min)", time=format_minutes(minutes)),
            tr("Wyloguj się teraz, a będzie gotowe o <b>{clock}</b>.", clock=ready.strftime("%H:%M")),
        ]
        if minutes >= 24 * 60:
            lines[-1] = tr("Wyloguj się teraz, a będzie gotowe {date} o <b>{clock}</b>.",
                           date=ready.strftime("%d.%m"), clock=ready.strftime("%H:%M"))
        if current < LOW_STAMINA:
            lines.append(tr("Teraz masz połowę expa i brak lootu (poniżej 14:00)."))
        elif current >= BONUS_STAMINA:
            lines.append(tr("Teraz masz bonus +50% expa (premium)."))
        self._result.setText("<br>".join(lines))


# Klucze z core/calculators.py -> nazwy pokazywane graczowi (nazwy profesji i skilli jak w grze).
_VOCATIONS = {"knight": "Knight", "paladin": "Paladin", "sorcerer": "Sorcerer", "druid": "Druid", "monk": "Monk"}
_SKILLS = {
    "melee": "Sword / Axe / Club",
    "distance": "Distance",
    "magic": "Magic level",
    "shielding": "Shielding",
    "fist": "Fist",
}


class SkillPage(QWidget):
    back_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        title = QLabel(tr("Skille"))
        title.setObjectName("title")
        self._vocation = QComboBox()
        for key, name in _VOCATIONS.items():
            self._vocation.addItem(name, key)
        self._skill = QComboBox()
        for key, name in _SKILLS.items():
            self._skill.addItem(name, key)
        self._current = QSpinBox(minimum=0, maximum=200, value=80)
        self._percent = QSpinBox(minimum=0, maximum=99, value=0, suffix=" %")
        self._target = QSpinBox(minimum=1, maximum=200, value=90)
        self._expert = QCheckBox(tr("Dummy w domu (+10%)"))
        self._double = QCheckBox(tr("Podwójny skill (event)"))
        for combo in (self._vocation, self._skill):
            combo.currentIndexChanged.connect(self._update)
        for spin in (self._current, self._percent, self._target):
            spin.valueChanged.connect(self._update)
        for box in (self._expert, self._double):
            box.toggled.connect(self._update)

        form = QFormLayout()
        form.addRow(tr("Profesja:"), self._vocation)
        form.addRow(tr("Skill:"), self._skill)
        form.addRow(tr("Obecny poziom:"), self._current)
        form.addRow(tr("Pasek do następnego:"), self._percent)
        form.addRow(tr("Cel:"), self._target)

        self._result = QLabel(wordWrap=True)
        self._result.setTextFormat(Qt.TextFormat.RichText)
        info = QLabel(
            tr(
                "Wpisz skill bez bonusu za lojalność (taki jak w Highscores). "
                "Ceny broni to ceny u NPC i w Store."
            ),
            wordWrap=True,
        )
        info.setObjectName("muted")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addLayout(_top_bar(tr("← Narzędzia"), self.back_requested))
        layout.addWidget(title)
        layout.addLayout(form)
        layout.addWidget(self._expert)
        layout.addWidget(self._double)
        layout.addWidget(self._result)
        layout.addWidget(info)
        layout.addStretch(1)
        self._update()

    def _update(self) -> None:
        skill = self._skill.currentData()
        current = self._current.value()
        # Poza magic levelem skille zaczynają się od 10, więc niższy poziom nie ma sensu.
        if skill != "magic" and current < 10:
            self._result.setText(tr("Ten skill zaczyna się od 10."))
            return
        if self._target.value() <= current:
            self._result.setText(tr("Cel musi być wyższy niż obecny poziom."))
            return
        plan = skill_plan(
            skill, self._vocation.currentData(), current, self._percent.value(), self._target.value(),
            self._expert.isChecked(), self._double.isChecked(),
        )
        hours, rest = divmod(plan.seconds, 3600)
        lines = [
            tr("Ładunki: <b>{n}</b> (bicie w dummy: {h} h {m} min)", n=format_gold(plan.charges), h=hours,
               m=rest // 60),
            "",
        ]
        for item in plan.weapons:
            lines.append(
                tr("{count}× {name}: {gold} gp albo {coins} TC", count=format_gold(item.count), name=item.weapon.name,
                   gold=format_gold(item.gold), coins=format_gold(item.coins))
            )
        self._result.setText("<br>".join(lines))
