import os
import re
import tempfile
import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from mouse_config_gui import capability, device_cli, ini_io, macro_library
from mouse_config_gui.button_group import ButtonGroup
from mouse_config_gui.dpi_group import DpiGroup, NUM_DPI_SLOTS
from mouse_config_gui.ini_io import NUM_PROFILES
from mouse_config_gui.keymap import is_valid_macro_action
from mouse_config_gui.led_group import LedGroup
from mouse_config_gui.macro_editor import MacroEditorDialog
from mouse_config_gui.models import DpiSlot, MacroAction, MouseConfig, ProfileConfig
from mouse_config_gui.performance_group import PerformanceGroup

_DEFAULT_SWATCH_COLOR = "9a9996"  # neutral gray until a profile's real LED color is loaded


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_title("Mouse Configurator")
        # Wide enough that the Macros dialog (content_width=960) doesn't get
        # clipped -- Adw.Dialog is constrained to fit inside its parent
        # window, not just its own content_width; verified the macro editor
        # needs ~665px minimum before an AdwFloatingSheet width warning and
        # visible clipping kick in.
        self.set_default_size(900, 760)

        self._loaded_config: MouseConfig | None = None
        self._current_file_path: Path | None = None
        self._dirty = False
        # Shared across all 5 profiles (MouseConfig-level, not per-profile,
        # unlike LED/DPI/Buttons) -- mutated in place by MacroEditorDialog.
        self._macros: dict[int, list[MacroAction]] = {}
        self._macro_names: dict[int, str] = {}

        self.profile_stack = Adw.ViewStack()
        self._swatch_provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            self._swatch_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )
        self._swatch_colors = {i: _DEFAULT_SWATCH_COLOR for i in range(1, NUM_PROFILES + 1)}
        self._update_swatch_css()

        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(self._build_header_bar())
        toolbar_view.add_top_bar(self._build_actions_row())
        toolbar_view.add_top_bar(self._build_profile_switcher())
        toolbar_view.set_content(self.profile_stack)

        self.toast_overlay = Adw.ToastOverlay()
        self.toast_overlay.set_child(toolbar_view)
        self.set_content(self.toast_overlay)

        if self._detected_model is not None:
            GLib.idle_add(self._do_initial_read)

    def _do_initial_read(self) -> bool:
        self._do_read()
        return GLib.SOURCE_REMOVE

    def _build_header_bar(self) -> Adw.HeaderBar:
        """Title row: the window title (shown centered by default), the
        window controls, and a file menu (Open/Save config) -- the model
        dropdown and mouse action buttons live on their own row below (see
        _build_actions_row) so they don't squeeze the title down to an
        ellipsized "Mouse Configurat..."."""
        header_bar = Adw.HeaderBar()

        self._setup_file_actions()
        menu = Gio.Menu()
        menu.append("Open Config File…", "win.open-config")
        menu.append("Save Config File", "win.save-config")
        menu.append("Save Config File As…", "win.save-config-as")
        menu_button = Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu)
        menu_button.set_tooltip_text("Config file")
        header_bar.pack_end(menu_button)

        # pack_start (opposite side from the file menu) so this doesn't disturb
        # _build_actions_row()'s existing 3-widget/2-spacer symmetry below.
        macros_button = Gtk.Button(label="Macros…")
        macros_button.set_tooltip_text("Edit the shared 15-slot macro store")
        macros_button.connect("clicked", self._on_macros_clicked)
        header_bar.pack_start(macros_button)

        return header_bar

    def _on_macros_clicked(self, _button: Gtk.Button) -> None:
        dialog = MacroEditorDialog(
            self._macros,
            self._macro_names,
            self._find_macro_references,
            on_changed=self._mark_dirty,
        )
        dialog.present(self)

    def _find_macro_references(self, macro_slot: int) -> list[str]:
        """Human-readable "Profile N: Button" locations currently mapped to
        macro_slot (macroN / macroN:repeats / macroN:while / macroN:until),
        across all 5 profiles -- so the macro editor can warn before
        clearing/replacing a slot out from under a button mapping that still
        points at it by number."""
        pattern = re.compile(rf"^macro{macro_slot}(?::.*)?$")
        references = []
        for profile_num, button_group in self.button_groups.items():
            for button_name, value in button_group.mappings.items():
                if pattern.match(value):
                    row = button_group.rows.get(button_name)
                    label = row.get_title() if row is not None else button_name
                    references.append(f"Profile {profile_num}: {label}")
        return references

    def _setup_file_actions(self) -> None:
        open_action = Gio.SimpleAction.new("open-config", None)
        open_action.connect("activate", self._on_open_config)
        self.add_action(open_action)

        save_action = Gio.SimpleAction.new("save-config", None)
        save_action.connect("activate", self._on_save_config)
        self.add_action(save_action)

        save_as_action = Gio.SimpleAction.new("save-config-as", None)
        save_as_action.connect("activate", self._on_save_config_as)
        self.add_action(save_as_action)

    @staticmethod
    def _ini_file_filters() -> Gio.ListStore:
        ini_filter = Gtk.FileFilter()
        ini_filter.set_name("INI config files")
        ini_filter.add_pattern("*.ini")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(ini_filter)
        return filters

    def _on_open_config(self, _action: Gio.SimpleAction, _param) -> None:
        if self._dirty:
            self._confirm_overwrite(self._prompt_open_config)
        else:
            self._prompt_open_config()

    def _prompt_open_config(self) -> None:
        dialog = Gtk.FileDialog(title="Open Config File", filters=self._ini_file_filters())
        dialog.open(self, None, self._on_open_config_finished)

    def _on_open_config_finished(self, dialog: Gtk.FileDialog, result: Gio.AsyncResult) -> None:
        try:
            file = dialog.open_finish(result)
        except GLib.Error:
            return  # user cancelled, or the portal reported an error -- nothing to do either way

        path = Path(file.get_path())
        try:
            config = ini_io.load(path)
        except Exception as exc:  # noqa: BLE001 -- surfaced to the user via Toast
            self._show_toast(self._error_message(exc))
            return

        self._current_file_path = path

        # A loaded file may have been written for a different model than
        # whatever's currently selected. Switch the dropdown to match *before*
        # populating widgets, so LED/DPI validation (lightmode list, DPI step
        # values, scrollspeed visibility, etc.) is scoped to the model the
        # data actually belongs to -- not silently checked against the wrong
        # one, which could pass by coincidence or reject a genuinely valid value.
        model_note = ""
        matching_stem = (
            capability.find_capability_by_model_name(config.model)
            if config.model is not None
            else None
        )
        if matching_stem is not None:
            self.model_dropdown.set_selected(self.model_names.index(matching_stem))
            model_note = f" (switched model to {matching_stem})"
        elif config.model is not None:
            model_note = f" (unrecognized model {config.model!r} -- kept current model selection)"

        self._populate_from_config(config)
        self._show_toast(f"Loaded {path.name}.{model_note}")

    def _on_save_config(self, _action: Gio.SimpleAction, _param) -> None:
        if self._current_file_path is not None:
            self._save_to_path(self._current_file_path)
        else:
            self._prompt_save_config()

    def _on_save_config_as(self, _action: Gio.SimpleAction, _param) -> None:
        self._prompt_save_config()

    def _prompt_save_config(self) -> None:
        dialog = Gtk.FileDialog(
            title="Save Config File", filters=self._ini_file_filters(), initial_name="config.ini"
        )
        dialog.save(self, None, self._on_save_config_finished)

    def _on_save_config_finished(self, dialog: Gtk.FileDialog, result: Gio.AsyncResult) -> None:
        try:
            file = dialog.save_finish(result)
        except GLib.Error:
            return  # user cancelled, or the portal reported an error -- nothing to do either way

        self._current_file_path = Path(file.get_path())
        self._save_to_path(self._current_file_path)

    def _save_to_path(self, path: Path) -> None:
        config = self._collect_config()
        try:
            ini_io.save(config, path)
        except Exception as exc:  # noqa: BLE001 -- surfaced to the user via Toast
            self._show_toast(self._error_message(exc))
            return

        self._loaded_config = config
        self._dirty = False
        self._show_toast(f"Saved {path.name}.")

    def _build_actions_row(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.set_margin_top(6)
        box.set_margin_bottom(6)

        self.model_names = capability.list_capabilities()
        self.model_dropdown = Gtk.DropDown.new_from_strings(self.model_names)
        self.model_dropdown.set_tooltip_text("Mouse model")
        # Without a fixed width, the button resizes to fit whichever model name
        # is currently selected -- pin it to the widest name (e.g. "m990chroma")
        # plus room for the dropdown arrow/padding so it stays a constant size.
        widest_name = max(self.model_names, key=len)
        text_width = self.model_dropdown.create_pango_layout(widest_name).get_pixel_size()[0]
        self.model_dropdown.set_size_request(text_width + 48, -1)
        detected = device_cli.detect_model()
        self._detected_model = detected  # used by __init__ to decide whether to auto-read on launch
        if detected in self.model_names:
            self.model_dropdown.set_selected(self.model_names.index(detected))
        self.model_dropdown.connect("notify::selected", self._on_model_changed)
        box.append(self.model_dropdown)

        # Equal-width expanding spacers on both sides of "Read from Mouse" give
        # even gaps between all three widgets, rather than bunching the two
        # buttons together at the end.
        box.append(Gtk.Box(hexpand=True))

        self.read_button = Gtk.Button(label="Read from Mouse")
        self.read_button.connect("clicked", self._on_read_clicked)
        box.append(self.read_button)

        box.append(Gtk.Box(hexpand=True))

        self.apply_button = Gtk.Button(label="Apply to Mouse")
        self.apply_button.add_css_class("suggested-action")
        self.apply_button.connect("clicked", self._on_apply_clicked)
        box.append(self.apply_button)

        return box

    def _current_capability(self) -> capability.Capability:
        name = self.model_names[self.model_dropdown.get_selected()]
        return capability.load_capability(name)

    def _on_model_changed(self, dropdown: Gtk.DropDown, _pspec) -> None:
        cap = self._current_capability()
        for led_group in self.led_groups.values():
            led_group.apply_capability(cap)
        for performance_group in self.performance_groups.values():
            performance_group.apply_capability(cap)
        for dpi_group in self.dpi_groups.values():
            dpi_group.apply_capability(cap)
        for button_group in self.button_groups.values():
            button_group.apply_capability(cap)

    def _build_profile_switcher(self) -> Gtk.Widget:
        """5 fixed profile tabs, each with a color swatch tinted to that
        profile's LED color (design doc §5) -- swatches start neutral gray
        and are updated via set_profile_color() once a config is loaded."""
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        box.add_css_class("linked")
        box.set_halign(Gtk.Align.CENTER)
        box.set_margin_top(6)
        box.set_margin_bottom(6)

        initial_capability = self._current_capability()
        self.led_groups: dict[int, LedGroup] = {}
        self.performance_groups: dict[int, PerformanceGroup] = {}
        self.dpi_groups: dict[int, DpiGroup] = {}
        self.button_groups: dict[int, ButtonGroup] = {}
        self._swatches: dict[int, Gtk.Widget] = {}
        self._profile_buttons: dict[int, Gtk.ToggleButton] = {}
        first_button: Gtk.ToggleButton | None = None

        for num in range(1, NUM_PROFILES + 1):
            page_name = f"profile{num}"
            led_group = LedGroup(initial_capability, on_changed=self._mark_dirty)
            self.led_groups[num] = led_group
            performance_group = PerformanceGroup(initial_capability, on_changed=self._mark_dirty)
            self.performance_groups[num] = performance_group
            dpi_group = DpiGroup(initial_capability, on_changed=self._mark_dirty)
            self.dpi_groups[num] = dpi_group
            button_group = ButtonGroup(initial_capability, self._macro_names, on_changed=self._mark_dirty)
            self.button_groups[num] = button_group

            page = Adw.PreferencesPage()
            page.add(led_group)
            page.add(performance_group)
            page.add(dpi_group)
            page.add(button_group)
            self.profile_stack.add_titled(page, page_name, f"Profile {num}")

            swatch = Gtk.Box(width_request=12, height_request=12)
            swatch.add_css_class("profile-swatch")
            swatch.add_css_class(f"profile-swatch-{num}")
            self._swatches[num] = swatch

            content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            content.append(swatch)
            content.append(Gtk.Label(label=f"Profile {num}"))

            button = Gtk.ToggleButton(child=content)
            if first_button is not None:
                button.set_group(first_button)
            else:
                first_button = button
            button.connect("toggled", self._on_profile_button_toggled, page_name)
            box.append(button)
            self._profile_buttons[num] = button

        if first_button is not None:
            first_button.set_active(True)

        return box

    def _on_profile_button_toggled(self, button: Gtk.ToggleButton, page_name: str) -> None:
        if button.get_active():
            self.profile_stack.set_visible_child_name(page_name)

    def set_profile_color(self, profile_num: int, hex_color: str) -> None:
        """Tint the given profile's tab swatch. hex_color is 6-hex RRGGBB, no '#'."""
        self._swatch_colors[profile_num] = hex_color
        self._update_swatch_css()

    def _update_swatch_css(self) -> None:
        css = "\n".join(
            f".profile-swatch-{num} {{ background-color: #{color}; border-radius: 3px; }}"
            for num, color in self._swatch_colors.items()
        )
        self._swatch_provider.load_from_string(css)

    # -- dirty tracking / toasts -------------------------------------------------

    def _mark_dirty(self) -> None:
        self._dirty = True

    def _show_toast(self, text: str) -> None:
        self.toast_overlay.add_toast(Adw.Toast(title=text))

    @staticmethod
    def _error_message(exc: Exception) -> str:
        # CLI error messages can be multi-line ("Couldn't open mouse.\n- Check
        # hardware and permissions..."); a Toast is single-line, so surface just
        # the actionable headline.
        return str(exc).splitlines()[0] if str(exc) else type(exc).__name__

    # -- UI <-> MouseConfig ------------------------------------------------------

    def _collect_config(self) -> MouseConfig:
        """Read all 5 profiles' widget state, plus the shared macro store,
        into a MouseConfig."""
        base = self._loaded_config if self._loaded_config is not None else MouseConfig()
        config = MouseConfig(
            model=self._current_capability().model,
            active_profile=base.active_profile,
            macros=dict(self._macros),
            macro_names=dict(self._macro_names),
        )

        for num in range(1, NUM_PROFILES + 1):
            led = self.led_groups[num]
            perf = self.performance_groups[num]
            dpi = self.dpi_groups[num]
            buttons = self.button_groups[num]
            base_profile = base.profiles[num - 1] if len(base.profiles) >= num else ProfileConfig()

            config.profiles.append(
                ProfileConfig(
                    lightmode=led.lightmode,
                    color=led.color,
                    brightness=led.brightness,
                    speed=led.speed,
                    scrollspeed=led.scrollspeed,
                    report_rate=perf.report_rate,
                    dpi_slots=[
                        DpiSlot(enabled=dpi.rows[slot].enabled, value=dpi.rows[slot].value)
                        for slot in range(1, NUM_DPI_SLOTS + 1)
                    ],
                    active_dpi_slot=base_profile.active_dpi_slot,
                    buttons=dict(buttons.mappings),
                )
            )

        return config

    def _populate_from_config(self, config: MouseConfig) -> None:
        self._loaded_config = config
        self._macros = dict(config.macros)
        # Mutate in place, don't rebind -- ButtonGroup/ButtonRow's macro
        # picker (button_picker.py) captured this exact dict object once at
        # construction time so renamed macros show up live; rebinding here
        # would orphan that reference and freeze it at whatever names
        # existed the first time a profile page was built.
        self._macro_names.clear()
        self._macro_names.update(config.macro_names)

        # mouse_m908 -R always returns fresh device state with no name data
        # (nowhere on the mouse to store one), so a plain "Read from Mouse"
        # -- including the automatic one on launch -- would otherwise wipe
        # every name on every read. Fall back to the locally-remembered name
        # for any slot that still has content but wasn't explicitly named by
        # what was just loaded (an explicit "# Macro N name:" from a loaded
        # .ini file still wins over the remembered one).
        remembered_names = macro_library.load_slot_names()
        for slot, name in remembered_names.items():
            if slot not in self._macro_names and self._macros.get(slot):
                self._macro_names[slot] = name

        for num in range(1, NUM_PROFILES + 1):
            profile = config.profiles[num - 1] if len(config.profiles) >= num else ProfileConfig()
            led = self.led_groups[num]
            perf = self.performance_groups[num]
            dpi = self.dpi_groups[num]
            self.button_groups[num].set_mappings(profile.buttons)

            if profile.lightmode is not None:
                try:
                    led.lightmode = profile.lightmode
                except ValueError:
                    pass  # not valid for the currently selected model -- leave the default
            if profile.color is not None:
                led.color = profile.color
                self.set_profile_color(num, profile.color)
            if profile.brightness is not None:
                led.brightness = profile.brightness
            if profile.speed is not None:
                led.speed = profile.speed
            if profile.scrollspeed is not None:
                led.scrollspeed = profile.scrollspeed
            if profile.report_rate is not None:
                try:
                    perf.report_rate = profile.report_rate
                except ValueError:
                    pass

            for slot_num in range(1, NUM_DPI_SLOTS + 1):
                if slot_num <= len(profile.dpi_slots):
                    slot = profile.dpi_slots[slot_num - 1]
                    dpi.rows[slot_num].enabled = slot.enabled
                    dpi.rows[slot_num].value = slot.value

        self._dirty = False

    # -- async CLI calls -----------------------------------------------------

    def _set_actions_sensitive(self, sensitive: bool) -> None:
        self.apply_button.set_sensitive(sensitive)
        self.read_button.set_sensitive(sensitive)

    def _run_async(self, work_fn, on_success, on_error) -> None:
        def worker():
            try:
                result = work_fn()
            except Exception as exc:  # noqa: BLE001 -- surfaced to the user via Toast
                GLib.idle_add(on_error, exc)
            else:
                GLib.idle_add(on_success, result)

        threading.Thread(target=worker, daemon=True).start()

    def _find_invalid_dpi_rows(self) -> list[tuple[int, int]]:
        return [
            (profile_num, slot_num)
            for profile_num, dpi_group in self.dpi_groups.items()
            for slot_num, row in dpi_group.rows.items()
            if not row.is_valid
        ]

    def _find_invalid_button_rows(self) -> list[tuple[int, str]]:
        return [
            (profile_num, name)
            for profile_num, button_group in self.button_groups.items()
            for name in button_group.invalid_names
        ]

    def _find_invalid_macro_slots(self) -> list[int]:
        # Unlike DPI/button rows, macro actions aren't all editor-validated
        # on the way in -- a loaded file's macro data goes straight into
        # self._macros without passing through is_valid_macro_action() until
        # someone opens that slot in the editor. Re-check everything here so
        # a slot nobody ever opened can't reach mouse_m908 unvalidated.
        return sorted(
            {
                slot
                for slot, actions in self._macros.items()
                for action in actions
                if not is_valid_macro_action(action.kind, action.value)
            }
        )

    def _show_invalid_dpi_toast(self, invalid: list[tuple[int, int]]) -> None:
        # mouse_m908 doesn't error out on a bad DPI value -- it just prints a
        # warning to stderr and silently skips that slot, and our own
        # apply_config() only inspects stderr on a non-zero exit code. Left
        # unchecked, hitting Apply with red DPI fields would look successful
        # while quietly not writing some of what's on screen.
        # Group by profile ("Profile 1: DPI 1, 2, 3") instead of a flat
        # "Profile 1 DPI 1, Profile 1 DPI 2, ..." list -- much shorter for the
        # common case of several bad slots in the same profile, and every
        # location is still named rather than truncated with "N more".
        by_profile: dict[int, list[int]] = {}
        for profile_num, slot_num in invalid:
            by_profile.setdefault(profile_num, []).append(slot_num)
        location_text = "; ".join(
            f"Profile {p}: DPI {', '.join(str(s) for s in slots)}"
            for p, slots in sorted(by_profile.items())
        )

        # Adw.Toast's plain `title` is a single-line, ellipsized label -- a
        # message this long just gets truncated. `custom-title` accepts any
        # widget, so use a wrapping Gtk.Label instead. The toast bubble has no
        # inherent max-width of its own -- without max_width_chars, the label's
        # unwrapped natural width wins and the bubble can grow past the window
        # edge, so this cap is load-bearing, not optional; it's tuned to land
        # around 2 lines for a typical one-profile message.
        label = Gtk.Label(label=f"Fix invalid DPI values before applying — {location_text}")
        label.set_wrap(True)
        label.set_max_width_chars(36)
        label.set_xalign(0)

        toast = Adw.Toast()
        toast.set_custom_title(label)
        toast.set_button_label("Go to Profile")
        first_profile = invalid[0][0]
        toast.connect(
            "button-clicked", lambda _t: self._profile_buttons[first_profile].set_active(True)
        )
        self.toast_overlay.add_toast(toast)

    def _show_invalid_button_toast(self, invalid: list[tuple[int, str]]) -> None:
        by_profile: dict[int, list[str]] = {}
        for profile_num, name in invalid:
            by_profile.setdefault(profile_num, []).append(
                self.button_groups[profile_num].rows[name].get_title()
            )
        location_text = "; ".join(
            f"Profile {p}: {', '.join(names)}" for p, names in sorted(by_profile.items())
        )

        label = Gtk.Label(label=f"Fix invalid button mappings before applying — {location_text}")
        label.set_wrap(True)
        label.set_max_width_chars(36)
        label.set_xalign(0)

        toast = Adw.Toast()
        toast.set_custom_title(label)
        toast.set_button_label("Go to Profile")
        first_profile = invalid[0][0]
        toast.connect(
            "button-clicked", lambda _t: self._profile_buttons[first_profile].set_active(True)
        )
        self.toast_overlay.add_toast(toast)

    def _show_invalid_macro_toast(self, invalid_slots: list[int]) -> None:
        location_text = ", ".join(f"Macro {slot}" for slot in invalid_slots)

        label = Gtk.Label(label=f"Fix invalid macro actions before applying — {location_text}")
        label.set_wrap(True)
        label.set_max_width_chars(36)
        label.set_xalign(0)

        toast = Adw.Toast()
        toast.set_custom_title(label)
        toast.set_button_label("Open Macros")
        toast.connect("button-clicked", lambda _t: self._on_macros_clicked(None))
        self.toast_overlay.add_toast(toast)

    def _on_apply_clicked(self, _button: Gtk.Button) -> None:
        invalid_dpi = self._find_invalid_dpi_rows()
        if invalid_dpi:
            self._show_invalid_dpi_toast(invalid_dpi)
            return

        invalid_buttons = self._find_invalid_button_rows()
        if invalid_buttons:
            self._show_invalid_button_toast(invalid_buttons)
            return

        invalid_macro_slots = self._find_invalid_macro_slots()
        if invalid_macro_slots:
            self._show_invalid_macro_toast(invalid_macro_slots)
            return

        config = self._collect_config()
        model = self._current_capability().model

        fd, tmp_name = tempfile.mkstemp(suffix=".ini", prefix="mouse-config-gui-apply-")
        os.close(fd)
        tmp_path = Path(tmp_name)
        ini_io.save(config, tmp_path)

        self._set_actions_sensitive(False)

        def work():
            try:
                device_cli.apply_config(tmp_path, model=model)
                # -c never touches macros -- separate transfer, same file
                # (already contains the ;## macroN blocks ini_io.save() wrote).
                device_cli.apply_macros(tmp_path, model=model)
            finally:
                tmp_path.unlink(missing_ok=True)

        def on_success(_result) -> None:
            self._set_actions_sensitive(True)
            self._loaded_config = config
            self._dirty = False
            self._show_toast("Applied to mouse.")

        def on_error(exc: Exception) -> None:
            self._set_actions_sensitive(True)
            self._show_toast(self._error_message(exc))

        self._run_async(work, on_success, on_error)

    def _on_read_clicked(self, _button: Gtk.Button) -> None:
        if self._dirty:
            self._confirm_overwrite(self._do_read)
        else:
            self._do_read()

    def _confirm_overwrite(self, action) -> None:
        dialog = Adw.AlertDialog(
            heading="Overwrite unapplied changes?",
            body="Reading from the mouse will discard edits you haven't applied yet.",
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("overwrite", "Overwrite")
        dialog.set_response_appearance("overwrite", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")

        def on_response(_dialog: Adw.AlertDialog, response: str) -> None:
            if response == "overwrite":
                action()

        dialog.connect("response", on_response)
        dialog.present(self)

    def _do_read(self) -> None:
        model = self._current_capability().model

        fd, tmp_name = tempfile.mkstemp(suffix=".ini", prefix="mouse-config-gui-read-")
        os.close(fd)
        tmp_path = Path(tmp_name)

        self._set_actions_sensitive(False)

        def work() -> MouseConfig:
            try:
                device_cli.read_config(tmp_path, model=model)
                return ini_io.load(tmp_path)
            finally:
                tmp_path.unlink(missing_ok=True)

        def on_success(config: MouseConfig) -> None:
            self._set_actions_sensitive(True)
            self._populate_from_config(config)
            self._show_toast("Read from mouse.")

        def on_error(exc: Exception) -> None:
            self._set_actions_sensitive(True)
            self._show_toast(self._error_message(exc))

        self._run_async(work, on_success, on_error)
