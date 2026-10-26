"""Cache surowego wikitekstu w generator/raw/ (folder jest w .gitignore).

Dzięki cache nie pobieramy tej samej strony przy każdym uruchomieniu,
a autor może spokojnie pisać kroki, mając pod ręką tekst z wiki.
"""

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from .wiki_api import WikiPage

RAW_DIR = Path(__file__).resolve().parent / "raw"


def cache_path(title: str, raw_dir: Path = RAW_DIR) -> Path:
    # "The Annihilator Quest/Spoiler" -> "The_Annihilator_Quest__Spoiler.json"
    name = title.replace("/", "__").replace(" ", "_")
    name = re.sub(r"[^A-Za-z0-9_.\-]", "", name)
    return raw_dir / f"{name}.json"


def load(title: str, raw_dir: Path = RAW_DIR) -> WikiPage | None:
    path = cache_path(title, raw_dir)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return WikiPage(data["title"], data["revid"], data["wikitext"])


def save(requested_title: str, page: WikiPage, raw_dir: Path = RAW_DIR) -> Path:
    path = cache_path(requested_title, raw_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "title": page.title,
        "revid": page.revid,
        "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "wikitext": page.wikitext,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
