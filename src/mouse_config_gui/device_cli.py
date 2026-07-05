"""Subprocess wrapper around the `mouse_m908` CLI (design doc §4.2) and device
auto-detection via VID 0x04d9 (§11.2).

Calls here are synchronous/blocking by design -- the caller (GUI layer) is
responsible for running them off the main thread (GLib subprocess or a worker
thread) so the UI doesn't block, per §4.2.
"""

import re
import subprocess
from pathlib import Path

from mouse_config_gui import capability

CLI_BIN = "mouse_m908"

_LSUSB_ID_RE = re.compile(r"ID\s+([0-9a-fA-F]{4}):([0-9a-fA-F]{4})")


class MouseCliError(Exception):
    """Raised when `mouse_m908` exits non-zero. Carries its stderr output."""

    def __init__(self, message: str, stderr: str = ""):
        super().__init__(message)
        self.stderr = stderr


class MouseNotFoundError(MouseCliError):
    """Raised when `mouse_m908` can't detect or open the device (permissions,
    udev rules, or no device attached)."""


def _run(args: list[str]) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(
            [CLI_BIN, *args], capture_output=True, text=True, check=False
        )
    except FileNotFoundError as e:
        raise MouseCliError(f"{CLI_BIN} is not installed or not on PATH") from e

    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "Couldn't detect mouse" in stderr or "Couldn't open mouse" in stderr:
            raise MouseNotFoundError(stderr, stderr=stderr)
        raise MouseCliError(stderr or f"{CLI_BIN} exited with code {result.returncode}", stderr=stderr)

    return result


def detect_model() -> str | None:
    """Parse `lsusb` for any device matching a known capability descriptor's
    usb.vid/usb.pids (see capabilities/*.yaml) and return its capability name
    (e.g. "m908"), or None if nothing matches (or lsusb isn't available).

    Note not every supported mouse uses VID 0x04d9 -- m686/m913 are a
    different wireless family on 0x25a7 -- so every "ID vid:pid" pair in
    lsusb's output is checked against the capability descriptors' USB ids.
    """
    try:
        result = subprocess.run(["lsusb"], capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return None

    if result.returncode != 0:
        return None

    for line in result.stdout.splitlines():
        if match := _LSUSB_ID_RE.search(line):
            vid, pid = int(match.group(1), 16), int(match.group(2), 16)
            if name := capability.find_capability_by_usb(vid, pid):
                return name

    return None


def list_models() -> list[str]:
    """mouse_m908 -M ? -- the CLI's own list of valid --model names."""
    result = _run(["-M", "?"])
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def apply_config(path: Path, model: str | None = None) -> None:
    """mouse_m908 -c <path> [-M <model>]"""
    args = ["-c", str(path)]
    if model is not None:
        args += ["-M", model]
    _run(args)


def read_config(path: Path, model: str | None = None) -> None:
    """mouse_m908 -R <path> [-M <model>]"""
    args = ["-R", str(path)]
    if model is not None:
        args += ["-M", model]
    _run(args)


def set_active_profile(n: int, model: str | None = None) -> None:
    """mouse_m908 -p <n> [-M <model>]"""
    args = ["-p", str(n)]
    if model is not None:
        args += ["-M", model]
    _run(args)
