"""Testy ustawień okna (bez Qt)."""

from tibiahelper.core.settings import MIN_OPACITY, Settings, load_settings, save_settings


def test_missing_file_gives_defaults(tmp_path):
    assert load_settings(tmp_path / "settings.json") == Settings()


def test_round_trip(tmp_path):
    path = tmp_path / "TibiaHelper" / "settings.json"
    save_settings(path, Settings(opacity=0.75, geometry="AdnQywAD"))
    assert load_settings(path) == Settings(opacity=0.75, geometry="AdnQywAD")


def test_opacity_is_clamped(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"opacity": 0.01}', encoding="utf-8")
    assert load_settings(path).opacity == MIN_OPACITY


def test_broken_file_gives_defaults(tmp_path):
    path = tmp_path / "settings.json"
    for text in ("{urwany", "[]", '{"opacity": "dużo"}'):
        path.write_text(text, encoding="utf-8")
        assert load_settings(path) == Settings()


def test_wrong_geometry_type_is_ignored(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"opacity": 0.5, "geometry": 123}', encoding="utf-8")
    assert load_settings(path) == Settings(opacity=0.5, geometry=None)


def test_language_round_trip(tmp_path):
    path = tmp_path / "settings.json"
    save_settings(path, Settings(language="de"))
    assert load_settings(path).language == "de"


def test_unknown_language_gives_polish(tmp_path):
    path = tmp_path / "settings.json"
    for value in ('"klingon"', "[1]", "null"):
        path.write_text(f'{{"opacity": 0.5, "language": {value}}}', encoding="utf-8")
        settings = load_settings(path)
        # Zły język nie kasuje reszty ustawień.
        assert settings.language == "pl" and settings.opacity == 0.5
