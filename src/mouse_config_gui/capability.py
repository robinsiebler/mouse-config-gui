"""Loads per-model capability descriptors from capabilities/*.yaml (design doc §3.3)."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

CAPABILITIES_DIR = Path(__file__).resolve().parents[2] / "capabilities"


@dataclass
class Capability:
    data: dict[str, Any]

    @property
    def model(self) -> str:
        return self.data["model"]


def list_capabilities(directory: Path = CAPABILITIES_DIR) -> list[str]:
    """Return the names (without .yaml) of all available capability descriptors."""
    return sorted(p.stem for p in directory.glob("*.yaml"))


def load_capability(name: str, directory: Path = CAPABILITIES_DIR) -> Capability:
    """Load a single capability descriptor by name, e.g. load_capability("m908")."""
    path = directory / f"{name}.yaml"
    with path.open() as f:
        return Capability(data=yaml.safe_load(f))


def find_capability_by_usb(
    vid: int, pid: int, directory: Path = CAPABILITIES_DIR
) -> str | None:
    """Return the capability name whose usb.vid/usb.pids match, or None.

    Descriptors other than "generic" are checked first, so a model with its
    own dedicated descriptor takes priority over generic's broad PID
    allowlist (which includes PIDs that also have a dedicated file, e.g.
    M908's 0xfc4d).
    """
    names = [n for n in list_capabilities(directory) if n != "generic"]
    names.append("generic")

    for name in names:
        usb = load_capability(name, directory).data.get("usb")
        if usb and usb.get("vid") == vid and pid in usb.get("pids", []):
            return name

    return None


def find_capability_by_model_name(model_name: str, directory: Path = CAPABILITIES_DIR) -> str | None:
    """Return the capability name (file stem) whose `model:` field equals
    model_name, or None if none matches.

    model_name is the CLI's -M value / a config file's "# Model:" line (e.g.
    "607", "990chroma") -- NOT the same as the capability file stem (e.g.
    "m607", "m990chroma"); the "m" prefix only exists in filenames, not in
    the data, so this lookup can't be a simple `in list_capabilities()` check.
    """
    for name in list_capabilities(directory):
        if load_capability(name, directory).model == model_name:
            return name
    return None
