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
    # Unmodeled keys (button_*, macro comment blocks) preserved verbatim so v1
    # round-trips them unchanged even though it has no UI for them yet (§8).
    raw: dict[str, str] = field(default_factory=dict)


@dataclass
class MouseConfig:
    model: str | None = None
    active_profile: int | None = None  # read-only runtime state, not written back
    profiles: list[ProfileConfig] = field(default_factory=list)
    # 15 shared macro slots (1-15), each a list of raw ";# action\tvalue" lines,
    # preserved verbatim since v1 doesn't edit macros (§8, §10).
    macros: dict[int, list[str]] = field(default_factory=dict)
