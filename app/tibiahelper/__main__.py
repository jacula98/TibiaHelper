"""Start aplikacji: python -m tibiahelper (z katalogu app/)."""

import argparse
import logging
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from .core.paths import bundled_data_file, progress_file
from .core.progress import ProgressStore
from .core.repository import QuestFileError, load_quest_file
from .ui.main_window import MainWindow


def main() -> int:
    parser = argparse.ArgumentParser(prog="tibiahelper")
    # Dla autora: podgląd szkiców przed zmianą statusu na "reviewed".
    parser.add_argument("--show-drafts", action="store_true", help="pokaż też questy 'draft'")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    app = QApplication(sys.argv)

    quests = []
    error = None
    try:
        result = load_quest_file(bundled_data_file())
        quests = result.quests if args.show_drafts else result.visible_quests
    except QuestFileError as exc:
        # Bez danych okno i tak się otwiera; użytkownik widzi komunikat zamiast awarii.
        logging.error("%s", exc)
        error = str(exc)

    window = MainWindow(quests, ProgressStore(progress_file()))
    window.show()
    if error:
        QMessageBox.warning(window, "TibiaHelper", f"Nie udało się wczytać questów.\n\n{error}")
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
