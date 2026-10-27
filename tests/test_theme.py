"""Testy motywów kolorystycznych: czy każdy motyw jest kompletny i czytelny."""

import os
import re

import pytest

from tibiahelper.core.settings import DEFAULT_THEME
from tibiahelper.ui import theme

HEX = re.compile(r"^#[0-9a-f]{6}$")
COLOR_FIELDS = ("background", "surface", "surface_hover", "border", "text", "muted", "accent", "on_accent", "warning", "good", "bad")


def _luminance(color: str) -> float:
    # Wzór z WCAG: jasność koloru odczuwana przez oko.
    channels = [int(color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    r, g, b = (c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_default_theme_exists():
    assert DEFAULT_THEME in theme.THEMES


@pytest.mark.parametrize("key", theme.THEMES)
def test_colors_are_hex(key):
    t = theme.THEMES[key]
    for field in COLOR_FIELDS:
        assert HEX.match(getattr(t, field)), f"{key}.{field}"


@pytest.mark.parametrize("key", theme.THEMES)
def test_text_is_readable(key):
    # 4.5 to próg WCAG dla zwykłego tekstu, 3 dla mniej ważnego (szare podpisy).
    t = theme.THEMES[key]
    assert contrast(t.text, t.background) >= 4.5
    assert contrast(t.text, t.surface) >= 4.5
    assert contrast(t.muted, t.background) >= 3
    assert contrast(t.on_accent, t.accent) >= 4.5


@pytest.mark.parametrize("key", theme.THEMES)
def test_style_uses_theme_colors(key):
    t = theme.THEMES[key]
    style = theme.build_style(t)
    assert t.accent in style and t.background in style
    # Nawiasy klamrowe z f-stringa muszą się zamienić na zwykłe, inaczej Qt odrzuci style sheet.
    assert "{{" not in style


def test_unknown_theme_falls_back_to_default():
    assert theme.theme_key("różowy") == DEFAULT_THEME
    assert theme.theme_key("wood") == "wood"


def test_apply_theme_switches_module_colors():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app, "light")
    assert theme.ACCENT == theme.THEMES["light"].accent
    theme.apply_theme(app, "nie-ma-takiego")
    assert theme.ACCENT == theme.THEMES[DEFAULT_THEME].accent


@pytest.mark.parametrize("key", theme.THEMES)
def test_element_colors_are_visible(key):
    t = theme.THEMES[key]
    assert contrast(t.good, t.surface) >= 3
    assert contrast(t.bad, t.surface) >= 3
