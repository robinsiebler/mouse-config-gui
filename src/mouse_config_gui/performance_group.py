"""Performance settings group for a single profile: report rate (design doc §5, §6)."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk

from mouse_config_gui.capability import Capability


class PerformanceGroup(Adw.PreferencesGroup):
    def __init__(self, capability: Capability, on_changed=None, **kwargs):
        super().__init__(title="Performance", **kwargs)
        self._on_changed = on_changed

        self.report_rate_row = Adw.ComboRow(title="Report Rate")
        self.add(self.report_rate_row)

        self.apply_capability(capability)

        # Connect after the initial apply_capability() above so construction-time
        # defaults don't spuriously mark a freshly built group as "changed".
        self.report_rate_row.connect("notify::selected", self._notify_changed)

    def _notify_changed(self, *_args) -> None:
        if self._on_changed is not None:
            self._on_changed()

    def apply_capability(self, capability: Capability) -> None:
        self._report_rates = capability.data["report_rates"]
        self.report_rate_row.set_model(
            Gtk.StringList.new([f"{rate} Hz" for rate in self._report_rates])
        )
        self.report_rate_row.set_selected(0)

    @property
    def report_rate(self) -> int:
        return self._report_rates[self.report_rate_row.get_selected()]

    @report_rate.setter
    def report_rate(self, value: int) -> None:
        try:
            index = self._report_rates.index(value)
        except ValueError:
            raise ValueError(f"{value!r} is not a valid report rate for this model") from None
        self.report_rate_row.set_selected(index)
