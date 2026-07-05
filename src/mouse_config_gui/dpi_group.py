"""DPI settings group for a single profile: 5 slots, each with an enable
checkbox and a validated value entry (design doc §5, §6, §7).

Validation is derived from the capability descriptor rather than hardcoded:
decimal values are checked against the exact set implied by
dpi.actual_step_breakpoints (matching mouse_m908's own lookup-table behavior,
not just a loose min/max range), and bytecode is checked against the universal
0x[04-8c][00-01] bounds shared by every model.
"""

import re

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk

from mouse_config_gui.capability import Capability

NUM_DPI_SLOTS = 5

_BYTECODE_RE = re.compile(r"^0x([0-9a-fA-F]{2})([0-9a-fA-F]{2})$")


def _valid_actual_values(dpi: dict) -> set[int]:
    values: set[int] = set()
    for lo, hi, step in dpi.get("actual_step_breakpoints", []):
        values.update(range(lo, hi + 1, step))
    if not values and "actual_range" in dpi:
        lo, hi = dpi["actual_range"]
        values.update(range(lo, hi + 1))
    return values


def _is_valid_bytecode(value: str) -> bool:
    match = _BYTECODE_RE.match(value)
    if not match:
        return False
    byte0, byte1 = int(match.group(1), 16), int(match.group(2), 16)
    return 0x04 <= byte0 <= 0x8C and byte1 in (0x00, 0x01)


class DpiRow(Adw.EntryRow):
    """One DPI slot: an enable checkbox prefix + the value as this row's own
    editable text, validated live against the model's dpi.formats."""

    def __init__(self, slot_num: int, capability: Capability, on_enabled_changed, on_changed=None):
        super().__init__(title=f"DPI {slot_num}")
        self.slot_num = slot_num
        self._on_enabled_changed = on_enabled_changed
        self._on_changed = on_changed

        self.enable_check = Gtk.CheckButton()
        self.enable_check.set_valign(Gtk.Align.CENTER)
        self.enable_check.set_active(True)
        self.enable_check.connect("toggled", self._on_toggle)
        self.add_prefix(self.enable_check)

        self.connect("changed", self._on_text_changed)
        self.apply_capability(capability)

    def _notify_changed(self) -> None:
        if self._on_changed is not None:
            self._on_changed()

    def _on_text_changed(self, _entry) -> None:
        if self._filter_input():
            return  # set_text() below re-enters this handler; let that call finish the job
        self._validate()
        self._notify_changed()

    def _allowed_chars(self) -> str:
        # DPI input isn't purely numeric: models that support bytecode format
        # need "0x1600"-style hex too. Restricting to plain digits would make
        # it impossible to type a valid value on bytecode-only models.
        if "bytecode" in self._dpi["formats"]:
            return "0123456789xXabcdefABCDEF"
        return "0123456789"

    def _filter_input(self) -> bool:
        """Strip characters that could never be part of a valid value for the
        current model. Returns True if it rewrote the text -- GtkEditable's
        own "changed" signal fires again synchronously from set_text(), so
        the caller should let that nested call do the validate/notify work
        instead of doing it twice for one edit.

        Note: filtering via the "insert-text" signal (the more obvious hook)
        has a real PyGObject marshaling bug for its in/out `position`
        argument -- verified empirically that it scrambles character order
        under rapid input. Filtering post-hoc on "changed" instead avoids it.
        """
        text = self.get_text()
        allowed = self._allowed_chars()
        filtered = "".join(c for c in text if c in allowed)
        if filtered == text:
            return False

        position = self.get_position()
        kept_before_cursor = sum(1 for c in text[:position] if c in allowed)
        self.set_text(filtered)
        self.set_position(kept_before_cursor)
        return True

    def apply_capability(self, capability: Capability) -> None:
        self._dpi = capability.data["dpi"]
        self._valid_actual = _valid_actual_values(self._dpi)
        self._filter_input()
        self._validate()

    def _on_toggle(self, _button) -> None:
        # Only toggle editability, not overall sensitivity -- disabling the
        # whole row would also disable this checkbox (child sensitivity
        # cascades from the parent), making it impossible to re-enable.
        self.set_editable(self.enable_check.get_active())
        self._on_enabled_changed()
        self._notify_changed()

    def _validate(self) -> None:
        if self.is_valid:
            self.remove_css_class("error")
        else:
            self.add_css_class("error")

    @property
    def is_valid(self) -> bool:
        value = self.value
        if not value:
            return True  # empty means "use mouse default" (design doc §7)
        formats = self._dpi["formats"]
        if "actual" in formats and value.isdigit() and int(value) in self._valid_actual:
            return True
        if "bytecode" in formats and _is_valid_bytecode(value):
            return True
        return False

    @property
    def enabled(self) -> bool:
        return self.enable_check.get_active()

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self.enable_check.set_active(value)

    @property
    def value(self) -> str:
        return self.get_text().strip()

    @value.setter
    def value(self, text: str) -> None:
        self.set_text(text)


class DpiGroup(Adw.PreferencesGroup):
    def __init__(self, capability: Capability, on_changed=None, **kwargs):
        super().__init__(title="DPI", **kwargs)

        self.rows: dict[int, DpiRow] = {}
        for slot_num in range(1, NUM_DPI_SLOTS + 1):
            row = DpiRow(slot_num, capability, self._enforce_min_enabled, on_changed)
            self.rows[slot_num] = row
            self.add(row)

        self._min_enabled = capability.data["dpi"]["min_enabled"]
        self._enforce_min_enabled()

    def apply_capability(self, capability: Capability) -> None:
        self._min_enabled = capability.data["dpi"]["min_enabled"]
        for row in self.rows.values():
            row.apply_capability(capability)
        self._enforce_min_enabled()

    def _enforce_min_enabled(self) -> None:
        enabled_rows = [row for row in self.rows.values() if row.enabled]
        lock = len(enabled_rows) <= self._min_enabled
        for row in self.rows.values():
            row.enable_check.set_sensitive(not (lock and row in enabled_rows))
