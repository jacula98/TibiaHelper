"""Testy wgrywania UI i hotkeyów (Quality of life) do clientoptions.json."""

import json

import pytest

from tibiahelper.core import client_options
from tibiahelper.core.paths import bundled_qol_dir

BUNDLED = bundled_qol_dir() / client_options.FILE_NAME


def test_bundled_file_has_no_personal_or_machine_settings():
    data = json.loads(BUNDLED.read_text(encoding="utf-8"))
    assert set(data) == {"clientOptionsVersion", "hotkeyOptions", "options", *client_options.REPLACED_SECTIONS}
    options = data["options"]
    assert not [key for key in options if key.startswith(("sound", "characterSelection"))]
    for key in ("loginEmailAddress", "sessionRemainLoggedIn", "rememberLoginEmail", "frameRateLimit", "rendererIndex"):
        assert key not in options
    assert "Basic" in data["hotkeyOptions"]["hotkeySets"]


def test_install_merges_and_backs_up_once(tmp_path):
    source = tmp_path / "ours.json"
    source.write_text(json.dumps({
        "clientOptionsVersion": 9,
        "options": {"gameWindowShowTextualEffects": False},
        "hotkeyOptions": {"currentHotkeySetName": "Basic", "hotkeySets": {"Basic": {"chatOff": [1]}}},
        "controlButtonsOptions": {"enabledButtons": ["skillsWidget"]},
    }))
    target = tmp_path / "conf" / client_options.FILE_NAME
    target.parent.mkdir()
    target.write_text(json.dumps({
        "clientOptionsVersion": 9,
        "clientWindowOptions": {"clientWindowWidth": 1920},
        "options": {"gameWindowShowTextualEffects": True, "soundMasterVolume": 40},
        "hotkeyOptions": {"currentHotkeySetName": "Mine", "hotkeySets": {"Basic": {"chatOff": [0]}, "Mine": {"chatOff": [2]}}},
    }))

    assert client_options.install(target, source) is True
    result = json.loads(target.read_text())
    assert result["clientWindowOptions"] == {"clientWindowWidth": 1920}
    assert result["options"] == {"gameWindowShowTextualEffects": False, "soundMasterVolume": 40}
    assert result["hotkeyOptions"]["currentHotkeySetName"] == "Basic"
    assert result["hotkeyOptions"]["hotkeySets"] == {"Basic": {"chatOff": [1]}, "Mine": {"chatOff": [2]}}
    assert result["controlButtonsOptions"] == {"enabledButtons": ["skillsWidget"]}

    assert client_options.install(target, source) is False
    backup = json.loads(target.with_name(target.name + client_options.BACKUP_SUFFIX).read_text())
    assert backup["hotkeyOptions"]["currentHotkeySetName"] == "Mine"


def test_install_without_existing_file_and_with_broken_file(tmp_path):
    target = tmp_path / "conf" / client_options.FILE_NAME
    assert client_options.install(target, BUNDLED) is False
    assert "Basic" in json.loads(target.read_text())["hotkeyOptions"]["hotkeySets"]

    target.write_text("[1, 2]")
    with pytest.raises(TypeError):
        client_options.install(target, BUNDLED)
