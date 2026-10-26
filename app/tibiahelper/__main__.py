"""Start aplikacji: python -m tibiahelper (z katalogu app/)."""

import argparse
import logging
import sys
import threading

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QMessageBox

from .core.paths import bundled_data_file, cached_data_file, progress_file, settings_file
from .core.progress import ProgressStore
from .core.repository import LoadResult, QuestFileError, load_quest_file
from .core.updater import load_best_local, update_from_github
from .ui.main_window import MainWindow


class _UpdateNotifier(QObject):
    """Przenosi wynik pobierania z wątku w tle do wątku okna.

    Okna Qt wolno zmieniać tylko z głównego wątku. Sygnał wysłany z innego
    wątku Qt sam dostarcza w głównym wątku (połączenie kolejkowane).
    """

    updated = Signal(object)


def main() -> int:
    parser = argparse.ArgumentParser(prog="tibiahelper")
    # Dla autora: podgląd szkiców przed zmianą statusu na "reviewed".
    parser.add_argument("--show-drafts", action="store_true", help="pokaż też questy 'draft'")
    # Dla autora: testowanie zmian w data/quests.json bez kopii z GitHuba.
    parser.add_argument(
        "--no-update", action="store_true", help="używaj tylko wbudowanego quests.json"
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    app = QApplication(sys.argv)

    def visible(result: LoadResult) -> list:
        return result.quests if args.show_drafts else result.visible_quests

    window = MainWindow(ProgressStore(progress_file()), settings_file())
    result = None
    error = None
    try:
        if args.no_update:
            result = load_quest_file(bundled_data_file())
        else:
            result = load_best_local(bundled_data_file(), cached_data_file())
        window.set_quests(visible(result), result.data_version)
    except QuestFileError as exc:
        # Bez danych okno i tak się otwiera; użytkownik widzi komunikat zamiast awarii.
        logging.error("%s", exc)
        error = str(exc)
        window.set_quests([], 0)

    window.show()
    if error:
        QMessageBox.warning(window, "TibiaHelper", f"Nie udało się wczytać questów.\n\n{error}")

    if not args.no_update:
        notifier = _UpdateNotifier()
        notifier.updated.connect(
            lambda new: window.set_quests(visible(new), new.data_version, "zaktualizowano")
        )
        current = result.data_version if result else 0
        # Pobieranie w tle, żeby okno nie zamarzło przy wolnym internecie.
        # daemon=True: zamknięcie okna nie czeka na koniec pobierania.
        threading.Thread(
            target=lambda: _run_update(notifier, current), daemon=True, name="update"
        ).start()

    return app.exec()


def _run_update(notifier: _UpdateNotifier, current_version: int) -> None:
    new = update_from_github(current_version, cached_data_file())
    if new is not None:
        notifier.updated.emit(new)


if __name__ == "__main__":
    sys.exit(main())
