# Using Mouse Configurator

A GTK4/libadwaita app for configuring Redragon/Holtek gaming mice on Linux —
LED lighting, DPI, report rate, button mapping, and macros — without hand
editing an INI file.

## Getting started

Plug in your mouse and launch `mouse-config-gui`. If it's a recognized
model, the app detects it automatically, selects the right model in the
dropdown, and reads its current settings straight from the mouse.

If nothing's detected (no mouse plugged in, or you just want to edit a
config file without a device attached), pick your model from the dropdown
in the top toolbar yourself. You can still open, edit, and save `.ini`
files without a mouse connected — you just won't be able to Read from or
Apply to a device until one is.

## The window

- **Header bar**: the ☰ menu (**Open Config File…**, **Save Config File**,
  **Save Config File As…**) and the **Macros…** button, which opens the
  [macro editor](macro-editor-guide.md) (see below).
- **Toolbar row**: the **model** dropdown, **Read from Mouse**, and
  **Apply to Mouse**.
- **Profile tabs**: five tabs, "Profile 1" through "Profile 5", one per
  profile slot the mouse stores. Each tab's little swatch is tinted with
  that profile's LED color so you can tell them apart at a glance.

Everything below the toolbar — LED, Performance, DPI, Buttons — applies to
whichever profile tab is currently selected; each profile has its own
independent settings. Macros are the exception: the 15 macro slots are
shared across all 5 profiles, which is why they live in their own dialog
instead of a per-profile section.

## Reading from and applying to the mouse

- **Read from Mouse** pulls the mouse's actual current settings into the
  app, discarding anything you've changed in the window but not applied.
  If you have unapplied edits, you'll be asked to confirm first.
- **Apply to Mouse** writes everything currently shown in the window —
  across all 5 profiles, plus any macro edits — to the physical mouse. If
  anything you've entered is invalid (a bad DPI value, an unrecognized
  button mapping, a malformed macro action), Apply is blocked and a toast
  tells you exactly what to fix and where, with a button that jumps you to
  the right profile.

Nothing is sent to the mouse until you click Apply — feel free to
experiment.

## Opening and saving config files

The ☰ menu's **Open Config File…** loads a `.ini` file (the same format
`mouse_m908 -R`/`-c` use) instead of reading from a live device — handy for
keeping a backup, or editing a config for a mouse you don't currently have
plugged in. If the file names a model your app recognizes, the model
dropdown switches to match automatically.

**Save Config File** / **Save Config File As…** write the current window
state back out to a `.ini` file, without touching the mouse.

## LED

Per profile: **Lightmode** (a shared set of effects — `static`,
`breathing`, `rainbow`, and others; two wireless models restrict this to a
smaller set), **Color**, **Brightness**, **Speed**, and **Scroll Speed**
(hidden entirely on models that don't support it). Note: on some models,
reading `speed`/`scrollspeed` back from the mouse isn't reliable even
though writing them works fine — if a value looks off after a fresh Read,
that's a known mouse_m908 quirk, not something wrong with your settings.

## Performance

Just **Report Rate** (the USB polling rate — 125/250/500/1000 Hz,
depending on what your model supports) per profile.

## DPI

Five DPI slots per profile, each with an enable checkbox and a value entry.
The entry only accepts values valid for your model's format (a decimal DPI
number in range, or raw `0xHHHH` bytecode, depending on the mouse) —
invalid entries turn red and block Apply. At least one slot must stay
enabled; the app won't let you uncheck the last one.

## Button mapping

Each of the mouse's programmable buttons gets a text entry (turns red if
what's typed isn't a recognized mapping) plus a **Choose…** button that
opens a categorized picker — Left/Right/Middle Click, Single Key, Combo
Key, Basic, Advanced, Media, **Macro** (lists your 15 macro slots by name,
if named), Fire Key, DPI Switch, Profile Switch, Report Rate, and Disable —
so you rarely need to type a mapping by hand. The **?** button next to the
group heading shows a quick syntax reference if you do.

The "Advanced" submenu is split into two groups: options confirmed to
actually work on Linux at the top, and options that are only meaningful to
the official Windows software (shown in red) at the bottom — mouse_m908
will accept them without error, but they likely won't do anything.

## Macros

The mouse stores 15 macros, shared across all 5 profiles, edited via the
**Macros…** button in the header bar rather than a per-profile section.
You can name them, build/edit their action sequences, and keep a local
library of extras to swap in as needed. See the dedicated
**[macro editor guide](macro-editor-guide.md)** for the full walkthrough.

## Where your data lives

- Whatever you Save or Apply lives in the `.ini` file you chose, or on the
  mouse itself.
- Macro names and your macro library are the exception — they're local to
  this computer (`~/.config/mouse-config-gui/`), since the mouse has no
  storage for either. Back that folder up alongside your config files if
  you want to keep them.
