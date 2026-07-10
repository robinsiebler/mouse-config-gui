"""Local macro library and slot names: app-side macro metadata that has no
home in the mouse's own data, independent of whichever config .ini is
currently loaded or read from the device.

- The library is a named collection of saved macro action lists, letting a
  macro be stashed and swapped into any of the 15 on-device slots as needed.
- Slot names remember what you called macro N, keyed purely by slot number.
  This exists because mouse_m908 -R always returns fresh device state with
  no name data (there's nowhere on the mouse to store one) -- without a
  local record independent of that, a name set via ini_io.py's `# Macro N
  name: ...` comment would only survive as long as you keep working from
  the same saved .ini file, and would vanish the moment the app's automatic
  read-on-launch (or any "Read from Mouse" click) pulls fresh state.

Both save to disk immediately on every change, the way a browser saves
bookmarks -- neither is part of MouseConfig/ini_io.py's round-trip or the
app's dirty-tracking/Apply-to-mouse flow.

Pure Python, no `gi` import, mirroring ini_io.py's/capability.py's/
keymap.py's discipline so it stays unit-testable without a display.
"""

import os
from pathlib import Path

import yaml

from mouse_config_gui.models import MacroAction


def _config_dir() -> Path:
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg_config_home) if xdg_config_home else Path.home() / ".config"
    return base / "mouse-config-gui"


def library_path() -> Path:
    return _config_dir() / "macro_library.yaml"


def slot_names_path() -> Path:
    return _config_dir() / "macro_slot_names.yaml"


def load_library(path: Path | None = None) -> dict[str, list[MacroAction]]:
    path = path if path is not None else library_path()
    if not path.exists():
        return {}

    data = yaml.safe_load(path.read_text()) or {}
    return {
        name: [MacroAction(kind=action["kind"], value=action["value"]) for action in actions]
        for name, actions in data.items()
    }


def save_library(entries: dict[str, list[MacroAction]], path: Path | None = None) -> None:
    path = path if path is not None else library_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        name: [{"kind": action.kind, "value": action.value} for action in actions]
        for name, actions in entries.items()
    }
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))


def load_slot_names(path: Path | None = None) -> dict[int, str]:
    path = path if path is not None else slot_names_path()
    if not path.exists():
        return {}

    data = yaml.safe_load(path.read_text()) or {}
    return {int(slot): name for slot, name in data.items()}


def save_slot_names(names: dict[int, str], path: Path | None = None) -> None:
    path = path if path is not None else slot_names_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump({str(slot): name for slot, name in names.items()}, sort_keys=True))
