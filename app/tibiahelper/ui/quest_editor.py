"""Edytor questa (tryb autora): python -m tibiahelper --author.

Edytujemy kopię questa jako zwykły słownik (taki jak w quests.json).
Dopiero „Zapisz” sprawdza całość (core/author.py) i zapisuje plik, więc
nieudana edycja niczego nie psuje.
"""

import copy
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..core import author
from ..core.models import MapPoint
from .map_window import KIND_NAMES, MapWindow

# Gdy krok nie ma jeszcze pinezki, mapa startuje w Thais (parter).
DEFAULT_START = MapPoint(x=32369, y=32241, z=7, label="Thais")


class QuestEditor(QWidget):
    # Wysyłany po udanym zapisie pliku: główne okno wczytuje dane od nowa.
    saved = Signal(str)  # id questa

    def __init__(self, quest: dict, data_file: Path, maps_dir: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle(f"Edycja: {quest['name']}")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.resize(480, 720)

        # deepcopy: zmiany w edytorze nie dotykają danych, które pokazuje aplikacja.
        self._quest = copy.deepcopy(quest)
        self._steps: list[dict] = self._quest["steps"]
        self._data_file = data_file
        self._maps_dir = maps_dir
        self._map: MapWindow | None = None
        self._current = -1  # indeks edytowanego kroku
        # Krok i fragment tekstu, dla których otwarto wybieranie miejsca na mapie.
        self._pending_step: int | None = None
        self._pending_anchor: str | None = None

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.addLayout(self._build_quest_form())
        layout.addWidget(_section("KROKI"))
        layout.addLayout(self._build_step_list())
        layout.addWidget(self._build_step_form())

        scroll = QScrollArea(widgetResizable=True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(content)

        outer = QVBoxLayout(self)
        outer.addWidget(scroll, 1)
        outer.addLayout(self._build_buttons())

        self._refresh_step_list()
        self._steps_list.setCurrentRow(0)

    # --- budowa okna ------------------------------------------------------------

    def _build_quest_form(self) -> QFormLayout:
        quest = self._quest
        self._name = QLineEdit(quest["name"])
        self._level = QSpinBox(minimum=0, maximum=5000, value=quest["min_level"])
        self._premium = QCheckBox("premium")
        self._premium.setChecked(quest["premium"])
        self._status = QLabel()
        self._status.setObjectName("muted")
        self._update_status_label()
        # Jedna rzecz w linii: łatwiej edytować niż listę po przecinkach.
        self._required = QPlainTextEdit("\n".join(quest.get("required_items", [])))
        self._required.setFixedHeight(70)
        self._rewards = QPlainTextEdit("\n".join(quest.get("rewards", [])))
        self._rewards.setFixedHeight(70)

        form = QFormLayout()
        form.addRow("Nazwa", self._name)
        level_row = QHBoxLayout()
        level_row.addWidget(self._level)
        level_row.addWidget(self._premium)
        form.addRow("Min. level", level_row)
        form.addRow("Status", self._status)
        form.addRow("Potrzebne\n(1 w linii)", self._required)
        form.addRow("Nagrody\n(1 w linii)", self._rewards)
        return form

    def _build_step_list(self) -> QVBoxLayout:
        self._steps_list = QListWidget()
        self._steps_list.setFixedHeight(150)
        # Długie kroki skracamy „…”, zamiast przewijać listę w bok.
        self._steps_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self._steps_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._steps_list.currentRowChanged.connect(self._select_step)

        buttons = QHBoxLayout()
        for text, tip, slot in (
            ("+ Dodaj", "Nowy krok pod zaznaczonym", self._add_step),
            ("− Usuń", "Usuń zaznaczony krok", self._remove_step),
            ("↑", "Przesuń wyżej", lambda: self._move_step(-1)),
            ("↓", "Przesuń niżej", lambda: self._move_step(+1)),
        ):
            button = QPushButton(text)
            button.setToolTip(tip)
            button.clicked.connect(slot)
            buttons.addWidget(button)

        layout = QVBoxLayout()
        layout.addWidget(self._steps_list)
        layout.addLayout(buttons)
        return layout

    def _build_step_form(self) -> QWidget:
        self._text = QPlainTextEdit()
        self._text.setFixedHeight(110)
        self._location = QLineEdit()
        self._npc = QLineEdit()
        self._items = QLineEdit(placeholderText="np. Shovel, Rope")

        self._markers = QListWidget()
        self._markers.setFixedHeight(80)
        add_pin = QPushButton("📍 Dodaj pinezkę")
        add_pin.setToolTip("Zaznacz w tekście kroku słowa, za którymi ma stać pinezka, potem kliknij")
        add_pin.clicked.connect(self._add_marker)
        remove_pin = QPushButton("Usuń pinezkę")
        remove_pin.clicked.connect(self._remove_marker)
        pin_buttons = QHBoxLayout()
        pin_buttons.addWidget(add_pin)
        pin_buttons.addWidget(remove_pin)

        hint = QLabel("Wskazówka: zaznacz fragment tekstu (np. „między Venore a Thais”), "
                      "a potem „Dodaj pinezkę” i kliknij miejsce na mapie.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)

        box = QWidget()
        form = QFormLayout(box)
        form.setContentsMargins(0, 8, 0, 0)
        form.addRow("Tekst kroku", self._text)
        form.addRow("Miejsce", self._location)
        form.addRow("NPC", self._npc)
        form.addRow("Przedmioty", self._items)
        form.addRow("Pinezki", self._markers)
        form.addRow("", pin_buttons)
        form.addRow("", hint)
        return box

    def _build_buttons(self) -> QHBoxLayout:
        review = QPushButton("✓ Oznacz jako przejrzany")
        review.setToolTip("Quest stanie się widoczny dla graczy (po zapisie)")
        review.clicked.connect(self._mark_reviewed)
        cancel = QPushButton("Zamknij")
        cancel.clicked.connect(self.close)
        save = QPushButton("Zapisz")
        save.setObjectName("primary")
        save.clicked.connect(self._save)

        buttons = QHBoxLayout()
        buttons.addWidget(review)
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        return buttons

    # --- kroki ------------------------------------------------------------------

    def _refresh_step_list(self) -> None:
        self._steps_list.blockSignals(True)
        row = self._steps_list.currentRow()
        self._steps_list.clear()
        for number, step in enumerate(self._steps, start=1):
            first_line = step.get("text", "").splitlines()[0] if step.get("text") else "(pusty krok)"
            pins = " 📍" * len(step.get("markers", []))
            self._steps_list.addItem(f"{number}. {first_line[:60]}{pins}")
        self._steps_list.setCurrentRow(min(row, len(self._steps) - 1))
        self._steps_list.blockSignals(False)

    def _select_step(self, row: int) -> None:
        self._store_step()
        self._current = row
        if row < 0:
            return
        step = self._steps[row]
        self._text.setPlainText(step.get("text", ""))
        self._location.setText(step.get("location") or "")
        self._npc.setText(step.get("npc") or "")
        self._items.setText(", ".join(step.get("items", [])))
        self._refresh_markers()

    def _store_step(self) -> None:
        """Przepisuje pola formularza do słownika edytowanego kroku."""
        if not 0 <= self._current < len(self._steps):
            return
        step = self._steps[self._current]
        step["text"] = self._text.toPlainText().strip()
        for key, widget in (("location", self._location), ("npc", self._npc)):
            value = widget.text().strip()
            # Puste pola usuwamy, żeby JSON nie miał zbędnych "location": "".
            if value:
                step[key] = value
            else:
                step.pop(key, None)
        items = [i.strip() for i in self._items.text().split(",") if i.strip()]
        if items:
            step["items"] = items
        else:
            step.pop("items", None)
        self._refresh_step_list()

    def _add_step(self) -> None:
        self._store_step()
        self._cancel_pick()
        index = self._current + 1
        self._steps.insert(index, {"text": "Nowy krok"})
        self._current = -1  # nowy krok nie nadpisuje formularza poprzedniego
        self._refresh_step_list()
        self._steps_list.setCurrentRow(index)
        self._text.setFocus()
        self._text.selectAll()

    def _remove_step(self) -> None:
        if len(self._steps) <= 1:
            QMessageBox.information(self, "Edytor", "Quest musi mieć przynajmniej jeden krok.")
            return
        index = self._current
        if index < 0:
            return
        self._cancel_pick()
        del self._steps[index]
        self._current = -1  # usunięty krok nie ma już czego zapisywać
        self._refresh_step_list()
        self._steps_list.setCurrentRow(min(index, len(self._steps) - 1))
        self._select_step(self._steps_list.currentRow())

    def _move_step(self, delta: int) -> None:
        self._store_step()
        self._cancel_pick()
        index, target = self._current, self._current + delta
        if index < 0 or not 0 <= target < len(self._steps):
            return
        self._steps[index], self._steps[target] = self._steps[target], self._steps[index]
        self._current = target
        self._refresh_step_list()
        self._steps_list.blockSignals(True)
        self._steps_list.setCurrentRow(target)
        self._steps_list.blockSignals(False)

    # --- pinezki ----------------------------------------------------------------

    def _refresh_markers(self) -> None:
        self._markers.clear()
        if self._current < 0:
            return
        text = self._text.toPlainText()
        for marker in self._steps[self._current].get("markers", []):
            anchor = marker.get("anchor")
            where = f" · po „{anchor}”" if anchor else " · na końcu tekstu"
            # Ostrzeżenie, gdy po edycji tekstu fragment z anchor zniknął.
            warning = " ⚠ brak tego fragmentu w tekście" if anchor and anchor not in text else ""
            self._markers.addItem(
                f"{marker['label']} ({KIND_NAMES[marker.get('kind', 'place')]}){where}{warning}"
            )

    def _add_marker(self) -> None:
        if self._current < 0:
            return
        self._pending_step = self._current
        self._pending_anchor = self._text.textCursor().selectedText().strip() or None
        step = self._steps[self._current]
        existing = [MapPoint.model_validate(m) for m in step.get("markers", [])]
        start = existing[-1] if existing else self._nearest_marker()
        if self._map is None:
            self._map = MapWindow(self._maps_dir, self)
            self._map.point_picked.connect(self._on_point_picked)
        self._map.pick_point(existing, start)

    def _nearest_marker(self) -> MapPoint:
        """Ostatnia pinezka z wcześniejszych kroków: następne miejsce jest zwykle niedaleko."""
        for step in reversed(self._steps[: self._current]):
            if step.get("markers"):
                return MapPoint.model_validate(step["markers"][-1])
        return DEFAULT_START

    def _cancel_pick(self) -> None:
        """Po dodaniu, usunięciu lub przesunięciu kroków numer kroku z wybierania jest nieaktualny."""
        self._pending_step = None
        if self._map is not None:
            self._map.close()

    def _on_point_picked(self, x: int, y: int, z: int) -> None:
        if self._pending_step is None:
            return
        if self._pending_step != self._current:
            # Autor przełączył krok w trakcie: pinezka trafia do kroku, z którego ją dodawał.
            self._steps_list.setCurrentRow(self._pending_step)
        dialog = _MarkerDialog(self._pending_anchor or self._location.text().strip(), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._store_step()
        marker = {"x": x, "y": y, "z": z, "label": dialog.label(), "kind": dialog.kind()}
        if self._pending_anchor:
            marker["anchor"] = self._pending_anchor
        self._steps[self._current].setdefault("markers", []).append(marker)
        self._cancel_pick()
        self._refresh_step_list()
        self._refresh_markers()

    def _remove_marker(self) -> None:
        row = self._markers.currentRow()
        markers = self._steps[self._current].get("markers", []) if self._current >= 0 else []
        if 0 <= row < len(markers):
            del markers[row]
            if not markers:
                del self._steps[self._current]["markers"]
            self._refresh_step_list()
            self._refresh_markers()

    # --- zapis ------------------------------------------------------------------

    def _collect(self) -> dict:
        self._store_step()
        quest = self._quest
        quest["name"] = self._name.text().strip()
        quest["min_level"] = self._level.value()
        quest["premium"] = self._premium.isChecked()
        quest["required_items"] = _lines(self._required)
        quest["rewards"] = _lines(self._rewards)
        return quest

    def _update_status_label(self) -> None:
        status = self._quest["status"]
        self._status.setText("przejrzany (widoczny dla graczy)" if status == "reviewed" else "szkic (draft)")

    def _mark_reviewed(self) -> None:
        try:
            self._quest = author.mark_reviewed(self._collect())
        except author.AuthorError as exc:
            QMessageBox.warning(self, "Edytor", str(exc))
            return
        self._steps = self._quest["steps"]
        self._update_status_label()
        QMessageBox.information(self, "Edytor", "Oznaczono jako przejrzany. Kliknij „Zapisz”, żeby zapisać.")

    def _save(self) -> None:
        quest = self._collect()
        try:
            data = author.load_data(self._data_file)
            author.replace_quest(data, quest)
            author.save_data(data, self._data_file)
        except author.AuthorError as exc:
            QMessageBox.warning(self, "Nie zapisano", str(exc))
            return
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Nie zapisano", f"Błąd pliku {self._data_file}:\n{exc}")
            return
        self.saved.emit(quest["id"])
        QMessageBox.information(
            self,
            "Zapisano",
            f"Zapisano w {self._data_file.name} (wersja danych {data['data_version']}).\n"
            "Żeby opublikować zmiany, wyślij ten plik Claude w czacie projektu.",
        )


class _MarkerDialog(QDialog):
    """Nazwa i rodzaj nowej pinezki."""

    def __init__(self, suggested_label: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle("Nowa pinezka")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self._label = QLineEdit(suggested_label)
        self._kind = QComboBox()
        for kind, name in KIND_NAMES.items():
            self._kind.addItem(name, kind)
        self._kind.setCurrentIndex(self._kind.findData("place"))

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        form = QFormLayout(self)
        form.addRow("Podpis na mapie", self._label)
        form.addRow("Rodzaj", self._kind)
        form.addRow(buttons)

    def _accept(self) -> None:
        if self._label.text().strip():
            self.accept()

    def label(self) -> str:
        return self._label.text().strip()

    def kind(self) -> str:
        return self._kind.currentData()


def _section(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("sectionTitle")
    return label


def _lines(edit: QPlainTextEdit) -> list[str]:
    return [line.strip() for line in edit.toPlainText().splitlines() if line.strip()]
