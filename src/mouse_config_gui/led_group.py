"""LED settings group for a single profile: lightmode, color, brightness,
speed, scrollspeed (design doc §5, §6).

Options and scrollspeed visibility are driven by the mouse model's capability
descriptor -- call apply_capability() whenever the selected model changes.
"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, Gtk

from mouse_config_gui.capability import Capability


class LedGroup(Adw.PreferencesGroup):
    def __init__(self, capability: Capability, on_changed=None, **kwargs):
        super().__init__(title="LED", **kwargs)
        self._on_changed = on_changed

        self.lightmode_row = Adw.ComboRow(title="Lightmode")
        self.add(self.lightmode_row)

        self.color_button = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog())
        self.color_button.set_valign(Gtk.Align.CENTER)
        color_row = Adw.ActionRow(title="Color")
        color_row.add_suffix(self.color_button)
        self.add(color_row)

        self.brightness_row = Adw.SpinRow(
            title="Brightness", adjustment=Gtk.Adjustment(value=1, lower=1, upper=1, step_increment=1)
        )
        self.add(self.brightness_row)

        self.speed_row = Adw.SpinRow(
            title="Speed", adjustment=Gtk.Adjustment(value=1, lower=1, upper=1, step_increment=1)
        )
        self.add(self.speed_row)

        self.scrollspeed_row = Adw.SpinRow(
            title="Scroll Speed", adjustment=Gtk.Adjustment(value=1, lower=1, upper=1, step_increment=1)
        )
        self.add(self.scrollspeed_row)

        self.apply_capability(capability)

        # Connect after the initial apply_capability() above so construction-time
        # defaults don't spuriously mark a freshly built group as "changed".
        self.lightmode_row.connect("notify::selected", self._notify_changed)
        self.color_button.connect("notify::rgba", self._notify_changed)

    def _notify_changed(self, *_args) -> None:
        if self._on_changed is not None:
            self._on_changed()

    def apply_capability(self, capability: Capability) -> None:
        led = capability.data["led"]

        self.lightmode_row.set_model(Gtk.StringList.new(led["lightmodes"]))
        self.lightmode_row.set_selected(0)

        self._set_range(self.brightness_row, led["brightness_range"])
        self._set_range(self.speed_row, led["speed_range"])

        scrollspeed_range = led.get("scrollspeed_range")
        self.scrollspeed_row.set_visible(scrollspeed_range is not None)
        if scrollspeed_range is not None:
            self._set_range(self.scrollspeed_row, scrollspeed_range)

    def _set_range(self, row: Adw.SpinRow, value_range: list[int]) -> None:
        lo, hi = value_range
        adjustment = Gtk.Adjustment(value=lo, lower=lo, upper=hi, step_increment=1, page_increment=1)
        adjustment.connect("value-changed", self._notify_changed)
        row.set_adjustment(adjustment)

    @property
    def lightmode(self) -> str:
        model = self.lightmode_row.get_model()
        return model.get_string(self.lightmode_row.get_selected())

    @lightmode.setter
    def lightmode(self, value: str) -> None:
        model = self.lightmode_row.get_model()
        for i in range(model.get_n_items()):
            if model.get_string(i) == value:
                self.lightmode_row.set_selected(i)
                return
        raise ValueError(f"{value!r} is not a valid lightmode for this model")

    @property
    def color(self) -> str:
        rgba = self.color_button.get_rgba()
        return "".join(f"{round(c * 255):02x}" for c in (rgba.red, rgba.green, rgba.blue))

    @color.setter
    def color(self, hex_color: str) -> None:
        rgba = Gdk.RGBA()
        rgba.parse(f"#{hex_color}")
        self.color_button.set_rgba(rgba)

    @property
    def brightness(self) -> int:
        return int(self.brightness_row.get_value())

    @brightness.setter
    def brightness(self, value: int) -> None:
        self.brightness_row.set_value(value)

    @property
    def speed(self) -> int:
        return int(self.speed_row.get_value())

    @speed.setter
    def speed(self, value: int) -> None:
        self.speed_row.set_value(value)

    @property
    def scrollspeed(self) -> int | None:
        if not self.scrollspeed_row.get_visible():
            return None
        return int(self.scrollspeed_row.get_value())

    @scrollspeed.setter
    def scrollspeed(self, value: int) -> None:
        self.scrollspeed_row.set_value(value)
