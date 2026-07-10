from pathlib import Path

from mouse_config_gui import macro_library
from mouse_config_gui.models import MacroAction


def test_load_library_returns_empty_dict_when_file_missing(tmp_path):
    assert macro_library.load_library(tmp_path / "does_not_exist.yaml") == {}


def test_save_then_load_round_trips(tmp_path):
    path = tmp_path / "macro_library.yaml"
    entries = {
        "Discord PTT": [
            MacroAction(kind="down", value="Ctrl_l"),
            MacroAction(kind="down", value="a"),
            MacroAction(kind="up", value="a"),
            MacroAction(kind="up", value="Ctrl_l"),
        ],
        "Empty Macro": [],
    }

    macro_library.save_library(entries, path)
    reloaded = macro_library.load_library(path)

    assert reloaded == entries


def test_save_library_creates_parent_directories(tmp_path):
    path = tmp_path / "nested" / "dir" / "macro_library.yaml"
    macro_library.save_library({"Foo": [MacroAction(kind="delay", value="5")]}, path)

    assert path.exists()
    assert macro_library.load_library(path) == {"Foo": [MacroAction(kind="delay", value="5")]}


def test_library_path_honors_xdg_config_home(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert macro_library.library_path() == tmp_path / "mouse-config-gui" / "macro_library.yaml"


def test_library_path_falls_back_to_home_config(monkeypatch, tmp_path):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert macro_library.library_path() == tmp_path / ".config" / "mouse-config-gui" / "macro_library.yaml"


def test_load_slot_names_returns_empty_dict_when_file_missing(tmp_path):
    assert macro_library.load_slot_names(tmp_path / "does_not_exist.yaml") == {}


def test_save_then_load_slot_names_round_trips(tmp_path):
    path = tmp_path / "macro_slot_names.yaml"
    names = {1: "Discord PTT", 7: "Copy/Paste Combo"}

    macro_library.save_slot_names(names, path)
    reloaded = macro_library.load_slot_names(path)

    assert reloaded == names
    # Keys must come back as int (slot numbers), not str -- YAML round-trips
    # dict keys as strings unless explicitly converted back.
    assert all(isinstance(slot, int) for slot in reloaded)


def test_slot_names_path_lives_alongside_library_path(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert macro_library.slot_names_path() == tmp_path / "mouse-config-gui" / "macro_slot_names.yaml"
