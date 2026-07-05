import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio

from mouse_config_gui.window import MainWindow


class MouseConfigApp(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id="io.github.mouse_config_gui",
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )

    def do_activate(self):
        window = self.props.active_window
        if not window:
            window = MainWindow(application=self)
        window.present()


def main() -> int:
    app = MouseConfigApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
