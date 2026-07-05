"""Button-mapping grammar validator (design_docs/keymap.md, design doc §10).

Grammar data lives in keymap_data.yaml rather than being parsed from
keymap.md's prose at runtime: keymap.md isn't shipped as package data, and
parsing markdown list sections out of an arbitrary doc path has the same
installed-package fragility capability.py's docstring already flags for
filesystem-relative paths -- see _capabilities_dir() for the fix that was
applied there. keymap_data.yaml is loaded the same way.

Matching is case-sensitive, verified directly against mouse_m908's C++
source (include/rd_mouse.cpp's _i_encode_button_mapping, include/data.cpp's
_c_keycodes/_c_keyboard_key_values maps): all literal tokens and modifiers
are lowercase, but named keyboard keys are PascalCase (e.g. "Delete", not
"delete"). Getting the case wrong doesn't error out there -- std::map's
operator[] silently default-constructs a 0x00 byte for a miss -- so a
case-insensitive validator would pass through mappings that the real tool
silently mangles. Fire's repeats/delay are a plain uint8_t cast with no
range check in that source (not the "1-255" keymap.md documents), so 0-255
is accepted for both; confirmed against a real M908's own -R output
reporting "fire:mouse_left:3:0" for its stock Fire-button mapping.
"""

from importlib import resources
import re

import yaml

_HEX_RE = re.compile(r"^0x[0-9a-fA-F]{8}$")
_FIRE_RE = re.compile(r"^fire:([^:]+):(\d+):(\d+)$")
_SNIPE_RE = re.compile(r"^snipe:(\d+)$")
_MACRO_RE = re.compile(r"^macro(\d+)(?::(\d+|while|until))?$")


def _load_data() -> dict:
    text = (resources.files("mouse_config_gui") / "keymap_data.yaml").read_text()
    return yaml.safe_load(text)


_DATA = _load_data()
_MODIFIERS = set(_DATA["modifiers"])
_KEYS = set(_DATA["keys"])
_MOUSE_AND_SPECIAL = set(_DATA["mouse_and_special"])
_MEDIA = set(_DATA["media"])
_COMPATIBILITY = set(_DATA["compatibility"])
_FIRE_BUTTONS = set(_DATA["fire_buttons"])
_LITERAL_TOKENS = _MOUSE_AND_SPECIAL | _MEDIA | _COMPATIBILITY

# 200-1100 in steps of 100 (rd_mouse.cpp's _c_snipe_dpi_values map keys).
SNIPE_DPI_VALUES = list(range(200, 1101, 100))


def grammar_data() -> dict:
    """Expose keymap_data.yaml's raw token lists (modifiers, keys,
    mouse_and_special, media, compatibility, fire_buttons) so UI pickers can
    offer the same vocabulary this validator accepts, without copying it."""
    return _DATA


def _is_valid_fire(value: str) -> bool:
    match = _FIRE_RE.match(value)
    if not match:
        return False
    button, repeats, delay = match.groups()
    if button not in _FIRE_BUTTONS and button not in _KEYS:
        return False
    return 0 <= int(repeats) <= 255 and 0 <= int(delay) <= 255


def _is_valid_snipe(value: str) -> bool:
    match = _SNIPE_RE.match(value)
    if not match:
        return False
    dpi = int(match.group(1))
    return 200 <= dpi <= 1100 and dpi % 100 == 0


def _is_valid_macro(value: str, num_macro_slots: int) -> bool:
    match = _MACRO_RE.match(value)
    if not match:
        return False
    num, suffix = match.groups()
    if not (1 <= int(num) <= num_macro_slots):
        return False
    if suffix is None or suffix in ("while", "until"):
        return True
    return 1 <= int(suffix) <= 255


def _is_valid_combo(value: str) -> bool:
    parts = value.split("+")
    if not parts or any(p == "" for p in parts):
        return False
    *modifiers, key = parts
    return all(m in _MODIFIERS for m in modifiers) and key in _KEYS


def is_valid_button_mapping(value: str, num_macro_slots: int = 15) -> bool:
    """Validate a button mapping string against keymap.md's grammar.

    Empty string is valid -- it means "omit this line," leaving the mouse's
    existing mapping for that button untouched (mirrors DpiRow's empty-value
    semantics in dpi_group.py).
    """
    value = value.strip()
    if not value:
        return True

    if value in _LITERAL_TOKENS:
        return True
    if _HEX_RE.match(value):
        return True
    if value.startswith("fire:"):
        return _is_valid_fire(value)
    if value.startswith("snipe:"):
        return _is_valid_snipe(value)
    if value.startswith("macro"):
        return _is_valid_macro(value, num_macro_slots)
    return _is_valid_combo(value)


# Macro action grammar (design doc §10), verified against mouse_m908's
# actual macro encode/decode (include/rd_mouse.cpp's _i_encode_macro/
# _i_decode_macro): down/up accept a keyboard key (the same `keys` list
# above -- includes capitalized modifier-as-key entries like "Ctrl_l", so
# e.g. holding Ctrl across a key press is `down Ctrl_l` / `down a` / `up a`
# / `up Ctrl_l`, no combo syntax needed here) or one of 5 mouse buttons --
# notably including forward/backward, which fire:'s button set does not.
# delay is in 10ms units, 1-255; move_* is a pixel-ish distance, 1-120.
# _i_encode_macro writes 3 bytes/action into a 256-byte buffer starting at
# offset 8 and stops once offset exceeds 212 -- simulated: 69 actions max
# (design doc §10 says 67; this is the source-verified correction).
MACRO_MOUSE_BUTTONS = ["mouse_left", "mouse_right", "mouse_middle", "mouse_forward", "mouse_backward"]
MACRO_ACTION_KINDS = ["down", "up", "delay", "move_left", "move_right", "move_up", "move_down"]
MAX_MACRO_ACTIONS = 69

_MACRO_MOUSE_BUTTONS = set(MACRO_MOUSE_BUTTONS)
_MOVE_KINDS = {"move_left", "move_right", "move_up", "move_down"}
# str.isdigit() disagrees with int(): "²".isdigit() is True but int("²")
# raises ValueError (superscripts/circled digits aren't decimal). \d matches
# Unicode's decimal-digit property, which is exactly what int() accepts --
# same reasoning as _FIRE_RE/_SNIPE_RE/_MACRO_RE's \d+ above.
_DIGITS_RE = re.compile(r"^\d+$")


def is_valid_macro_action(kind: str, value: str) -> bool:
    if kind in ("down", "up"):
        return value in _MACRO_MOUSE_BUTTONS or value in _KEYS
    if kind == "delay":
        return bool(_DIGITS_RE.match(value)) and 1 <= int(value) <= 255
    if kind in _MOVE_KINDS:
        return bool(_DIGITS_RE.match(value)) and 1 <= int(value) <= 120
    return False
