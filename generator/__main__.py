"""Generator danych questów (narzędzie autora, nie trafia do .exe).

Uruchamiaj z katalogu głównego repo:
    python -m generator fetch "The Annihilator Quest" [--refresh]
    python -m generator add-draft "The Annihilator Quest" [--id annihilator-quest]
    python -m generator review annihilator-quest
    python -m generator check-updates
    python -m generator coords "Tom"            # współrzędne NPC/miejsca do pinezek na mapie
    python -m generator monster "Skeleton"      # dodaj/odśwież potwora (HP, exp, obrazek)
    python -m generator import-all               # wszystkie potwory + brakujące questy (szkice)
    python -m generator spawns                   # miejsca występowania potworów z TibiaRoute
"""

import argparse
import json
import sys
from pathlib import Path

# Generator korzysta z modelu danych aplikacji (app/tibiahelper), żeby szkice
# przechodziły dokładnie tę samą walidację co w aplikacji.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from . import bulk, cache, monsters, quests, quests_file, spawns  # noqa: E402
from tibiahelper.core import author  # noqa: E402
from .wiki_api import WikiClient  # noqa: E402
from .wikitext import infobox_position, mapper_coords  # noqa: E402


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

    coords = commands.add_parser("coords", help="pokaż współrzędne ze strony (NPC, miejsca, questa)")
    coords.add_argument("title")
    coords.add_argument("--refresh", action="store_true")

    monster = commands.add_parser("monster", help="dodaj albo odśwież potwora w data/quests.json")
    monster.add_argument("title", help='tytuł strony potwora na TibiaWiki, np. "Skeleton"')
    monster.add_argument("--id", help="własne id (domyślnie z nazwy, np. poison-spider)")
    monster.add_argument("--refresh", action="store_true", help="pobierz stronę ponownie mimo cache")

    import_all = commands.add_parser("import-all", help="pobierz wszystkie potwory i questy z TibiaWiki")
    import_all.add_argument("--refresh", action="store_true", help="pobierz strony ponownie mimo cache")

    commands.add_parser("spawns", help="pobierz miejsca występowania potworów z TibiaRoute")

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
            if any(c.newly_flagged for c in changes):
                quests_file.save(data)
                print("Przejrzane questy ze zmianami oznaczono jako needs_review.")
            print(f"Zmienionych questów: {len(changes)}")

        elif args.command == "coords":
            print_coords(client, args.title, args.refresh)

        elif args.command == "monster":
            data = quests_file.load()
            entry = monsters.fetch_monster(client, args.title, args.id, args.refresh)
            author.upsert_monster(data, entry)
            quests_file.save(data)
            print(f"{entry['id']}: {entry['name']}, HP {entry['hp']}, exp {entry['exp']}, {entry['elements']}")

        elif args.command == "import-all":
            data = quests_file.load()
            count, skipped = bulk.import_monsters(data, client, args.refresh)
            added, refreshed = bulk.import_quests(data, client, args.refresh)
            quests_file.save(data)
            for line in skipped:
                print(f"Pominięto {line}")
            print(f"Potwory: {count}, nowe questy (szkice): {added}, odświeżone szkice: {refreshed}")

        elif args.command == "spawns":
            quest_data = quests_file.load()
            data, unmatched = spawns.build(spawns.download(), quest_data.get("monsters", []))
            spawns.save(data)
            # Aplikacja szuka aktualizacji po data_version w quests.json, więc podbijamy ją też tutaj.
            quests_file.save(quest_data)
            total = sum(len(points) for points in data["monsters"].values())
            print(f"Potwory z miejscami: {len(data['monsters'])}, punktów: {total}")
            if unmatched:
                print("Bez pary w data/quests.json:", ", ".join(unmatched))

    except (LookupError, ValueError, RuntimeError, OSError) as exc:
        print(f"Błąd: {exc}", file=sys.stderr)
        return 1
    return 0


def print_coords(client: WikiClient, title: str, refresh: bool) -> None:
    """Wypisuje gotowe do wklejenia punkty "markers" (label i kind autor poprawia ręcznie)."""
    pages = [title, title + quests.SPOILER_SUFFIX]
    cached = {t: cache.load(t) for t in pages}
    if refresh or cached[title] is None:
        cached = client.get_pages(pages)
        for requested, page in cached.items():
            if page is not None:
                cache.save(requested, page)
    if cached[title] is None:
        raise LookupError(f"Na TibiaWiki nie ma strony {title!r}")

    position = infobox_position(cached[title].wikitext)
    if position:
        print(f"Infobox ({title}):")
        print(json.dumps({**position, "label": title, "kind": "npc"}, ensure_ascii=False))
    for requested, page in cached.items():
        for found in mapper_coords(page.wikitext) if page else []:
            print(f"\n{requested}: …{found.pop('context')[-80:]}")
            print(json.dumps({**found, "label": "TODO", "kind": "place"}, ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
