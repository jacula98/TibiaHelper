"""Logika komend generatora, oddzielona od CLI, żeby dało się ją testować."""

import re
import urllib.parse
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from tibiahelper.core.models import WIKI_URL_PREFIX

from . import cache, spoiler
from .wiki_api import WikiClient, WikiPage
from .terminology import apply_terms
from .wikitext import parse_infobox

SPOILER_SUFFIX = "/Spoiler"
TODO_MARK = "TODO"


@dataclass(frozen=True)
class QuestPages:
    """Strona questa (infobox: level, premium, nagrody) i jego /Spoiler (kroki)."""

    main: WikiPage
    spoiler: WikiPage | None

    @property
    def revision(self) -> int:
        # Numery rewizji w MediaWiki rosną globalnie, więc największy z obu stron
        # mówi, kiedy ostatnio zmieniło się cokolwiek, z czego korzystamy.
        return max(self.main.revid, self.spoiler.revid if self.spoiler else 0)


def fetch(
    client: WikiClient, title: str, refresh: bool = False, raw_dir: Path = cache.RAW_DIR
) -> QuestPages:
    """Strona questa i spoiler: z cache albo z wiki (refresh=True wymusza pobranie)."""
    titles = [title, title + SPOILER_SUFFIX]
    cached = {t: cache.load(t, raw_dir) for t in titles}
    if refresh or cached[title] is None:
        fetched = client.get_pages(titles)
        if fetched[title] is None:
            raise LookupError(f"Na TibiaWiki nie ma strony {title!r}")
        for requested, page in fetched.items():
            if page is not None:
                cache.save(requested, page, raw_dir)
        cached = fetched
    return QuestPages(main=cached[title], spoiler=cached[title + SPOILER_SUFFIX])


def slugify(name: str) -> str:
    name = re.sub(r"^the\s+", "", name.strip(), flags=re.IGNORECASE)
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def source_url(title: str) -> str:
    return WIKI_URL_PREFIX + urllib.parse.quote(title.replace(" ", "_"), safe="/():,'")


def title_from_url(url: str) -> str:
    return urllib.parse.unquote(url.removeprefix(WIKI_URL_PREFIX)).replace("_", " ")


def make_draft(pages: QuestPages, quest_id: str | None = None) -> dict:
    """Szkic questa z danych infoboxu. Kroki uzupełnia autor razem z Claude."""
    info = {key: apply_terms(value) for key, value in parse_infobox(pages.main.wikitext).items()}
    name = info.get("name") or pages.main.title
    level = re.match(r"\d+", info.get("lvl", ""))
    steps = [{"text": f"{TODO_MARK}: uproszczone kroki na podstawie strony /Spoiler"}]
    required: list[str] = []
    if pages.spoiler is not None:
        # Materiał z wiki do przerobienia przez autora (po angielsku, pierwszy krok z TODO).
        steps, required = spoiler.draft_content(pages.spoiler.wikitext, name)
    return {
        "id": quest_id or slugify(name),
        "name": name,
        "min_level": int(level.group()) if level else 0,
        "premium": info.get("premium", "").lower() == "yes",
        "source_url": source_url(pages.main.title),
        "wiki_revision": pages.revision,
        "status": "draft",
        "reviewed_at": None,
        "steps": steps,
        "required_items": required,
        "rewards": [info["reward"]] if info.get("reward") else [],
    }


def add_draft(data: dict, pages: QuestPages, quest_id: str | None = None) -> dict:
    draft = make_draft(pages, quest_id)
    if any(q.get("id") == draft["id"] for q in data["quests"]):
        raise ValueError(f"Quest o id {draft['id']!r} już jest w pliku")
    data["quests"].append(draft)
    return draft


def review(data: dict, quest_id: str, pages: QuestPages, now: datetime | None = None) -> dict:
    """Oznacza quest jako przejrzany względem rewizji z cache."""
    quest = next((q for q in data["quests"] if q.get("id") == quest_id), None)
    if quest is None:
        raise LookupError(f"Nie ma questa o id {quest_id!r}")
    if any(TODO_MARK in step.get("text", "") for step in quest["steps"]):
        raise ValueError("Quest ma jeszcze kroki z TODO; uzupełnij je przed przeglądem")
    quest["status"] = "reviewed"
    quest["reviewed_at"] = (now or datetime.now(UTC)).isoformat(timespec="seconds")
    # Zapisujemy rewizję, którą autor faktycznie widział w cache.
    quest["wiki_revision"] = pages.revision
    quest["needs_review"] = False
    return quest


@dataclass(frozen=True)
class Change:
    quest_id: str
    status: str
    known_revision: int | None
    latest_revision: int
    newly_flagged: bool = False


def check_updates(data: dict, client: WikiClient) -> list[Change]:
    """Porównuje revision id z wiki. Przejrzane questy dostają needs_review=True."""
    titles = {q["id"]: title_from_url(q["source_url"]) for q in data["quests"]}
    all_titles = [t for title in titles.values() for t in (title, title + SPOILER_SUFFIX)]
    latest = client.latest_revisions(all_titles)

    changes = []
    for quest in data["quests"]:
        title = titles[quest["id"]]
        revision = max(latest.get(title) or 0, latest.get(title + SPOILER_SUFFIX) or 0)
        known = quest.get("wiki_revision")
        if revision and (known is None or revision > known):
            # Nowe oznaczenie tylko raz: kolejne uruchomienia dalej raportują zmianę,
            # ale nie zapisują pliku i nie podbijają data_version bez potrzeby.
            newly = quest["status"] == "reviewed" and not quest.get("needs_review")
            if newly:
                quest["needs_review"] = True
            changes.append(Change(quest["id"], quest["status"], known, revision, newly))
    return changes
