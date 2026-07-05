"""Custom INI parser/writer for mouse_m908 config files (design doc §4.1, §8).

Not configparser: configparser drops comments, and this format's comments carry
real metadata (`# Model:`, `# Currently active profile:`) as well as data v1
doesn't model at all (macro comment blocks). Round-trip guarantee is about DATA,
not bytes: button_* lines and macro blocks come back out verbatim, but decorative
comments explaining field meaning/ranges are not preserved on save -- mouse_m908's
own -R output doesn't preserve them either (it always emits its own fixed set of
comments), so there's nothing canonical to round-trip there.
"""

import re
from pathlib import Path

from mouse_config_gui.models import DpiSlot, MouseConfig, ProfileConfig

NUM_PROFILES = 5

_SECTION_RE = re.compile(r"^\[profile(\d)\]$")
_MODEL_RE = re.compile(r"^#\s*Model:\s*(\S+)")
_ACTIVE_PROFILE_RE = re.compile(r"^#\s*Currently active profile:\s*(\d+)")
_ACTIVE_DPI_RE = re.compile(r"^#\s*Active dpi level(?: for this profile)?:\s*(\d+)")
_MACRO_HEADER_RE = re.compile(r"^;##\s*macro(\d+)$")
_DPI_ENABLE_RE = re.compile(r"^dpi([1-5])_enable$")
_DPI_VALUE_RE = re.compile(r"^dpi([1-5])$")

_INT_FIELDS = ("brightness", "speed", "report_rate")


def load(path: Path) -> MouseConfig:
    config = MouseConfig()
    profiles: dict[int, ProfileConfig] = {}
    dpi_enabled: dict[int, dict[int, bool]] = {}
    dpi_values: dict[int, dict[int, str]] = {}
    current_profile: int | None = None
    current_macro: int | None = None

    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if match := _MACRO_HEADER_RE.match(line):
            current_macro = int(match.group(1))
            config.macros[current_macro] = []
            current_profile = None
            continue
        if current_macro is not None and line.startswith(";#"):
            config.macros[current_macro].append(line)
            continue

        if line.startswith("#"):
            if match := _MODEL_RE.match(line):
                config.model = match.group(1)
            elif match := _ACTIVE_PROFILE_RE.match(line):
                config.active_profile = int(match.group(1))
            elif current_profile is not None and (match := _ACTIVE_DPI_RE.match(line)):
                profiles[current_profile].active_dpi_slot = int(match.group(1))
            continue

        if match := _SECTION_RE.match(line):
            current_profile = int(match.group(1))
            profiles[current_profile] = ProfileConfig()
            continue

        if current_profile is None or "=" not in line:
            continue

        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        profile = profiles[current_profile]

        if key == "lightmode":
            profile.lightmode = value
        elif key == "color":
            profile.color = value
        elif key == "scrollspeed":
            profile.scrollspeed = int(value, 16)
        elif key in _INT_FIELDS:
            setattr(profile, key, int(value))
        elif match := _DPI_ENABLE_RE.match(key):
            dpi_enabled.setdefault(current_profile, {})[int(match.group(1))] = value == "1"
        elif match := _DPI_VALUE_RE.match(key):
            dpi_values.setdefault(current_profile, {})[int(match.group(1))] = value
        else:
            profile.raw[key] = value

    for num in range(1, NUM_PROFILES + 1):
        profile = profiles.setdefault(num, ProfileConfig())
        enabled = dpi_enabled.get(num, {})
        values = dpi_values.get(num, {})
        if enabled or values:
            profile.dpi_slots = [
                DpiSlot(enabled=enabled.get(slot, True), value=values.get(slot, ""))
                for slot in range(1, 6)
            ]
        config.profiles.append(profile)

    return config


def save(config: MouseConfig, path: Path) -> None:
    lines: list[str] = []

    if config.model is not None:
        lines.append(f"# Model: {config.model}")
    if config.active_profile is not None:
        lines.append(f"# Currently active profile: {config.active_profile}")

    for num in range(1, NUM_PROFILES + 1):
        profile = (
            config.profiles[num - 1]
            if len(config.profiles) >= num
            else ProfileConfig()
        )
        lines.append("")
        lines.append(f"[profile{num}]")

        if profile.lightmode is not None:
            lines.append(f"lightmode={profile.lightmode}")
        if profile.color is not None:
            lines.append(f"color={profile.color}")
        if profile.brightness is not None:
            lines.append(f"brightness={profile.brightness}")
        if profile.speed is not None:
            lines.append(f"speed={profile.speed}")
        if profile.scrollspeed is not None:
            lines.append(f"scrollspeed={profile.scrollspeed:x}")
        if profile.report_rate is not None:
            lines.append(f"report_rate={profile.report_rate}")

        for slot_num, slot in enumerate(profile.dpi_slots, start=1):
            lines.append(f"dpi{slot_num}_enable={1 if slot.enabled else 0}")
            if slot.value:
                lines.append(f"dpi{slot_num}={slot.value}")

        for key, value in profile.raw.items():
            lines.append(f"{key}={value}")

    if config.macros:
        lines.append("")
        for macro_num in sorted(config.macros):
            lines.append("")
            lines.append(f";## macro{macro_num}")
            lines.extend(config.macros[macro_num])

    path.write_text("\n".join(lines) + "\n")
