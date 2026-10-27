"""Status streamu na Kick: odpowiedź API -> nadaje / offline / nie wiadomo. Bez sieci."""

import json
import urllib.error

from tibiahelper.core import stream


def answer(data):
    return lambda url: json.dumps(data).encode()


def test_live_when_livestream_present():
    assert stream.is_live(answer({"slug": "jackyykick", "livestream": {"is_live": True}})) is True


def test_offline_when_livestream_null():
    assert stream.is_live(answer({"slug": "jackyykick", "livestream": None})) is False


def test_unknown_on_network_error():
    def fail(url):
        raise urllib.error.URLError("brak sieci")

    assert stream.is_live(fail) is None


def test_unknown_on_blocked_or_changed_answer():
    # Np. Cloudflare odda stronę HTML albo Kick zmieni format.
    assert stream.is_live(lambda url: b"<html>Just a moment...</html>") is None
    assert stream.is_live(answer({"slug": "jackyykick"})) is None
    assert stream.is_live(answer([1, 2])) is None


def test_only_https_kick_addresses():
    assert stream.API_URL.startswith("https://kick.com/")
    assert stream.CHANNEL_URL.startswith("https://kick.com/")
