
# Mouse Configurator

GTK4 + libadwaita GUI front end for [`mouse_m908`](https://github.com/dokutan/mouse_m908),
letting you edit Redragon/Holtek (VID `0x04d9`) gaming mouse configs with real widgets
instead of hand-editing the INI file.

See [`design_docs/mouse-config-gui-design.md`](design_docs/mouse-config-gui-design.md) for
the full design, and [`design_docs/mouse_gui_mockup.html`](design_docs/mouse_gui_mockup.html)
for a UI mockup.

## Status

Only tested against a real **Redragon M908**. Capability data (LED modes,
DPI ranges, USB ids, etc.) for the other 11 models `mouse_m908` supports was
derived directly from its C++ source, not verified against real hardware --
if something's wrong for your model, please open an issue.

## Requirements

- Python 3.10+
- GTK4 + libadwaita 1.x + PyGObject (`python3-gi`), typically a system package
  (e.g. `gir1.2-adw-1`/`libadwaita` + `python3-gi` on Debian/Ubuntu, `python-gobject` +
  `libadwaita` on Arch, `python3-gobject` on Fedora)
- [`mouse_m908`](https://github.com/dokutan/mouse_m908) installed and on `PATH`

## Install

```sh
pip install --user git+https://github.com/robinsiebler/mouse-config-gui.git
```

After installing:

```sh
mouse-config-gui
```

`--user` installs alongside your system Python rather than into an isolated
venv, so it picks up the system-installed PyGObject/GTK4 instead of trying
(and failing) to build them from source, and the `mouse-config-gui` command
lands in `~/.local/bin`, which is on `PATH` by default on most distros.

## Development setup

```sh
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -e ".[dev]"
mouse-config-gui
```

`--system-site-packages` is required so the venv can see the system-installed PyGObject.
