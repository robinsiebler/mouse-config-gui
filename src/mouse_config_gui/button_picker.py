"""Categorized "Choose…" picker for button mappings, attached as a suffix on
each ButtonRow (button_group.py). Mirrors the structure of the mouse's
official Windows configurator (Left Click / Right Click / Single Key /
Combo Key / Basic ▸ / Media ▸ / Macro ▸ / Fire Key… / DPI Switch ▸ / ...) so
the common cases can be picked instead of typed from memory.

Every token offered here comes from keymap.grammar_data() -- the same data
keymap.is_valid_button_mapping() validates against -- so the menu can never
hand back something the validator would then reject.
"""

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import GLib, Gtk

from mouse_config_gui.keymap import SNIPE_DPI_VALUES, grammar_data

# "Basic"/"Advanced" aren't grammar categories of their own -- they're a UI
# grouping of the remaining mouse_and_special tokens not already offered as
# their own top-level item (left/right/middle/forward/backward/profile_switch)
# or their own submenu (report_rate+/-). (label, value) pairs since these
# symbols/tokens don't mechanically humanize the way compatibility_*/media_*
# do -- "dpi-cycle" -> "Dpi Cycle" reads worse than a hand-picked label.
_BASIC_ITEMS = [
    ("DPI Up", "dpi+"),
    ("DPI Down", "dpi-"),
    ("Cycle DPI", "dpi-cycle"),
    ("Scroll Up", "scroll_up"),
    ("Scroll Down", "scroll_down"),
    ("Next Profile", "profile+"),
    ("Previous Profile", "profile-"),
    ("Toggle DPI LED", "dpi_led_toggle"),
    ("Reset Settings", "reset_settings"),
    ("Switch LED Mode", "led_mode_switch"),
]
_REPORT_RATE_ITEMS = [
    ("Increase Report Rate", "report_rate+"),
    ("Decrease Report Rate", "report_rate-"),
]

# design_docs/keymap.md's own heading for this category: "Compatibility
# functions (these are only handled by the official software and are mostly
# redundant)". Confirmed empirically: compatibility_select_all does nothing
# on Linux. Both it and the working media_play use the same 0x8e/0x01 report
# prefix, but compatibility_*'s third byte is a vendor-only 0xff sub-code
# only the Windows driver decodes, while media_play's is a real HID
# Consumer-Control usage code Linux understands -- so two better substitutes
# exist for some of these, each swapping in a *different* mapping than the
# literal compatibility_* token:
#   - editing actions -> the actual OS keyboard shortcut (near-universal
#     app-level convention, independent of desktop environment)
#   - browser nav / lock -> the equivalent Media_* keyboard key (keymap_data
#     .yaml's `keys` list), which uses that same real HID code path the
#     working media_play does, instead of compatibility_*'s vendor-only one
# (label, substitute value, source compatibility_* token being replaced)
_ADVANCED_WORKING = [
    ("Cut", "ctrl_l+x", "compatibility_cut"),
    ("Copy", "ctrl_l+c", "compatibility_copy"),
    ("Paste", "ctrl_l+v", "compatibility_paste"),
    ("Select All", "ctrl_l+a", "compatibility_select_all"),
    ("Find", "ctrl_l+f", "compatibility_find"),
    ("New", "ctrl_l+n", "compatibility_new"),
    ("Print", "ctrl_l+p", "compatibility_print"),
    ("Save", "ctrl_l+s", "compatibility_save"),
    ("Browser Back", "Media_Back", "compatibility_browser_backward"),
    ("Browser Forward", "Media_Forward", "compatibility_browser_forward"),
    ("Browser Stop", "Media_Stop", "compatibility_browser_stop"),
    ("Browser Refresh", "Media_Refresh", "compatibility_browser_refresh"),
    ("Lock", "Media_Screenlock", "compatibility_lock_pcme"),
]

# No cross-desktop-environment equivalent exists for these -- Switch Window/
# Close Window/Run/Show Desktop/Open Explorer/Mail/Browser Home/Browser
# Search/Browser Favorite all vary by GNOME/KDE/XFCE/etc. Guessing wrong
# would silently do something *different* than intended (e.g. closing the
# wrong window), which seems worse than an honest no-op -- so these stay a
# literal passthrough of the vendor-only compatibility_* token.
_ADVANCED_LIKELY_INERT = [
    "compatibility_switch_window",
    "compatibility_close_window",
    "compatibility_open_explorer",
    "compatibility_run",
    "compatibility_show_desktop",
    "compatibility_mail",
    "compatibility_browser_home",
    "compatibility_browser_search",
    "compatibility_browser_favorite",
]

_ADVANCED_CAVEAT = (
    "Below: only interpreted by the official Windows software -- likely no "
    "effect when applied via mouse_m908 on Linux."
)


def _modifier_label(modifier: str) -> str:
    base, side = modifier.rsplit("_", 1)
    return f"{base.capitalize()} ({side.upper()})"


def _humanize_token(token: str, *, strip_prefix: str) -> str:
    """"compatibility_open_explorer" -> "Open Explorer", "media_volume_up" -> "Volume Up"."""
    return token.removeprefix(strip_prefix).replace("_", " ").title()


def _row_button(label: str, *, expand_child: Gtk.Widget | None = None, dim: bool = False) -> Gtk.Button:
    """A flat, left-aligned, full-width button used for every picker row.

    dim: render the label in the theme's error/destructive red, for options
    that are unlikely to actually do anything (see _ADVANCED_LIKELY_INERT).
    Styled on the Label, not the Button, so it reads as "muted text" rather
    than a big red "destructive-action" button background.
    """
    if expand_child is not None:
        child = expand_child
    else:
        child = Gtk.Label(xalign=0)
        if dim:
            child.set_markup(f'<span foreground="#e01b24">{GLib.markup_escape_text(label)}</span>')
        else:
            child.set_label(label)
    button = Gtk.Button(child=child)
    button.add_css_class("flat")
    button.set_hexpand(True)
    return button


def _leaf_button(label: str, value: str, on_pick, tooltip: str | None = None, *, dim: bool = False) -> Gtk.Button:
    button = _row_button(label, dim=dim)
    if tooltip:
        button.set_tooltip_text(tooltip)
    button.connect("clicked", lambda _b: on_pick(value))
    return button


def _submenu_button(label: str, popover: Gtk.Popover) -> Gtk.MenuButton:
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    box.append(Gtk.Label(label=label, xalign=0, hexpand=True))
    box.append(Gtk.Image.new_from_icon_name("go-next-symbolic"))
    button = Gtk.MenuButton(child=box, popover=popover)
    button.add_css_class("flat")
    # GtkMenuButton resets its popover's position to BOTTOM the moment the
    # popover is assigned (verified: popover.set_position() before this point
    # gets silently clobbered) -- `direction` is the property it actually
    # honors, and it maps ArrowType.RIGHT to a rightward flyout, auto-flipping
    # to the left on its own if there isn't room.
    button.set_direction(Gtk.ArrowType.RIGHT)
    return button


def _scrolled(child: Gtk.Widget) -> Gtk.ScrolledWindow:
    scrolled = Gtk.ScrolledWindow(max_content_height=280, propagate_natural_height=True)
    scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scrolled.set_child(child)
    return scrolled


def _menu_box() -> Gtk.Box:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    box.set_size_request(220, -1)
    box.set_margin_top(6)
    box.set_margin_bottom(6)
    box.set_margin_start(6)
    box.set_margin_end(6)
    return box


def _form_box() -> Gtk.Box:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    box.set_size_request(220, -1)
    box.set_margin_top(10)
    box.set_margin_bottom(10)
    box.set_margin_start(10)
    box.set_margin_end(10)
    return box


def searchable_key_dropdown() -> Gtk.DropDown:
    dropdown = Gtk.DropDown.new_from_strings(sorted(grammar_data()["keys"]))
    dropdown.set_enable_search(True)
    dropdown.set_expression(Gtk.PropertyExpression.new(Gtk.StringObject, None, "string"))
    return dropdown


def selected_dropdown_string(dropdown: Gtk.DropDown) -> str:
    item = dropdown.get_selected_item()
    return item.get_string() if item is not None else ""


def _list_box(items: list[tuple[str, str]], on_pick, *, show_value_tooltip: bool = False) -> Gtk.Widget:
    """items: list of (label, value) pairs; clicking a row picks its value.

    show_value_tooltip: when the label is a friendly rewrite of the value
    (e.g. "Open Explorer" for "compatibility_open_explorer"), show the raw
    token on hover so it's still discoverable.
    """
    box = _menu_box()
    for label, value in items:
        tooltip = value if show_value_tooltip and label != value else None
        box.append(_leaf_button(label, value, on_pick, tooltip=tooltip))
    return box


def _list_popover(items: list[tuple[str, str]], on_pick, *, show_value_tooltip: bool = False) -> Gtk.Popover:
    return Gtk.Popover(child=_scrolled(_list_box(items, on_pick, show_value_tooltip=show_value_tooltip)))


def _advanced_popover(on_pick) -> Gtk.Popover:
    """Working substitutes on top, a divider + caveat, then the remaining
    compatibility_* tokens (dimmed red -- see _ADVANCED_LIKELY_INERT)."""
    compatibility_tokens = set(grammar_data()["compatibility"])
    covered = {source for _, _, source in _ADVANCED_WORKING} | set(_ADVANCED_LIKELY_INERT)
    assert covered == compatibility_tokens, (
        "Advanced menu is out of sync with keymap_data.yaml's compatibility list -- "
        f"missing={compatibility_tokens - covered} extra={covered - compatibility_tokens}"
    )

    box = _menu_box()
    for label, value, _source in _ADVANCED_WORKING:
        box.append(_leaf_button(label, value, on_pick))

    box.append(Gtk.Separator())
    note = Gtk.Label(label=_ADVANCED_CAVEAT, wrap=True, xalign=0, max_width_chars=28)
    note.add_css_class("dim-label")
    note.add_css_class("caption")
    box.append(note)

    for token in _ADVANCED_LIKELY_INERT:
        label = _humanize_token(token, strip_prefix="compatibility_")
        box.append(_leaf_button(label, token, on_pick, tooltip=token, dim=True))

    return Gtk.Popover(child=_scrolled(box))


def _single_key_popover(on_pick) -> Gtk.Popover:
    box = _form_box()
    dropdown = searchable_key_dropdown()
    box.append(dropdown)
    insert = Gtk.Button(label="Insert")
    insert.add_css_class("suggested-action")
    insert.connect("clicked", lambda _b: on_pick(selected_dropdown_string(dropdown)))
    box.append(insert)
    return Gtk.Popover(child=box)


def _combo_key_popover(on_pick) -> Gtk.Popover:
    box = _form_box()
    modifiers = grammar_data()["modifiers"]
    checks = {}
    for modifier in modifiers:
        check = Gtk.CheckButton(label=_modifier_label(modifier))
        checks[modifier] = check
        box.append(check)

    dropdown = searchable_key_dropdown()
    box.append(dropdown)

    def on_insert(_button):
        selected_modifiers = [m for m in modifiers if checks[m].get_active()]
        key = selected_dropdown_string(dropdown)
        on_pick("+".join([*selected_modifiers, key]))

    insert = Gtk.Button(label="Insert")
    insert.add_css_class("suggested-action")
    insert.connect("clicked", on_insert)
    box.append(insert)
    return Gtk.Popover(child=box)


def _fire_key_popover(on_pick) -> Gtk.Popover:
    box = _form_box()

    button_dropdown = Gtk.DropDown.new_from_strings(["Left Click", "Right Click", "Middle Button"])
    button_values = ["mouse_left", "mouse_right", "mouse_middle"]
    box.append(button_dropdown)

    repeats_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    repeats_row.append(Gtk.Label(label="Repeats", hexpand=True, xalign=0))
    repeats_spin = Gtk.SpinButton.new_with_range(0, 255, 1)
    repeats_spin.set_value(5)
    repeats_row.append(repeats_spin)
    box.append(repeats_row)

    delay_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    delay_row.append(Gtk.Label(label="Delay", hexpand=True, xalign=0))
    delay_spin = Gtk.SpinButton.new_with_range(0, 255, 1)
    delay_spin.set_value(1)
    delay_row.append(delay_spin)
    box.append(delay_row)

    def on_insert(_button):
        button_value = button_values[button_dropdown.get_selected()]
        mapping = f"fire:{button_value}:{repeats_spin.get_value_as_int()}:{delay_spin.get_value_as_int()}"
        on_pick(mapping)

    insert = Gtk.Button(label="Insert")
    insert.add_css_class("suggested-action")
    insert.connect("clicked", on_insert)
    box.append(insert)
    return Gtk.Popover(child=box)


def _macro_items(macro_names: dict[int, str], num_macro_slots: int) -> list[tuple[str, str]]:
    return [
        (f"{macro_names[n]} (Macro {n})" if macro_names.get(n) else f"Macro {n}", f"macro{n}")
        for n in range(1, num_macro_slots + 1)
    ]


def build_picker_button(on_pick, num_macro_slots: int, macro_names: dict[int, str]) -> Gtk.MenuButton:
    """A "Choose…" button whose popover offers every mapping category,
    calling on_pick(value) and collapsing the whole menu when a value is
    picked (single- or multi-level).

    macro_names: the same live dict MainWindow/MacroEditorDialog mutate in
    place -- captured once here at ButtonRow-construction time, so the Macro
    submenu is rebuilt from current names each time the root popover opens
    (see refresh_macro_submenu below) rather than frozen at whatever names
    existed when this button was first built.
    """
    data = grammar_data()
    root_popover = Gtk.Popover()

    def pick(value: str) -> None:
        on_pick(value)
        root_popover.popdown()

    root_box = _menu_box()
    root_box.append(_leaf_button("Left Click", "left", pick))
    root_box.append(_leaf_button("Right Click", "right", pick))
    root_box.append(_leaf_button("Middle Button", "middle", pick))
    root_box.append(_leaf_button("Forward", "forward", pick))
    root_box.append(_leaf_button("Backward", "backward", pick))
    root_box.append(Gtk.Separator())
    root_box.append(_submenu_button("Single Key", _single_key_popover(pick)))
    root_box.append(_submenu_button("Combo Key", _combo_key_popover(pick)))
    root_box.append(Gtk.Separator())
    root_box.append(_submenu_button("Basic", _list_popover(_BASIC_ITEMS, pick, show_value_tooltip=True)))
    advanced_button = _submenu_button("Advanced", _advanced_popover(pick))
    advanced_button.set_tooltip_text(_ADVANCED_CAVEAT)
    root_box.append(advanced_button)
    root_box.append(_submenu_button(
        "Media",
        _list_popover(
            [(_humanize_token(t, strip_prefix="media_"), t) for t in data["media"]],
            pick,
            show_value_tooltip=True,
        ),
    ))
    macro_popover = Gtk.Popover()

    def refresh_macro_submenu(*_args) -> None:
        items = _macro_items(macro_names, num_macro_slots)
        macro_popover.set_child(_scrolled(_list_box(items, pick, show_value_tooltip=True)))

    refresh_macro_submenu()
    # Rebuilt every time the root menu opens, not just once at construction,
    # so a name typed in the Macro editor shows up here without needing to
    # rebuild this whole picker (e.g. by switching models and back).
    root_popover.connect("show", refresh_macro_submenu)
    root_box.append(_submenu_button("Macro", macro_popover))
    root_box.append(_submenu_button("Fire Key…", _fire_key_popover(pick)))
    root_box.append(_submenu_button(
        "DPI Switch",
        _list_popover([(f"{dpi} DPI", f"snipe:{dpi}") for dpi in SNIPE_DPI_VALUES], pick),
    ))
    root_box.append(Gtk.Separator())
    root_box.append(_leaf_button("Profile Switch", "profile_switch", pick))
    root_box.append(_submenu_button(
        "Report Rate", _list_popover(_REPORT_RATE_ITEMS, pick, show_value_tooltip=True)
    ))
    root_box.append(Gtk.Separator())
    root_box.append(_leaf_button("Disable", "none", pick))

    root_popover.set_child(_scrolled(root_box))

    picker_button = Gtk.MenuButton(icon_name="view-list-symbolic", popover=root_popover)
    picker_button.set_tooltip_text("Choose a mapping…")
    picker_button.set_valign(Gtk.Align.CENTER)
    return picker_button
