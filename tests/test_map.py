"""Testy punktów na mapie, pinezek w tekście i pobierania map pięter (bez sieci)."""

import pytest
from pydantic import ValidationError

from tibiahelper.core import mapdata
from tibiahelper.core.models import Step
from tibiahelper.ui.rich_text import parse_pin_link, step_html

PNG = mapdata.PNG_SIGNATURE + b"reszta pliku"
POINT = {"x": 32649, "y": 32093, "z": 7, "label": "Stos kamieni"}


# --- model ------------------------------------------------------------------


def test_marker_defaults():
    step = Step.model_validate({"text": "Idź tam.", "markers": [POINT]})
    assert step.markers[0].kind == "place"
    assert step.markers[0].anchor is None


@pytest.mark.parametrize(
    "change",
    [
        {"x": 1},  # poza mapą Tibii
        {"z": 16},  # są tylko piętra 0-15
        {"kind": "boss"},
        {"anchor": "nie ma tego w tekście"},
    ],
)
def test_invalid_marker_rejected(change):
    with pytest.raises(ValidationError):
        Step.model_validate({"text": "Idź tam.", "markers": [{**POINT, **change}]})


# --- pinezki w tekście -------------------------------------------------------


def test_pin_goes_after_anchor():
    step = Step.model_validate(
        {"text": "Idź między Venore a Thais. Kop.", "markers": [{**POINT, "anchor": "Venore a Thais"}]}
    )
    html = step_html(2, step, "<img>")
    assert html == '2. Idź między Venore a Thais&nbsp;<a href="pin:0" title="Stos kamieni"><img></a>. Kop.'


def test_pin_without_anchor_goes_at_end_and_text_is_escaped():
    step = Step.model_validate(
        {"text": "<b>nie HTML</b>", "markers": [{**POINT, "label": 'a"b'}]}
    )
    html = step_html(1, step, "<img>")
    assert html.startswith("1. &lt;b&gt;nie HTML&lt;/b&gt;&nbsp;<a ")
    assert 'title="a&quot;b"' in html


def test_parse_pin_link():
    assert parse_pin_link("pin:3") == 3
    assert parse_pin_link("pin:x") is None
    assert parse_pin_link("https://example.com") is None


# --- mapy pięter ---------------------------------------------------------------


def test_to_pixel_and_floor_label():
    assert mapdata.to_pixel(31744, 30976) == (0, 0)
    assert mapdata.floor_label(7) == "parter"
    assert mapdata.floor_label(6) == "+1"
    assert mapdata.floor_label(9) == "-2"


def test_ensure_floor_downloads_once(tmp_path):
    calls = []

    def fetch(url):
        calls.append(url)
        return PNG

    path = mapdata.ensure_floor(tmp_path, 7, fetch=fetch)
    assert path.read_bytes() == PNG
    mapdata.ensure_floor(tmp_path, 7, fetch=fetch)
    assert len(calls) == 1  # drugi raz z dysku


def test_ensure_floor_falls_back_to_second_url(tmp_path):
    def fetch(url):
        if "github.io" in url:
            raise OSError("zablokowane")
        return PNG

    assert mapdata.ensure_floor(tmp_path, 8, fetch=fetch).exists()


def test_ensure_floor_rejects_non_png(tmp_path):
    with pytest.raises(ValueError):
        mapdata.ensure_floor(tmp_path, 7, fetch=lambda url: b"<html>404</html>")
    assert not mapdata.floor_path(tmp_path, 7).exists()


def test_ensure_floor_rejects_bad_floor(tmp_path):
    with pytest.raises(ValueError):
        mapdata.ensure_floor(tmp_path, 16, fetch=lambda url: PNG)
