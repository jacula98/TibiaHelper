"""Pobieranie obrazków na listach (SpriteAnimator) bez sieci: fetch podmieniamy na funkcję testową."""

import os
import threading
import time
import urllib.error

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from tibiahelper.ui import monster_grid  # noqa: E402 (najpierw ustawiamy QT_QPA_PLATFORM)
from tibiahelper.ui.monster_grid import SpriteAnimator  # noqa: E402

URL = "https://static.wikia.nocookie.net/tibia/images/a/ab/X.gif"
GIF = b"GIF89a" + b"\0" * 10  # ensure_image sprawdza tylko pierwsze bajty


def wait_idle(animator: SpriteAnimator) -> None:
    deadline = time.monotonic() + 5
    while animator._workers and time.monotonic() < deadline:
        time.sleep(0.01)
    assert animator._workers == 0


def test_downloads_in_parallel(tmp_path):
    running, most = 0, 0
    lock = threading.Lock()

    def fetch(url):
        nonlocal running, most
        with lock:
            running += 1
            most = max(most, running)
        time.sleep(0.1)
        with lock:
            running -= 1
        return GIF

    animator = SpriteAnimator(tmp_path, fetch=fetch)
    for i in range(8):
        assert animator.frame(f"m{i}", URL) is None
    wait_idle(animator)
    assert all((tmp_path / f"m{i}.gif").exists() for i in range(8))
    assert most > 1


def test_worker_survives_unexpected_error(tmp_path):
    # Wcześniej taki błąd zabijał wątek i reszta kolejki czekała, aż użytkownik przewinie listę.
    def fetch(url):
        if "bad" in url:
            raise RuntimeError("zerwane połączenie")
        return GIF

    animator = SpriteAnimator(tmp_path, fetch=fetch)
    animator.frame("ok", URL)
    animator.frame("bad", URL + "bad")
    wait_idle(animator)
    assert (tmp_path / "ok.gif").exists()


def test_skips_images_scrolled_away(tmp_path):
    fetched = []
    animator = SpriteAnimator(tmp_path, fetch=lambda url: fetched.append(url) or GIF)
    animator.frame("gone", URL)
    animator._used["gone"] = time.monotonic() - 10  # dawno nierysowany (przewinięty)
    wait_idle(animator)
    assert not (tmp_path / "gone.gif").exists()
    # Gdy wróci na ekran, zlecamy go znowu.
    animator.frame("gone", URL)
    wait_idle(animator)
    assert (tmp_path / "gone.gif").exists()


@pytest.mark.parametrize(("error", "retried"), [(urllib.error.URLError("brak sieci"), True), (ValueError("nie GIF"), False)])
def test_retry_only_after_temporary_errors(tmp_path, monkeypatch, error, retried):
    monkeypatch.setattr(monster_grid, "RETRY_AFTER", 0.0)
    calls = []

    def fetch(url):
        calls.append(url)
        raise error

    animator = SpriteAnimator(tmp_path, fetch=fetch)
    animator.frame("x", URL)
    wait_idle(animator)
    animator.frame("x", URL)
    wait_idle(animator)
    assert len(calls) == (2 if retried else 1)
