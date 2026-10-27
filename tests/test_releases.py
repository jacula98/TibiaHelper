"""Testy powiadomienia o nowej wersji programu (Release na GitHubie)."""

import json
import urllib.error

from tibiahelper import __version__
from tibiahelper.core import releases


def _fetch(payload):
    def fetch(url: str) -> bytes:
        assert url == releases.LATEST_URL
        return json.dumps(payload).encode("utf-8")

    return fetch


def test_parse_version():
    assert releases.parse_version("v1.2.3") == (1, 2, 3)
    assert releases.parse_version("0.2") == (0, 2, 0)
    assert releases.parse_version("wersja 2") is None
    assert releases.parse_version(__version__) is not None


def test_newer_release_is_offered_with_safe_link():
    page = "https://github.com/jacula98/TibiaHelper/releases/tag/v0.3.0"
    release = releases.check_for_release("0.2.0", _fetch({"tag_name": "v0.3.0", "html_url": page}))
    assert release == releases.Release("0.3.0", page)

    # Link spoza Release tego repo podmieniamy na stronę Release.
    evil = releases.check_for_release("0.2.0", _fetch({"tag_name": "v0.3.0", "html_url": "https://evil.example/"}))
    assert evil.url == releases.RELEASES_PAGE + "latest"


def test_same_older_or_broken_release_is_ignored():
    assert releases.check_for_release("0.3.0", _fetch({"tag_name": "v0.3.0"})) is None
    assert releases.check_for_release("1.0.0", _fetch({"tag_name": "v0.9.9"})) is None
    assert releases.check_for_release("0.1.0", _fetch({"tag_name": "nightly"})) is None
    assert releases.check_for_release("0.1.0", _fetch({"message": "Not Found"})) is None

    def no_release(url: str) -> bytes:
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    assert releases.check_for_release("0.1.0", no_release) is None
