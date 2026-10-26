"""Testy generatora. Wiki jest zastąpiona sztucznym transportem: zero zapytań do sieci."""

from datetime import UTC, datetime

import pytest

import json
from pathlib import Path

from generator import quests
from generator.terminology import apply_terms, find_forbidden
from generator.wiki_api import WikiClient, WikiPage
from generator.wikitext import parse_infobox, strip_markup
from tibiahelper.core.models import Quest

INFOBOX = """{{Infobox Quest|List={{{1|}}}|GetValue={{{GetValue|}}}
| name           = The Annihilator Quest
| reward         = [[Demon Outfits]] and one of: [[Magic Sword]], [[Monk (Creature)|Monk]]
| location       = [[Edron]] {{Mapper Coords|1|2|text=here}}
| lvl            = 100
| premium        = yes
}}
Tekst pod infoboxem."""


class FakeWiki:
    """Udaje API: zwraca strony ze słownika i zapisuje wysłane zapytania."""

    def __init__(self, pages: dict[str, tuple[int, str]], redirects: dict[str, str] | None = None):
        self.pages = pages
        self.redirects = redirects or {}
        self.requests: list[dict] = []

    def __call__(self, params: dict[str, str]) -> dict:
        self.requests.append(params)
        titles = params["titles"].split("|")
        redirects = [{"from": t, "to": self.redirects[t]} for t in titles if t in self.redirects]
        result = []
        for title in titles:
            final = self.redirects.get(title, title)
            if final not in self.pages:
                result.append({"title": final, "missing": True})
                continue
            revid, text = self.pages[final]
            revision = {"revid": revid}
            if "content" in params["rvprop"]:
                revision["slots"] = {"main": {"content": text}}
            result.append({"title": final, "revisions": [revision]})
        return {"query": {"redirects": redirects, "pages": result}}


def client(fake: FakeWiki) -> WikiClient:
    return WikiClient(transport=fake, delay=0)


# --- wikitekst ----------------------------------------------------------------


def test_strip_markup():
    assert strip_markup("[[Edron]] [[Hero Cave|jaskinia]] '''ważne''' {{Szablon|x}}") == (
        "Edron jaskinia ważne"
    )


def test_parse_infobox():
    info = parse_infobox(INFOBOX)
    assert info["name"] == "The Annihilator Quest"
    assert info["lvl"] == "100"
    assert info["premium"] == "yes"
    assert info["reward"] == "Demon Outfits and one of: Magic Sword, Monk"
    assert info["location"] == "Edron"


# --- klient API ---------------------------------------------------------------


def test_get_pages_follows_redirects_and_reports_missing():
    fake = FakeWiki({"The Annihilator Quest": (10, INFOBOX)}, {"Annihilator Quest": "The Annihilator Quest"})
    pages = client(fake).get_pages(["Annihilator Quest", "Nie Ma"])
    assert pages["Annihilator Quest"] == WikiPage("The Annihilator Quest", 10, INFOBOX)
    assert pages["Nie Ma"] is None
    assert fake.requests[0]["redirects"] == "1"


def test_requests_are_batched_by_50():
    fake = FakeWiki({f"Q{i}": (i, "") for i in range(120)})
    revisions = client(fake).latest_revisions([f"Q{i}" for i in range(120)])
    assert len(fake.requests) == 3
    assert revisions["Q119"] == 119
    assert fake.requests[0]["rvprop"] == "ids"  # bez treści stron


def test_api_error_raises():
    with pytest.raises(RuntimeError, match="maxlag"):
        WikiClient(transport=lambda p: {"error": {"code": "maxlag"}}, delay=0).get_pages(["X"])


# --- fetch + cache ------------------------------------------------------------


def test_fetch_uses_cache_after_first_download(tmp_path):
    fake = FakeWiki({"Q": (5, INFOBOX), "Q/Spoiler": (7, "kroki")})
    first = quests.fetch(client(fake), "Q", raw_dir=tmp_path)
    second = quests.fetch(client(fake), "Q", raw_dir=tmp_path)
    assert first == second
    assert first.revision == 7  # większa z rewizji strony i spoilera
    assert len(fake.requests) == 1


def test_fetch_refresh_downloads_again(tmp_path):
    fake = FakeWiki({"Q": (5, INFOBOX)})
    quests.fetch(client(fake), "Q", raw_dir=tmp_path)
    fake.pages["Q"] = (9, INFOBOX)
    pages = quests.fetch(client(fake), "Q", refresh=True, raw_dir=tmp_path)
    assert pages.revision == 9
    assert pages.spoiler is None


def test_fetch_missing_page_raises(tmp_path):
    with pytest.raises(LookupError):
        quests.fetch(client(FakeWiki({})), "Nie Ma", raw_dir=tmp_path)


# --- szkic, przegląd, zmiany na wiki ------------------------------------------


def pages(main_rev=5, spoiler_rev=7) -> quests.QuestPages:
    return quests.QuestPages(
        main=WikiPage("The Annihilator Quest", main_rev, INFOBOX),
        spoiler=WikiPage("The Annihilator Quest/Spoiler", spoiler_rev, "kroki"),
    )


def test_make_draft_is_valid_quest():
    draft = quests.make_draft(pages())
    quest = Quest.model_validate(draft)
    assert quest.id == "annihilator-quest"
    assert quest.min_level == 100
    assert quest.premium
    assert quest.source_url == "https://tibia.fandom.com/wiki/The_Annihilator_Quest"
    assert quest.wiki_revision == 7
    assert quest.status == "draft"


def test_add_draft_rejects_duplicate_id():
    data = {"quests": []}
    quests.add_draft(data, pages())
    with pytest.raises(ValueError):
        quests.add_draft(data, pages())


def test_review_refuses_todo_steps():
    data = {"quests": [quests.make_draft(pages())]}
    with pytest.raises(ValueError, match="TODO"):
        quests.review(data, "annihilator-quest", pages())


def test_review_marks_quest_reviewed():
    draft = quests.make_draft(pages())
    draft["steps"] = [{"text": "Zbierz drużynę 4 graczy."}]
    draft["needs_review"] = True
    data = {"quests": [draft]}
    now = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)

    quest = quests.review(data, "annihilator-quest", pages(spoiler_rev=8), now=now)

    assert Quest.model_validate(quest).is_visible
    assert quest["wiki_revision"] == 8
    assert quest["reviewed_at"] == "2026-10-26T12:00:00+00:00"
    assert quest["needs_review"] is False


def test_check_updates_flags_only_changed_reviewed_quests():
    reviewed = quests.make_draft(pages())
    reviewed.update(status="reviewed", reviewed_at="2026-10-01T00:00:00+00:00")
    unchanged = dict(reviewed, id="unchanged", source_url=quests.source_url("Katana Quest"))
    unchanged["wiki_revision"] = 50
    data = {"quests": [reviewed, unchanged]}
    fake = FakeWiki({"The Annihilator Quest": (5, ""), "The Annihilator Quest/Spoiler": (20, ""), "Katana Quest": (50, "")})

    changes = quests.check_updates(data, client(fake))

    assert [(c.quest_id, c.known_revision, c.latest_revision) for c in changes] == [
        ("annihilator-quest", 7, 20)
    ]
    assert reviewed["needs_review"] is True
    assert changes[0].newly_flagged
    assert "needs_review" not in unchanged

    # Drugie uruchomienie: zmiana dalej widoczna, ale już nie "nowa", więc bez zapisu.
    again = quests.check_updates(data, client(fake))
    assert [c.newly_flagged for c in again] == [False]


def test_title_and_url_round_trip():
    title = "The Desert Dungeon Quest"
    assert quests.title_from_url(quests.source_url(title)) == title


# --- nazewnictwo --------------------------------------------------------------


def test_apply_terms_replaces_gate_of_expertise():
    assert apply_terms("Enter the gate of expertise (lvl 20)") == "Enter the bramka lvl-owa (lvl 20)"
    assert apply_terms("Two Gates of Expertise") == "Two bramki lvl-owe"


def test_find_forbidden_reports_matched_text():
    assert find_forbidden("przez Gate of Expertise") == ["Gate of Expertise"]


def test_make_draft_applies_terms():
    page = WikiPage("Q", 1, "{{Infobox Quest\n| reward = Access to [[Gate of Expertise]]\n}}")
    draft = quests.make_draft(quests.QuestPages(main=page, spoiler=None))
    assert draft["rewards"] == ["Access to bramka lvl-owa"]


def test_repo_data_uses_polish_terms():
    """Reguła autora: w danych aplikacji nie ma angielskiej nazwy "Gate of Expertise"."""
    data_file = Path(__file__).parents[1] / "data" / "quests.json"
    text = json.dumps(json.loads(data_file.read_text(encoding="utf-8")), ensure_ascii=False)
    assert find_forbidden(text) == []


# --- współrzędne do mapy -------------------------------------------------------


def test_wiki_coord():
    from generator.wikitext import wiki_coord

    assert wiki_coord("125.151") == 32151
    assert wiki_coord("127") == 127 * 256


def test_mapper_coords_and_infobox_position():
    from generator.wikitext import infobox_position, mapper_coords

    text = "Open the [[Loose Stone Pile]] ({{Mapper Coords|127.137|125.93|7|4|text=here}})"
    assert mapper_coords(text) == [
        {"x": 32649, "y": 32093, "z": 7, "context": "Open the Loose Stone Pile ("}
    ]
    npc = "{{Infobox NPC\n| name = Tom\n| posx = 125.85\n| posy = 125.199\n| posz = 7\n}}"
    assert infobox_position(npc) == {"x": 32085, "y": 32199, "z": 7}
    assert infobox_position("{{Infobox NPC\n| name = X\n}}") is None


def test_spoiler_draft_content():
    from generator import spoiler

    wikitext = (
        "== Required Equipment ==\n"
        "* [[Honeycomb]] ''(more than one)''\n"
        "== Mission 1 ==\n"
        "Go to {{Mapper Coords|125.252|121.75|7|3|text=Sven}} and say {{KW|mead}}.\n"
        "{{Infobox Hint\n|text=ignored\n}}\n"
        "Drink [[Mead|the mead]].\n"
    )
    steps, required = spoiler.draft_content(wikitext, "Barbarian Test Quest")
    assert steps[0]["text"] == spoiler.TODO_STEP
    assert required == ["Honeycomb (more than one)"]
    assert steps[1]["text"] == "[Mission 1] Go to Sven and say mead."
    assert steps[1]["markers"][0]["x"] == 125 * 256 + 252
    assert steps[1]["markers"][0]["z"] == 7
    assert steps[2]["text"] == "Drink the mead."
    assert "ignored" not in str(steps)
