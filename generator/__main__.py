"""Generator danych questów (narzędzie autora, nie trafia do .exe).

Uruchamiaj z katalogu głównego repo:
    python -m generator fetch "The Annihilator Quest" [--refresh]
    python -m generator add-draft "The Annihilator Quest" [--id annihilator-quest]
    python -m generator review annihilator-quest
    python -m generator check-updates
"""

import argparse
import sys
from pathlib import Path

# Generator korzysta z modelu danych aplikacji (app/tibiahelper), żeby szkice
# przechodziły dokładnie tę samą walidację co w aplikacji.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from . import quests, quests_file  # noqa: E402
from .wiki_api import WikiClient  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m generator")
    commands = parser.add_subparsers(dest="command", required=True)

    fetch = commands.add_parser("fetch", help="pobierz stronę questa i spoiler do generator/raw/")
    fetch.add_argument("title", help='tytuł strony na TibiaWiki, np. "Katana Quest"')
    fetch.add_argument("--refresh", action="store_true", help="pobierz ponownie mimo cache")

    add = commands.add_parser("add-draft", help="dodaj quest jako draft do data/quests.json")
    add.add_argument("title")
    add.add_argument("--id", help="własne id questa (domyślnie z nazwy)")

    review = commands.add_parser("review", help="oznacz quest jako przejrzany")
    review.add_argument("quest_id")

    commands.add_parser("check-updates", help="sprawdź, które questy zmieniły się na wiki")

    args = parser.parse_args(argv)
    client = WikiClient()

    try:
        if args.command == "fetch":
            pages = quests.fetch(client, args.title, refresh=args.refresh)
            spoiler = pages.spoiler.revid if pages.spoiler else "brak"
            print(f"{pages.main.title}: rewizja {pages.main.revid}, spoiler: {spoiler}")

        elif args.command == "add-draft":
            data = quests_file.load()
            draft = quests.add_draft(data, quests.fetch(client, args.title), args.id)
            quests_file.save(data)
            print(f"Dodano draft {draft['id']!r}. Uzupełnij kroki, potem: review {draft['id']}")

        elif args.command == "review":
            data = quests_file.load()
            quest = quests_file.find(data, args.quest_id)
            if quest is None:
                raise LookupError(f"Nie ma questa o id {args.quest_id!r}")
            pages = quests.fetch(client, quests.title_from_url(quest["source_url"]))
            quests.review(data, args.quest_id, pages)
            quests_file.save(data)
            print(f"{args.quest_id}: reviewed (rewizja wiki {pages.revision})")

        elif args.command == "check-updates":
            data = quests_file.load()
            changes = quests.check_updates(data, client)
            for change in changes:
                print(
                    f"{change.quest_id} [{change.status}]: "
                    f"{change.known_revision} -> {change.latest_revision}"
                )
            if any(c.status == "reviewed" for c in changes):
                quests_file.save(data)
                print("Przejrzane questy ze zmianami oznaczono jako needs_review.")
            print(f"Zmienionych questów: {len(changes)}")

    except (LookupError, ValueError, RuntimeError, OSError) as exc:
        print(f"Błąd: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
