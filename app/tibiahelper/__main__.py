"""Start aplikacji: python -m tibiahelper (z katalogu app/)."""

import argparse
import logging
import sys
import threading

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QMessageBox

from .core.paths import (
    bundled_data_file,
    bundled_spawns_file,
    cached_data_file,
    cached_spawns_file,
    progress_file,
    settings_file,
)
from .core.progress import ProgressStore
from .core.repository import LoadResult, QuestFileError, load_quest_file
from .core.spawns import load_spawns
from .core.updater import Update, apply_update, check_for_update, load_best_local
from .ui.main_window import MainWindow
from .ui.theme import apply_theme


class _UpdateNotifier(QObject):
    """Przenosi wynik sprawdzania z wątku w tle do wątku okna.

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
    # Dla autora: edytor questów, zapis do data/quests.json w repo (tylko uruchamianie ze źródeł).
    parser.add_argument("--author", action="store_true", help="tryb autora: edycja questów")
    args = parser.parse_args()
    if args.author:
        # Autor pracuje na pliku z repo i widzi szkice, a kopia z GitHuba by mu go podmieniła.
        args.show_drafts = args.no_update = True

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    app = QApplication(sys.argv)
    apply_theme(app)

    def visible(result: LoadResult) -> list:
        return result.quests if args.show_drafts else result.visible_quests

    author_file = None
    if args.author:
        if getattr(sys, "frozen", False):
            # W .exe plik danych jest w katalogu tymczasowym i ginie po zamknięciu.
            QMessageBox.warning(None, "TibiaHelper", "Tryb autora działa tylko przy uruchomieniu ze źródeł.")
            return 1
        author_file = bundled_data_file()
    window = MainWindow(ProgressStore(progress_file()), settings_file(), author_file)
    result = None
    error = None
    try:
        if args.no_update:
            result = load_quest_file(bundled_data_file())
        else:
            result = load_best_local(bundled_data_file(), cached_data_file())
        window.set_quests(visible(result), result.data_version, result.monsters, result.item_images)
    except QuestFileError as exc:
        # Bez danych okno i tak się otwiera; użytkownik widzi komunikat zamiast awarii.
        logging.error("%s", exc)
        error = str(exc)
        window.set_quests([], 0)

    # --no-update: tylko pliki z repo (autor sprawdza swoje zmiany).
    spawns_paths = [bundled_spawns_file()] if args.no_update else [bundled_spawns_file(), cached_spawns_file()]
    spawns = load_spawns(*spawns_paths)
    window.set_spawns(spawns)

    window.show()
    if error:
        QMessageBox.warning(window, "TibiaHelper", f"Nie udało się wczytać questów.\n\n{error}")

    if not args.no_update:
        notifier = _UpdateNotifier()

        def install(update: Update) -> None:
            # Wywoływane dopiero po kliknięciu „Zaktualizuj”.
            if not apply_update(update, cached_data_file(), cached_spawns_file()):
                QMessageBox.warning(window, "TibiaHelper", "Nie udało się zapisać nowych poradników.")
            # Nawet gdy zapis się nie udał, pokazujemy nowe dane do końca tej sesji.
            window.set_quests(
                visible(update.result), update.data_version, update.result.monsters, update.result.item_images
            )
            if update.spawns_raw is not None:
                window.set_spawns(load_spawns(bundled_spawns_file(), cached_spawns_file()))

        notifier.updated.connect(
            lambda update: window.offer_update(update.data_version, lambda: install(update))
        )
        current = result.data_version if result else 0
        # Pobieranie w tle, żeby okno nie zamarzło przy wolnym internecie.
        # daemon=True: zamknięcie okna nie czeka na koniec pobierania.
        threading.Thread(
            target=lambda: _run_update(notifier, current, spawns.version), daemon=True, name="update"
        ).start()

    return app.exec()


def _run_update(notifier: _UpdateNotifier, current_version: int, spawns_version: int) -> None:
    update = check_for_update(current_version, spawns_version=spawns_version)
    if update is not None:
        notifier.updated.emit(update)


if __name__ == "__main__":
    sys.exit(main())
