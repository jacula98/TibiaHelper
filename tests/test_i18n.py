"""Testy tłumaczeń: każdy tekst z tr("...") i N_("...") ma tłumaczenie w każdym języku."""

import ast
import json
import re
from pathlib import Path

import pytest

from tibiahelper.core import i18n
from tibiahelper.core.i18n import DEFAULT_LANGUAGE, LANGUAGES, N_, load_catalog, set_language, tr

APP_DIR = Path(i18n.__file__).resolve().parent.parent
FOREIGN = [code for code in LANGUAGES if code != DEFAULT_LANGUAGE]
PLACEHOLDER = re.compile(r"\{(\w*)\}")


def source_texts() -> set[str]:
    """Teksty z wywołań tr("...") i N_("...") w kodzie aplikacji (przez ast, a nie regex)."""
    texts = set()
    for path in APP_DIR.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in ("tr", "N_")
                and node.args
            ):
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    texts.add(first.value)
    return texts


@pytest.fixture(autouse=True)
def polish_after_test():
    # Język to stan całego programu: po teście wracamy do polskiego, żeby nie psuć innych testów.
    yield
    set_language(DEFAULT_LANGUAGE)


def test_source_has_texts():
    # Zabezpieczenie testu: gdyby ast nic nie znalazł, testy niżej przeszłyby „na pusto”.
    assert len(source_texts()) > 100


@pytest.mark.parametrize("language", FOREIGN)
def test_every_text_is_translated(language):
    catalog = load_catalog(language)
    missing = sorted(source_texts() - catalog.keys())
    assert not missing, f"{language}.json: brak tłumaczeń dla {missing}"


@pytest.mark.parametrize("language", FOREIGN)
def test_no_unused_translations(language):
    # Stare wpisy po zmianie tekstu w kodzie: lepiej je usunąć, niż tłumaczyć na próżno.
    raw = json.loads((i18n.TRANSLATIONS_DIR / f"{language}.json").read_text(encoding="utf-8"))
    unused = sorted(raw.keys() - source_texts())
    assert not unused, f"{language}.json: nieużywane wpisy {unused}"


@pytest.mark.parametrize("language", FOREIGN)
def test_placeholders_match(language):
    for text, translated in load_catalog(language).items():
        assert set(PLACEHOLDER.findall(translated)) == set(PLACEHOLDER.findall(text)), (language, text)


@pytest.mark.parametrize("language", FOREIGN)
def test_no_gate_of_expertise_in_polish_keys(language):
    # Reguła nazewnictwa dotyczy polskich tekstów (kluczy).
    for text in load_catalog(language):
        assert "Gate of Expertise" not in text


def test_tr_uses_selected_language():
    assert tr("Ustawienia") == "Ustawienia"
    set_language("en")
    assert tr("Ustawienia") == "Settings"
    assert tr("Wersja poradników: {n}", n=7) == "Guide version: 7"


def test_unknown_text_and_language_fall_back_to_polish():
    assert set_language("xx") == DEFAULT_LANGUAGE
    set_language("de")
    assert tr("tego tekstu nie ma w tłumaczeniach") == "tego tekstu nie ma w tłumaczeniach"


def test_broken_translation_falls_back_to_polish(tmp_path, monkeypatch):
    (tmp_path / "en.json").write_text('{"Wersja: {n}": "Version: {m}", "pusty": ""}', encoding="utf-8")
    monkeypatch.setattr(i18n, "TRANSLATIONS_DIR", tmp_path)
    set_language("en")
    assert tr("Wersja: {n}", n=2) == "Wersja: 2"
    assert tr("pusty") == "pusty"


def test_missing_or_broken_file_gives_empty_catalog(tmp_path):
    assert load_catalog("en", tmp_path) == {}
    (tmp_path / "en.json").write_text("[1, 2]", encoding="utf-8")
    assert load_catalog("en", tmp_path) == {}


def test_n_does_not_translate():
    set_language("en")
    assert N_("Ustawienia") == "Ustawienia"
