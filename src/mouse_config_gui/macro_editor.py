"""Macro editor: a manual sequencer for the shared 15-slot macro store
(design doc §10). Macros are MouseConfig-level, not per-profile, so unlike
LED/DPI/Buttons this is a standalone dialog rather than embedded in a
profile page.

Add/remove/reorder/edit an action's kind+value in place -- no live
key-capture recording, which was considered and deliberately deferred to
keep this first version at the same reliability level as the rest of the
app.
"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk

from mouse_config_gui import macro_library
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


def _down_up_values() -> list[str]:
    """down/up accept a keyboard key or one of 5 mouse buttons (notably
    including forward/backward, which fire:'s button set does not) --
    combine both into one searchable list rather than reusing
    button_picker.searchable_key_dropdown(), which only has keys."""
    return [*MACRO_MOUSE_BUTTONS, *sorted(grammar_data()["keys"])]


def _down_up_value_dropdown() -> Gtk.DropDown:
    dropdown = Gtk.DropDown.new_from_strings(_down_up_values())
    dropdown.set_enable_search(True)
    dropdown.set_expression(Gtk.PropertyExpression.new(Gtk.StringObject, None, "string"))
    return dropdown


def _build_kind_value_widgets(
    initial: MacroAction | None = None,
) -> tuple[Gtk.Widget, Gtk.DropDown, Gtk.DropDown, Gtk.SpinButton]:
    """A kind dropdown + a value widget that swaps between a searchable key
    dropdown (down/up) and a spin button (delay/move_*), used identically by
    the Add form and the Edit-action dialog -- one widget-building path so
    they can't drift apart. Returns (container, kind_dropdown, key_dropdown,
    number_spin); read the current value via selected_dropdown_string()/
    get_value_as_int() on whichever of the latter two is visible.
    """
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

    kind_dropdown = Gtk.DropDown.new_from_strings([_KIND_LABELS[kind] for kind in MACRO_ACTION_KINDS])
    box.append(kind_dropdown)

    key_dropdown = _down_up_value_dropdown()
    number_spin = Gtk.SpinButton.new_with_range(1, 255, 1)
    value_stack = Gtk.Stack()
    value_stack.add_named(key_dropdown, "key")
    value_stack.add_named(number_spin, "number")
    value_stack.set_hexpand(True)
    box.append(value_stack)

    def sync_stack_and_range(*_args) -> None:
        kind = MACRO_ACTION_KINDS[kind_dropdown.get_selected()]
        if kind in ("down", "up"):
            value_stack.set_visible_child_name("key")
        else:
            value_stack.set_visible_child_name("number")
            upper = 255 if kind == "delay" else 120
            number_spin.set_range(1, upper)
            number_spin.set_value(1)

    kind_dropdown.connect("notify::selected", sync_stack_and_range)

    if initial is not None:
        kind_dropdown.set_selected(MACRO_ACTION_KINDS.index(initial.kind))
    sync_stack_and_range()  # sets the stack page even if set_selected() above was a no-op

    if initial is not None:
        if initial.kind in ("down", "up"):
            key_dropdown.set_selected(_down_up_values().index(initial.value))
        else:
            number_spin.set_value(int(initial.value))

    return box, kind_dropdown, key_dropdown, number_spin


class _ActionRow(Adw.ActionRow):
    """One action in the sequence: reorder buttons as prefix, edit/delete as suffix."""

    def __init__(self, action: MacroAction, index: int, on_move, on_edit, on_delete):
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

        edit_button = Gtk.Button(icon_name="document-edit-symbolic", valign=Gtk.Align.CENTER)
        edit_button.add_css_class("flat")
        edit_button.connect("clicked", lambda _b: on_edit(index))
        self.add_suffix(edit_button)

        delete_button = Gtk.Button(icon_name="user-trash-symbolic", valign=Gtk.Align.CENTER)
        delete_button.add_css_class("flat")
        delete_button.connect("clicked", lambda _b: on_delete(index))
        self.add_suffix(delete_button)


class MacroEditorDialog(Adw.Dialog):
    """Operates directly on the given macros/macro_names dicts (mutated in
    place), same "shared mutable state + on_changed callback" convention
    every other group (LedGroup, DpiGroup, ButtonGroup) already uses. The
    macro library is different -- not part of MouseConfig, so it's loaded/
    saved directly against disk here rather than threaded through
    MainWindow, and never calls on_changed() by itself (see _on_load_from_library
    for the one exception: loading a library entry INTO a slot does touch
    self._macros, so that path does mark the config dirty)."""

    def __init__(
        self,
        macros: dict[int, list[MacroAction]],
        macro_names: dict[int, str],
        get_macro_references,
        on_changed=None,
        **kwargs,
    ):
        super().__init__(title="Macros", content_width=960, content_height=640, **kwargs)
        self._macros = macros
        self._macro_names = macro_names
        self._get_macro_references = get_macro_references
        self._on_changed = on_changed
        self._selected_slot = 1
        self._sidebar_rows: dict[int, Adw.ActionRow] = {}
        self._updating_name_entry = False
        self._library = macro_library.load_library()

        sidebar_list = Gtk.ListBox()
        sidebar_list.add_css_class("navigation-sidebar")
        sidebar_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        for slot in range(1, NUM_MACRO_SLOTS + 1):
            row = Adw.ActionRow(title=self._slot_title(slot), subtitle=self._slot_subtitle(slot))
            # Title can now be a name loaded from a file -- same untrusted-
            # markup concern _ActionRow already guards against.
            row.set_use_markup(False)
            row.macro_slot = slot
            self._sidebar_rows[slot] = row
            sidebar_list.append(row)
        sidebar_list.connect("row-selected", self._on_row_selected)

        sidebar_scrolled = Gtk.ScrolledWindow(child=sidebar_list, vexpand=True)
        sidebar_toolbar = Adw.ToolbarView()
        sidebar_toolbar.add_top_bar(Adw.HeaderBar())
        sidebar_toolbar.set_content(sidebar_scrolled)
        sidebar_page = Adw.NavigationPage(title="Macros", child=sidebar_toolbar)

        self._name_entry = Adw.EntryRow(title="Name (optional)")
        self._name_entry.connect("changed", self._on_name_changed)
        name_list = Gtk.ListBox()
        name_list.add_css_class("boxed-list")
        name_list.set_selection_mode(Gtk.SelectionMode.NONE)
        name_list.append(self._name_entry)

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
        content_box.append(name_list)
        content_box.append(self._count_label)
        content_box.append(list_scrolled)
        content_box.append(self._build_add_form())
        content_box.append(self._build_library_actions())

        content_toolbar = Adw.ToolbarView()
        content_toolbar.add_top_bar(Adw.HeaderBar())
        content_toolbar.set_content(content_box)
        self._content_page = Adw.NavigationPage(title="Macro 1", child=content_toolbar)

        split_view = Adw.NavigationSplitView(sidebar=sidebar_page, content=self._content_page)

        self._toast_overlay = Adw.ToastOverlay()
        self._toast_overlay.set_child(split_view)
        self.set_child(self._toast_overlay)

        sidebar_list.select_row(self._sidebar_rows[1])
        self._refresh_slot_view()

    def _build_add_form(self) -> Gtk.Widget:
        box, self._kind_dropdown, self._key_dropdown, self._number_spin = _build_kind_value_widgets()

        self.add_button = Gtk.Button(label="Add")
        self.add_button.add_css_class("suggested-action")
        self.add_button.connect("clicked", self._on_add_clicked)
        box.append(self.add_button)

        return box

    def _current_kind(self) -> str:
        return MACRO_ACTION_KINDS[self._kind_dropdown.get_selected()]

    def _current_value(self) -> str:
        if self._current_kind() in ("down", "up"):
            return selected_dropdown_string(self._key_dropdown)
        return str(self._number_spin.get_value_as_int())

    def _on_row_selected(self, _list_box, row) -> None:
        if row is None:
            return
        self._selected_slot = row.macro_slot
        self._content_page.set_title(self._slot_title(row.macro_slot))
        self._refresh_slot_view()

    def _slot_title(self, slot: int) -> str:
        return self._macro_names.get(slot) or f"Macro {slot}"

    def _slot_subtitle(self, slot: int) -> str:
        count = len(self._macros.get(slot, []))
        count_text = "Empty" if count == 0 else f"{count} action" + ("" if count == 1 else "s")
        # Named slots still show their number, so the numbered identity
        # (what the device/keymap.md macroN reference actually means)
        # doesn't disappear behind the name.
        if self._macro_names.get(slot):
            return f"Macro {slot} · {count_text}"
        return count_text

    def _refresh_sidebar_row(self, slot: int) -> None:
        row = self._sidebar_rows[slot]
        row.set_title(self._slot_title(slot))
        row.set_subtitle(self._slot_subtitle(slot))
        if slot == self._selected_slot:
            self._content_page.set_title(self._slot_title(slot))

    def _refresh_slot_view(self) -> None:
        self._updating_name_entry = True
        self._name_entry.set_text(self._macro_names.get(self._selected_slot, ""))
        self._updating_name_entry = False
        self._refresh_action_list()

    def _on_name_changed(self, entry: Adw.EntryRow) -> None:
        if self._updating_name_entry:
            return
        text = entry.get_text().strip()
        if text:
            self._macro_names[self._selected_slot] = text
        else:
            self._macro_names.pop(self._selected_slot, None)
        self._refresh_sidebar_row(self._selected_slot)
        # Persisted independent of Apply/Save, same as the library, so a
        # name survives the next launch's automatic "Read from Mouse" (which
        # always comes back name-less -- there's nowhere on the mouse to
        # store one).
        macro_library.save_slot_names(self._macro_names)
        self._notify_changed()

    def _refresh_action_list(self) -> None:
        while (row := self.list_box.get_row_at_index(0)) is not None:
            self.list_box.remove(row)

        actions = self._macros.get(self._selected_slot, [])
        for index, action in enumerate(actions):
            self.list_box.append(
                _ActionRow(action, index, self._on_move, self._on_edit_action_clicked, self._on_delete)
            )

        self._count_label.set_label(f"{len(actions)} / {MAX_MACRO_ACTIONS} actions")
        self.add_button.set_sensitive(len(actions) < MAX_MACRO_ACTIONS)

    def _notify_changed(self) -> None:
        if self._on_changed is not None:
            self._on_changed()

    def _confirm(self, heading: str, body: str, confirm_label: str, on_confirm) -> None:
        dialog = Adw.AlertDialog(heading=heading, body=body)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("confirm", confirm_label)
        dialog.set_response_appearance("confirm", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")

        def on_response(_dialog: Adw.AlertDialog, response: str) -> None:
            if response == "confirm":
                on_confirm()

        dialog.connect("response", on_response)
        dialog.present(self)

    def _reference_warning(self, slot: int) -> str:
        """" Currently mapped to: Profile 1: Left Click, Profile 3: Button 5."
        or "" if nothing references this slot. Button mappings reference a
        macro by number (macroN), so clearing/replacing a slot's content
        doesn't update or warn those buttons on its own -- surfaced here so
        that's not a silent surprise."""
        references = self._get_macro_references(slot)
        if not references:
            return ""
        return " Currently mapped to: " + ", ".join(references) + "."

    def _on_clear_macro_clicked(self, _button: Gtk.Button) -> None:
        actions = self._macros.get(self._selected_slot)
        if not actions:
            self._toast_overlay.add_toast(
                Adw.Toast(title=f"Macro {self._selected_slot} is already empty.")
            )
            return

        count_text = f"{len(actions)} action" + ("" if len(actions) == 1 else "s")
        name = self._macro_names.get(self._selected_slot)
        named_part = f' ("{name}")' if name else ""
        self._confirm(
            heading="Clear Macro?",
            body=f"This removes all {count_text} from Macro {self._selected_slot}{named_part} "
            "and clears its name." + self._reference_warning(self._selected_slot)
            + " Nothing on the mouse itself changes until you Apply.",
            confirm_label="Clear",
            on_confirm=self._do_clear_macro,
        )

    def _do_clear_macro(self) -> None:
        self._macros.pop(self._selected_slot, None)
        had_name = self._macro_names.pop(self._selected_slot, None) is not None
        if had_name:
            macro_library.save_slot_names(self._macro_names)
        self._refresh_slot_view()
        self._refresh_sidebar_row(self._selected_slot)
        self._toast_overlay.add_toast(Adw.Toast(title=f"Cleared Macro {self._selected_slot}."))
        self._notify_changed()

    def _on_add_clicked(self, _button) -> None:
        actions = self._macros.setdefault(self._selected_slot, [])
        if len(actions) >= MAX_MACRO_ACTIONS:
            return
        kind, value = self._current_kind(), self._current_value()
        if not is_valid_macro_action(kind, value):
            return  # shouldn't happen -- values come from constrained widgets
        actions.append(MacroAction(kind=kind, value=value))
        self._refresh_action_list()
        self._refresh_sidebar_row(self._selected_slot)
        self._notify_changed()

    def _on_edit_action_clicked(self, index: int) -> None:
        action = self._macros[self._selected_slot][index]
        box, kind_dropdown, key_dropdown, number_spin = _build_kind_value_widgets(initial=action)

        dialog = Adw.AlertDialog(heading="Edit Action")
        dialog.set_extra_child(box)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("save", "Save")
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("save")
        dialog.set_close_response("cancel")

        def on_response(_dialog: Adw.AlertDialog, response: str) -> None:
            if response != "save":
                return
            kind = MACRO_ACTION_KINDS[kind_dropdown.get_selected()]
            value = (
                selected_dropdown_string(key_dropdown)
                if kind in ("down", "up")
                else str(number_spin.get_value_as_int())
            )
            if not is_valid_macro_action(kind, value):
                return  # shouldn't happen -- values come from constrained widgets
            self._macros[self._selected_slot][index] = MacroAction(kind=kind, value=value)
            self._refresh_action_list()
            self._refresh_sidebar_row(self._selected_slot)
            self._notify_changed()

        dialog.connect("response", on_response)
        dialog.present(self)

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
        self._refresh_sidebar_row(self._selected_slot)
        self._notify_changed()

    # -- macro library ---------------------------------------------------

    def _build_library_actions(self) -> Gtk.Widget:
        # Two rows, not one -- a single row of all four buttons requests more
        # width than the main window budgets for the Macros dialog (verified
        # live: "AdwFloatingSheet exceeds AdwBreakpointBin width" once Copy to
        # Slot was added as a 4th button here), and growing the main window
        # every time a button is added to this row doesn't scale.
        container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

        top_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        container.append(top_row)

        save_button = Gtk.Button(label="Save to Library…")
        save_button.connect("clicked", self._on_save_to_library_clicked)
        top_row.append(save_button)

        self._library_popover = Gtk.Popover()
        self._refresh_library_popover()
        load_button = Gtk.MenuButton(label="Load from Library…", popover=self._library_popover)
        top_row.append(load_button)

        bottom_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        container.append(bottom_row)

        copy_button = Gtk.Button(label="Copy to Slot…")
        copy_button.connect("clicked", self._on_copy_to_slot_clicked)
        bottom_row.append(copy_button)

        clear_button = Gtk.Button(label="Clear Macro")
        clear_button.add_css_class("destructive-action")
        clear_button.connect("clicked", self._on_clear_macro_clicked)
        bottom_row.append(clear_button)

        return container

    def _refresh_library_popover(self) -> None:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.set_size_request(260, -1)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        box.set_margin_start(6)
        box.set_margin_end(6)

        if not self._library:
            empty_label = Gtk.Label(label="No saved macros yet", xalign=0)
            empty_label.add_css_class("dim-label")
            box.append(empty_label)
        else:
            for name in sorted(self._library):
                box.append(self._build_library_row(name))

        scrolled = Gtk.ScrolledWindow(max_content_height=280, propagate_natural_height=True)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_child(box)
        self._library_popover.set_child(scrolled)

    def _build_library_row(self, name: str) -> Gtk.Widget:
        count = len(self._library[name])
        count_text = f"{count} action" + ("" if count == 1 else "s")

        label = Gtk.Label(xalign=0, hexpand=True)
        label.set_use_markup(False)  # name can come from a loaded/edited library file
        label.set_wrap(True)
        label.set_label(f"{name}\n{count_text}")

        load_button = Gtk.Button(child=label)
        load_button.add_css_class("flat")
        load_button.set_hexpand(True)
        load_button.connect("clicked", lambda _b, n=name: self._on_load_from_library(n))

        rename_button = Gtk.Button(icon_name="document-edit-symbolic", valign=Gtk.Align.CENTER)
        rename_button.add_css_class("flat")
        rename_button.connect("clicked", lambda _b, n=name: self._on_rename_library_entry_clicked(n))

        delete_button = Gtk.Button(icon_name="user-trash-symbolic", valign=Gtk.Align.CENTER)
        delete_button.add_css_class("flat")
        delete_button.connect("clicked", lambda _b, n=name: self._on_delete_from_library(n))

        row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        row_box.append(load_button)
        row_box.append(rename_button)
        row_box.append(delete_button)
        return row_box

    def _on_rename_library_entry_clicked(self, old_name: str) -> None:
        self._library_popover.popdown()
        dialog = Adw.AlertDialog(heading="Rename Library Entry", body=f"Rename '{old_name}' to:")
        entry = Gtk.Entry(text=old_name)
        dialog.set_extra_child(entry)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("rename", "Rename")
        dialog.set_response_appearance("rename", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("rename")
        dialog.set_close_response("cancel")

        def on_response(_dialog: Adw.AlertDialog, response: str) -> None:
            if response != "rename":
                return
            new_name = entry.get_text().strip()
            if not new_name or new_name == old_name:
                return
            self._do_rename_library_entry(old_name, new_name)

        dialog.connect("response", on_response)
        dialog.present(self)

    def _do_rename_library_entry(self, old_name: str, new_name: str) -> None:
        # A collision with an existing entry silently overwrites it, same as
        # Save to Library already does when you save under a name that's
        # already taken -- consistent, if worth a heads-up in the toast.
        replaced = new_name in self._library
        self._library[new_name] = self._library.pop(old_name)
        macro_library.save_library(self._library)
        self._refresh_library_popover()
        title = f"Renamed '{old_name}' to '{new_name}'."
        if replaced:
            title += f" Replaced the existing '{new_name}'."
        self._toast_overlay.add_toast(Adw.Toast(title=title))

    def _on_load_from_library(self, name: str) -> None:
        self._library_popover.popdown()
        existing = self._macros.get(self._selected_slot)
        if not existing:
            self._do_load_from_library(name)
            return

        count_text = f"{len(existing)} action" + ("" if len(existing) == 1 else "s")
        self._confirm(
            heading="Replace Macro Contents?",
            body=f"Macro {self._selected_slot} currently has {count_text}. "
            f"Loading '{name}' will replace them."
            + self._reference_warning(self._selected_slot)
            + " Nothing on the mouse itself changes until you Apply.",
            confirm_label="Replace",
            on_confirm=lambda: self._do_load_from_library(name),
        )

    def _do_load_from_library(self, name: str) -> None:
        # This DOES touch self._macros/macro_names (unlike save/delete,
        # which only touch the separate library store), so it's the one
        # library action that marks the config dirty.
        self._macros[self._selected_slot] = list(self._library[name])
        self._macro_names[self._selected_slot] = name
        macro_library.save_slot_names(self._macro_names)
        self._refresh_slot_view()
        self._refresh_sidebar_row(self._selected_slot)
        self._toast_overlay.add_toast(
            Adw.Toast(title=f"Loaded '{name}' into Macro {self._selected_slot}.")
        )
        self._notify_changed()

    def _on_copy_to_slot_clicked(self, _button: Gtk.Button) -> None:
        actions = self._macros.get(self._selected_slot, [])
        if not actions:
            self._toast_overlay.add_toast(
                Adw.Toast(title=f"Nothing to copy — Macro {self._selected_slot} is empty.")
            )
            return

        target_slots = [slot for slot in range(1, NUM_MACRO_SLOTS + 1) if slot != self._selected_slot]
        dialog = Adw.AlertDialog(
            heading="Copy to Slot",
            body=f"Copy Macro {self._selected_slot}'s {len(actions)} action"
            + ("" if len(actions) == 1 else "s")
            + " to:",
        )
        dropdown = Gtk.DropDown.new_from_strings([self._slot_title(slot) for slot in target_slots])
        dialog.set_extra_child(dropdown)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("copy", "Copy")
        dialog.set_response_appearance("copy", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("copy")
        dialog.set_close_response("cancel")

        def on_response(_dialog: Adw.AlertDialog, response: str) -> None:
            if response != "copy":
                return
            self._on_copy_target_chosen(target_slots[dropdown.get_selected()])

        dialog.connect("response", on_response)
        dialog.present(self)

    def _on_copy_target_chosen(self, target_slot: int) -> None:
        existing = self._macros.get(target_slot)
        if not existing:
            self._do_copy_to_slot(target_slot)
            return

        count_text = f"{len(existing)} action" + ("" if len(existing) == 1 else "s")
        self._confirm(
            heading="Replace Macro Contents?",
            body=f"Macro {target_slot} currently has {count_text}. "
            f"Copying Macro {self._selected_slot} here will replace them."
            + self._reference_warning(target_slot)
            + " Nothing on the mouse itself changes until you Apply.",
            confirm_label="Replace",
            on_confirm=lambda: self._do_copy_to_slot(target_slot),
        )

    def _do_copy_to_slot(self, target_slot: int) -> None:
        # Only the action list copies over -- the target slot's own name (if
        # any) is left untouched, same as copying content between two already
        # -distinct slots shouldn't silently rename one of them.
        self._macros[target_slot] = list(self._macros.get(self._selected_slot, []))
        self._refresh_sidebar_row(target_slot)
        self._toast_overlay.add_toast(
            Adw.Toast(title=f"Copied Macro {self._selected_slot} to Macro {target_slot}.")
        )
        self._notify_changed()

    def _on_delete_from_library(self, name: str) -> None:
        self._library_popover.popdown()
        count = len(self._library[name])
        count_text = f"{count} action" + ("" if count == 1 else "s")
        self._confirm(
            heading="Delete from Library?",
            body=f"This permanently deletes '{name}' ({count_text}) from your local macro "
            "library. It doesn't affect any macro slot currently on the mouse.",
            confirm_label="Delete",
            on_confirm=lambda: self._do_delete_from_library(name),
        )

    def _do_delete_from_library(self, name: str) -> None:
        self._library.pop(name, None)
        macro_library.save_library(self._library)
        self._refresh_library_popover()
        self._toast_overlay.add_toast(Adw.Toast(title=f"Deleted '{name}' from library."))

    def _on_save_to_library_clicked(self, _button: Gtk.Button) -> None:
        actions = self._macros.get(self._selected_slot, [])
        if not actions:
            self._toast_overlay.add_toast(
                Adw.Toast(title=f"Nothing to save — Macro {self._selected_slot} is empty.")
            )
            return

        dialog = Adw.AlertDialog(
            heading="Save to Library",
            body=f"Save Macro {self._selected_slot}'s {len(actions)} action"
            + ("" if len(actions) == 1 else "s")
            + " to the library under this name:",
        )
        entry = Gtk.Entry(text=self._macro_names.get(self._selected_slot, ""))
        dialog.set_extra_child(entry)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("save", "Save")
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("save")
        dialog.set_close_response("cancel")

        def on_response(_dialog: Adw.AlertDialog, response: str) -> None:
            if response != "save":
                return
            name = entry.get_text().strip()
            if not name:
                return
            self._library[name] = list(actions)
            macro_library.save_library(self._library)
            self._refresh_library_popover()
            self._toast_overlay.add_toast(Adw.Toast(title=f"Saved to library as '{name}'."))

        dialog.connect("response", on_response)
        dialog.present(self)
