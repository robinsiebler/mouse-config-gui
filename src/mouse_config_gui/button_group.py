"""Button mapping group for a single profile: one validated entry row per
programmable button, driven by the mouse model's capability descriptor
(design doc §5, §10).

The set of buttons (names and count) genuinely differs by model -- 8 on
generic, 20 on M908, 26 on M990 -- unlike DPI's fixed 5 slots across every
model, so apply_capability() rebuilds the row list rather than just
re-labeling existing rows (mirrors dpi_group.py's validation approach, not
its fixed-row-count shape).
"""

import re

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk

from mouse_config_gui.button_picker import build_picker_button
from mouse_config_gui.capability import Capability
from mouse_config_gui.keymap import is_valid_button_mapping

_BUTTON_NUM_RE = re.compile(r"^button_(\d+)$")

# Curated illustrative examples, not the full grammar -- the validator's own
# source of truth is keymap.py/keymap_data.yaml. This is UI copy to answer
# "what do I type here" without sending the user to design_docs/keymap.md.
_SYNTAX_HELP = (
    "<b>Plain key</b> — <tt>a</tt>, <tt>F1</tt>, <tt>Delete</tt>\n"
    "<b>Key combo</b> — <tt>super_l+shift_l+2</tt>\n"
    "<b>Mouse button / special</b> — <tt>left</tt>, <tt>dpi+</tt>, "
    "<tt>dpi-cycle</tt>, <tt>profile_switch</tt>\n"
    "<b>Fire</b> (rapid-fire presses) — <tt>fire:button:repeats:delay</tt>, "
    "e.g. <tt>fire:mouse_left:5:1</tt>\n"
    "<b>Snipe</b> (temporary DPI while held) — <tt>snipe:dpi</tt>, "
    "e.g. <tt>snipe:500</tt>\n"
    "<b>Macro</b> — <tt>macro3</tt>, <tt>macro3:5</tt>, <tt>macro3:while</tt>, "
    "<tt>macro3:until</tt>\n"
    "<b>Media / compatibility</b> — <tt>media_play</tt>, "
    "<tt>compatibility_copy</tt>\n"
    "<b>Raw bytes</b> (debugging) — <tt>0x11aa22bb</tt>\n"
    "\n"
    "Leave blank to leave a button's mapping unchanged."
)


def _build_help_button() -> Gtk.MenuButton:
    label = Gtk.Label(label=_SYNTAX_HELP, use_markup=True, wrap=True, xalign=0)
    label.set_max_width_chars(48)
    label.set_margin_top(12)
    label.set_margin_bottom(12)
    label.set_margin_start(12)
    label.set_margin_end(12)

    popover = Gtk.Popover(child=label)

    button = Gtk.MenuButton(icon_name="dialog-question-symbolic", popover=popover)
    button.set_tooltip_text("Button mapping syntax")
    button.set_valign(Gtk.Align.CENTER)
    return button


def _humanize(name: str) -> str:
    """"button_dpi_up" -> "DPI Up", "scroll_up" -> "Scroll Up", "button_1" -> "Button 1"."""
    if match := _BUTTON_NUM_RE.match(name):
        return f"Button {match.group(1)}"
    words = name.removeprefix("button_").replace("_", " ").split()
    return " ".join(w.upper() if w == "dpi" else w.capitalize() for w in words)


class ButtonRow(Adw.EntryRow):
    """One button's mapping, validated live against keymap.py's grammar."""

    def __init__(self, name: str, num_macro_slots: int, on_changed=None):
        super().__init__(title=_humanize(name))
        self.name = name
        self._num_macro_slots = num_macro_slots
        self._on_changed = on_changed

        self.add_suffix(build_picker_button(self._on_picked, num_macro_slots))
        self.connect("changed", self._on_text_changed)

    def _on_picked(self, value: str) -> None:
        self.value = value

    def _on_text_changed(self, _entry) -> None:
        self._validate()
        if self._on_changed is not None:
            self._on_changed()

    def _validate(self) -> None:
        if self.is_valid:
            self.remove_css_class("error")
        else:
            self.add_css_class("error")

    @property
    def is_valid(self) -> bool:
        return is_valid_button_mapping(self.value, num_macro_slots=self._num_macro_slots)

    @property
    def value(self) -> str:
        return self.get_text().strip()

    @value.setter
    def value(self, text: str) -> None:
        self.set_text(text)
        self._validate()


class ButtonGroup(Adw.PreferencesGroup):
    def __init__(self, capability: Capability, on_changed=None, **kwargs):
        super().__init__(title="Buttons", **kwargs)
        self.set_header_suffix(_build_help_button())
        self._on_changed = on_changed
        self.rows: dict[str, ButtonRow] = {}
        # Mapping keys loaded from a config whose button set doesn't match the
        # currently selected model's row list -- kept so Apply/Save doesn't
        # silently drop them (design doc §8's round-trip guarantee).
        self._unmatched: dict[str, str] = {}

        self.apply_capability(capability)

    def _notify_changed(self) -> None:
        if self._on_changed is not None:
            self._on_changed()

    def apply_capability(self, capability: Capability) -> None:
        previous = self.mappings
        num_macro_slots = capability.data["num_macro_slots"]
        names = capability.data["buttons"]["names"]

        for row in self.rows.values():
            self.remove(row)
        self.rows = {}

        for name in names:
            row = ButtonRow(name, num_macro_slots, on_changed=self._notify_changed)
            if name in previous:
                row.value = previous[name]
            self.rows[name] = row
            self.add(row)

        self._unmatched = {k: v for k, v in previous.items() if k not in self.rows}

    @property
    def mappings(self) -> dict[str, str]:
        result = {name: row.value for name, row in self.rows.items() if row.value}
        result.update(self._unmatched)
        return result

    def set_mappings(self, mappings: dict[str, str]) -> None:
        for row in self.rows.values():
            row.value = ""
        self._unmatched = {}
        for name, value in mappings.items():
            if name in self.rows:
                self.rows[name].value = value
            else:
                self._unmatched[name] = value

    @property
    def invalid_names(self) -> list[str]:
        return [name for name, row in self.rows.items() if not row.is_valid]
