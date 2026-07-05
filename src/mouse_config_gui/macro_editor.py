"""Macro editor: a manual sequencer for the shared 15-slot macro store
(design doc §10). Macros are MouseConfig-level, not per-profile, so unlike
LED/DPI/Buttons this is a standalone dialog rather than embedded in a
profile page.

Add/remove/reorder only -- no in-place value editing (delete + re-add
instead), and no live key-capture recording. Both were considered and
deliberately deferred to keep this first version at the same reliability
level as the rest of the app.
"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk

from mouse_config_gui.button_picker import selected_dropdown_string
from mouse_config_gui.keymap import (
    MACRO_ACTION_KINDS,
    MACRO_MOUSE_BUTTONS,
    MAX_MACRO_ACTIONS,
    grammar_data,
    is_valid_macro_action,
)
from mouse_config_gui.models import MacroAction

NUM_MACRO_SLOTS = 15

_KIND_LABELS = {
    "down": "Down",
    "up": "Up",
    "delay": "Delay",
    "move_left": "Move Left",
    "move_right": "Move Right",
    "move_up": "Move Up",
    "move_down": "Move Down",
}


def _action_row_title(action: MacroAction) -> str:
    label = _KIND_LABELS[action.kind]
    if action.kind == "delay":
        return f"{label}: {action.value} ({int(action.value) * 10} ms)"
    return f"{label}: {action.value}"


def _down_up_value_dropdown() -> Gtk.DropDown:
    """down/up accept a keyboard key or one of 5 mouse buttons (notably
    including forward/backward, which fire:'s button set does not) --
    combine both into one searchable list rather than reusing
    button_picker.searchable_key_dropdown(), which only has keys."""
    values = [*MACRO_MOUSE_BUTTONS, *sorted(grammar_data()["keys"])]
    dropdown = Gtk.DropDown.new_from_strings(values)
    dropdown.set_enable_search(True)
    dropdown.set_expression(Gtk.PropertyExpression.new(Gtk.StringObject, None, "string"))
    return dropdown


class _ActionRow(Adw.ActionRow):
    """One action in the sequence: reorder buttons as prefix, delete as suffix."""

    def __init__(self, action: MacroAction, index: int, on_move, on_delete):
        super().__init__()
        # Adw.ActionRow's title defaults to Pango markup -- action.value can
        # come from a loaded file (not just this editor's own constrained
        # widgets), so an unescaped "&"/"<" would fail to parse and render
        # blank rather than the actual text. Titles here never need markup
        # formatting, so disabling it outright is simpler than escaping.
        self.set_use_markup(False)
        self.set_title(_action_row_title(action))

        up_button = Gtk.Button(icon_name="go-up-symbolic", valign=Gtk.Align.CENTER)
        up_button.add_css_class("flat")
        up_button.connect("clicked", lambda _b: on_move(index, -1))
        self.add_prefix(up_button)

        down_button = Gtk.Button(icon_name="go-down-symbolic", valign=Gtk.Align.CENTER)
        down_button.add_css_class("flat")
        down_button.connect("clicked", lambda _b: on_move(index, 1))
        self.add_prefix(down_button)

        delete_button = Gtk.Button(icon_name="user-trash-symbolic", valign=Gtk.Align.CENTER)
        delete_button.add_css_class("flat")
        delete_button.connect("clicked", lambda _b: on_delete(index))
        self.add_suffix(delete_button)


class MacroEditorDialog(Adw.Dialog):
    """Operates directly on the given macros dict (mutated in place), same
    "shared mutable state + on_changed callback" convention every other
    group (LedGroup, DpiGroup, ButtonGroup) already uses."""

    def __init__(self, macros: dict[int, list[MacroAction]], on_changed=None, **kwargs):
        super().__init__(title="Macros", content_width=720, content_height=560, **kwargs)
        self._macros = macros
        self._on_changed = on_changed
        self._selected_slot = 1
        self._sidebar_rows: dict[int, Adw.ActionRow] = {}

        sidebar_list = Gtk.ListBox()
        sidebar_list.add_css_class("navigation-sidebar")
        sidebar_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        for slot in range(1, NUM_MACRO_SLOTS + 1):
            row = Adw.ActionRow(title=f"Macro {slot}", subtitle=self._slot_subtitle(slot))
            row.macro_slot = slot
            self._sidebar_rows[slot] = row
            sidebar_list.append(row)
        sidebar_list.connect("row-selected", self._on_row_selected)

        sidebar_scrolled = Gtk.ScrolledWindow(child=sidebar_list, vexpand=True)
        sidebar_toolbar = Adw.ToolbarView()
        sidebar_toolbar.add_top_bar(Adw.HeaderBar())
        sidebar_toolbar.set_content(sidebar_scrolled)
        sidebar_page = Adw.NavigationPage(title="Macros", child=sidebar_toolbar)

        self._count_label = Gtk.Label(xalign=0)
        self._count_label.add_css_class("dim-label")

        self.list_box = Gtk.ListBox()
        self.list_box.add_css_class("boxed-list")
        self.list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        list_scrolled = Gtk.ScrolledWindow(child=self.list_box, vexpand=True)

        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content_box.set_margin_top(12)
        content_box.set_margin_bottom(12)
        content_box.set_margin_start(12)
        content_box.set_margin_end(12)
        content_box.append(self._count_label)
        content_box.append(list_scrolled)
        content_box.append(self._build_add_form())

        content_toolbar = Adw.ToolbarView()
        content_toolbar.add_top_bar(Adw.HeaderBar())
        content_toolbar.set_content(content_box)
        self._content_page = Adw.NavigationPage(title="Macro 1", child=content_toolbar)

        split_view = Adw.NavigationSplitView(sidebar=sidebar_page, content=self._content_page)
        self.set_child(split_view)

        sidebar_list.select_row(self._sidebar_rows[1])
        self._refresh_action_list()

    def _build_add_form(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        self._kind_dropdown = Gtk.DropDown.new_from_strings(
            [_KIND_LABELS[kind] for kind in MACRO_ACTION_KINDS]
        )
        box.append(self._kind_dropdown)

        self._key_dropdown = _down_up_value_dropdown()
        self._number_spin = Gtk.SpinButton.new_with_range(1, 255, 1)

        self._value_stack = Gtk.Stack()
        self._value_stack.add_named(self._key_dropdown, "key")
        self._value_stack.add_named(self._number_spin, "number")
        self._value_stack.set_hexpand(True)
        box.append(self._value_stack)

        self._kind_dropdown.connect("notify::selected", self._on_kind_changed)
        self._on_kind_changed()

        self.add_button = Gtk.Button(label="Add")
        self.add_button.add_css_class("suggested-action")
        self.add_button.connect("clicked", self._on_add_clicked)
        box.append(self.add_button)

        return box

    def _current_kind(self) -> str:
        return MACRO_ACTION_KINDS[self._kind_dropdown.get_selected()]

    def _on_kind_changed(self, *_args) -> None:
        kind = self._current_kind()
        if kind in ("down", "up"):
            self._value_stack.set_visible_child_name("key")
        else:
            self._value_stack.set_visible_child_name("number")
            upper = 255 if kind == "delay" else 120
            self._number_spin.set_range(1, upper)
            self._number_spin.set_value(1)

    def _current_value(self) -> str:
        if self._current_kind() in ("down", "up"):
            return selected_dropdown_string(self._key_dropdown)
        return str(self._number_spin.get_value_as_int())

    def _on_row_selected(self, _list_box, row) -> None:
        if row is None:
            return
        self._selected_slot = row.macro_slot
        self._content_page.set_title(f"Macro {row.macro_slot}")
        self._refresh_action_list()

    def _slot_subtitle(self, slot: int) -> str:
        count = len(self._macros.get(slot, []))
        if count == 0:
            return "Empty"
        return f"{count} action" + ("" if count == 1 else "s")

    def _refresh_action_list(self) -> None:
        while (row := self.list_box.get_row_at_index(0)) is not None:
            self.list_box.remove(row)

        actions = self._macros.get(self._selected_slot, [])
        for index, action in enumerate(actions):
            self.list_box.append(_ActionRow(action, index, self._on_move, self._on_delete))

        self._count_label.set_label(f"{len(actions)} / {MAX_MACRO_ACTIONS} actions")
        self.add_button.set_sensitive(len(actions) < MAX_MACRO_ACTIONS)

    def _notify_changed(self) -> None:
        if self._on_changed is not None:
            self._on_changed()

    def _on_add_clicked(self, _button) -> None:
        actions = self._macros.setdefault(self._selected_slot, [])
        if len(actions) >= MAX_MACRO_ACTIONS:
            return
        kind, value = self._current_kind(), self._current_value()
        if not is_valid_macro_action(kind, value):
            return  # shouldn't happen -- values come from constrained widgets
        actions.append(MacroAction(kind=kind, value=value))
        self._refresh_action_list()
        self._sidebar_rows[self._selected_slot].set_subtitle(self._slot_subtitle(self._selected_slot))
        self._notify_changed()

    def _on_move(self, index: int, direction: int) -> None:
        actions = self._macros.get(self._selected_slot, [])
        new_index = index + direction
        if not (0 <= new_index < len(actions)):
            return
        actions[index], actions[new_index] = actions[new_index], actions[index]
        self._refresh_action_list()
        self._notify_changed()

    def _on_delete(self, index: int) -> None:
        actions = self._macros.get(self._selected_slot, [])
        del actions[index]
        if not actions:
            self._macros.pop(self._selected_slot, None)
        self._refresh_action_list()
        self._sidebar_rows[self._selected_slot].set_subtitle(self._slot_subtitle(self._selected_slot))
        self._notify_changed()
