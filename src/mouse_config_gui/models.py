"""In-memory data model for a mouse config (design doc §4, §6)."""

from dataclasses import dataclass, field


@dataclass
class DpiSlot:
    enabled: bool = True
    value: str = ""  # actual decimal or 0xHHHH bytecode, per capability descriptor


@dataclass
class ProfileConfig:
    lightmode: str | None = None
    color: str | None = None  # 6-hex RRGGBB, no leading '#'
    brightness: int | None = None
    speed: int | None = None
    scrollspeed: int | None = None
    report_rate: int | None = None
    dpi_slots: list[DpiSlot] = field(default_factory=list)
    active_dpi_slot: int | None = None  # read-only runtime state, not written back
    # Button/scroll mappings (button_*, scroll_up, scroll_down), keyed by their
    # INI key. Validated against keymap.py's grammar by the button editor.
    buttons: dict[str, str] = field(default_factory=dict)


@dataclass
class MacroAction:
    kind: str   # "down" | "up" | "delay" | "move_left" | "move_right" | "move_up" | "move_down"
    value: str  # key/mouse-button name for down/up; decimal string for delay/move


@dataclass
class MouseConfig:
    model: str | None = None
    active_profile: int | None = None  # read-only runtime state, not written back
    profiles: list[ProfileConfig] = field(default_factory=list)
    # 15 shared macro slots (1-15), each an ordered action list. Validated
    # against keymap.py's is_valid_macro_action() by the macro editor.
    macros: dict[int, list[MacroAction]] = field(default_factory=dict)
