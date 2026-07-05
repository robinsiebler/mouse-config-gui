"""Loads per-model capability descriptors from the bundled capabilities/*.yaml
(design doc §3.3), via importlib.resources rather than a filesystem path
relative to this file -- that assumption breaks once the package is actually
installed (e.g. `pip install git+https://...`) instead of run from an
editable source checkout, since capabilities/ then lives inside the
installed package, not N parents up from capability.py.
"""

from dataclasses import dataclass
from importlib import resources
from typing import Any

import yaml


def _capabilities_dir() -> Any:
    # Return type is importlib.resources.abc.Traversable, but that submodule
    # only exists from Python 3.11 -- this project supports 3.10 too.
    return resources.files("mouse_config_gui") / "capabilities"


@dataclass
class Capability:
    data: dict[str, Any]

    @property
    def model(self) -> str:
        return self.data["model"]


def list_capabilities() -> list[str]:
    """Return the names (without .yaml) of all available capability descriptors."""
    return sorted(
        p.name.removesuffix(".yaml")
        for p in _capabilities_dir().iterdir()
        if p.name.endswith(".yaml")
    )


def load_capability(name: str) -> Capability:
    """Load a single capability descriptor by name, e.g. load_capability("m908")."""
    text = (_capabilities_dir() / f"{name}.yaml").read_text()
    return Capability(data=yaml.safe_load(text))


def find_capability_by_usb(vid: int, pid: int) -> str | None:
    """Return the capability name whose usb.vid/usb.pids match, or None.

    Descriptors other than "generic" are checked first, so a model with its
    own dedicated descriptor takes priority over generic's broad PID
    allowlist (which includes PIDs that also have a dedicated file, e.g.
    M908's 0xfc4d).
    """
    names = [n for n in list_capabilities() if n != "generic"]
    names.append("generic")

    for name in names:
        usb = load_capability(name).data.get("usb")
        if usb and usb.get("vid") == vid and pid in usb.get("pids", []):
            return name

    return None


def find_capability_by_model_name(model_name: str) -> str | None:
    """Return the capability name (file stem) whose `model:` field equals
    model_name, or None if none matches.

    model_name is the CLI's -M value / a config file's "# Model:" line (e.g.
    "607", "990chroma") -- NOT the same as the capability file stem (e.g.
    "m607", "m990chroma"); the "m" prefix only exists in filenames, not in
    the data, so this lookup can't be a simple `in list_capabilities()` check.
    """
    for name in list_capabilities():
        if load_capability(name).model == model_name:
            return name
    return None
