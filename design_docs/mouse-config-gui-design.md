# Mouse Configurator — Design Doc (v1)

## 1. Overview

A GTK4 + libadwaita desktop application that provides a graphical front end for
[`mouse_m908`](https://github.com/dokutan/mouse_m908), the CLI tool used to configure
Redragon (and compatible Holtek VID 0x04d9) gaming mice on Linux. `mouse_m908` reads/writes
a single INI file per device and pushes it to hardware via USB; this GUI edits that INI
file with real widgets (color pickers, dropdowns, validated inputs) instead of hand
editing text, then shells out to the CLI to apply changes.

**v1 scope:** LED settings, DPI settings, report rate, profile management (read/apply/switch).
**Deferred to v2:** button mapping and macro editing (see §10).

## 2. Why GTK4 + libadwaita

- `python3-gi` (PyGObject) ships as a system package on virtually every Linux distro,
  unlike PySide6/PyQt6 which pull a large pip wheel. This matters for the stated goal of
  easy install/use.
- libadwaita gives us ready-made widgets that map directly onto this app's needs:
  `Adw.ViewSwitcher`/`Adw.ViewStack` for profile tabs, `Adw.ComboRow` for dropdowns,
  `Adw.SpinRow` / `Gtk.Entry` + `Gtk.EntryBuffer` validators for custom DPI input,
  `Gtk.ColorDialogButton` for color, `Adw.PreferencesGroup` for grouping related settings.
- Tkinter was ruled out: no native color picker widget worth using, no built-in validated
  input row, and past experience (kde-theme-installer) hit real Tkinter threading pain.
- Qt was ruled out per install-friction goals, even though it would look better on this
  KDE/Breeze desktop specifically.

## 3. Device support model

`mouse_m908` supports several mice with varying feature sets (confirmed from
`examples/example_*.ini` and the project README). Rather than hardcoding one schema,
the app uses a **capability descriptor per model**, so the same UI code adapts its
widgets/ranges to whichever mouse is selected.

### 3.1 Confirmed per-model differences

v1 originally scoped to the 4 example files shipped with `mouse_m908`, but the CLI's
C++ source (`include/<model>/`) actually implements 11 distinct mouse models plus a
`generic` catch-all, each with its own capability descriptor now (§3.3). Facts below
are sourced directly from the C++ (`data.cpp`/`setters.cpp`/`readers.cpp`), not just
the example `.ini` files or README prose — those two sometimes disagree (see M607 note).

| Model | VID:PID(s) | Profiles | Lightmode | Brightness | DPI format | DPI range | Notes |
|---|---|---|---|---|---|---|---|
| M908 | 04d9:fc4d | 5 | shared 11-value enum | 1–3 | actual + bytecode | 200–12400 (step 100/200) | Reference implementation |
| M607 | 04d9:fc38 | 5 | shared enum | 1–3 | actual + bytecode | 100–7200 (step 100/200) | Own `.ini`/docs claim 100–10000; the implemented lookup table stops at 7200 |
| M709 | 04d9:fc2a | 5 | shared enum | 1–3 | bytecode only | — | No decimal-DPI table implemented |
| M711 | 04d9:fc30 | 5 | shared enum | 1–3 | actual + bytecode | 100–10000 (step 100/200) | Also accepts independent per-axis DPI (`X<n>Y<m>`) |
| M715 | 04d9:fc39 | 5 | shared enum | 1–3 | bytecode only | — | Reverse-engineering incomplete upstream (source comments) |
| M719 | 04d9:fc4f | 5 | shared enum | 1–3 | actual + bytecode | 100–10000 (step 100/200) | README: fully implemented, like M908 |
| M721 | 04d9:fc5c | 5 | shared enum | 1–3 | bytecode only | — | Decimal-DPI table exists in source but is commented out (dead code) |
| M990 | 04d9:fc0f | 5 | shared enum | 1–3 | bytecode only | — | Decimal-DPI table left empty ("TODO"); distinct USB packet-table shapes from the rest of the family |
| M990 Chroma | 04d9:fc41 | 5 | shared enum | 1–3 | bytecode only | — | Richer RGB effect encoding in packet tables vs plain M908 |
| M686 | 25a7:fa34/fa35 | **2** | **restricted: off/static/breathing/rainbow** | **0–255** | actual only | 100–16000 (step 100) | Different vendor (wireless family); unsupported lightmodes silently downgrade to `static`; scrollspeed not exposed at all |
| M913 | 25a7:fa07/fa08 | **2** | **restricted: off/static/breathing/rainbow** | **0–255** | actual only | 100–16000 (step 100) | Same wireless family/quirks as M686 |
| generic | 04d9: 21-PID allowlist | 5 | shared enum | 1–3 | bytecode only | — | Fallback for any 0x04d9 device without a dedicated descriptor |

Shared across all 12 unless noted above: report rate 125/250/500/1000 Hz, speed 1–8
(write-only reliable, see §8), 5 DPI slots (min 1 enabled), 15 macro slots.
Scrollspeed is settable 1–0x3f (1–63) on every 0x04d9 model but its **read-back is
unreliable** (the CLI's own `-R` output prints a warning) — except M686/M913, where
scrollspeed isn't exposed by the read path at all (no value, no warning).

### 3.2 Shared `lightmode` enum

```
breathing, breathing_rainbow, rainbow, static, wave, alternating,
reactive, reactive_button, flashing, off, random
```
README notes only M908 and M719 have *all* settings fully implemented; other 0x04d9
models may silently ignore unsupported modes. v1 approach for those models: show the
full list and let the CLI be the enforcer (no client-side restriction).

**Exception confirmed in source**: M686 and M913 have their own restricted 4-value
lightmode enum (`off`, `static`, `breathing`, `rainbow`) and their `set_lightmode()`
silently maps anything else to `static`. For these two models specifically, the
capability descriptor restricts the dropdown to the 4 supported values — client-side
restriction is warranted here since the "let the CLI enforce it" approach would let
the UI show a mode that silently gets swapped out from under the user.

### 3.3 Capability descriptor (data-driven, not hardcoded per-model logic)

```yaml
# capabilities/m908.yaml
model: "908"                 # exact string passed to mouse_m908 -M
usb:
  vid: 0x04d9
  pids: [0xfc4d]
num_profiles: 5
num_macro_slots: 15
led:
  lightmodes: [breathing, breathing_rainbow, rainbow, static, wave,
               alternating, reactive, reactive_button, flashing, "off", random]
  brightness_range: [1, 3]
  speed_range: [1, 8]
  speed_readback_reliable: false
  scrollspeed_range: [1, 0x3f]
  scrollspeed_readback_reliable: false
report_rates: [125, 250, 500, 1000]
dpi:
  formats: [actual, bytecode]
  actual_range: [200, 12400]
  actual_step_breakpoints: [[200, 6200, 100], [6400, 12400, 200]]
  num_slots: 5
  min_enabled: 1             # can't disable all 5
buttons:
  supported: false           # v2
  count: 20
  names: [...]               # informational only until v2's button editor
macros:
  supported: false           # v2
quirks: [...]                # free-text model-specific caveats worth surfacing later
```

Each supported model gets one of these files, keyed by the CLI's own model name (also
used directly as the `-M` argument — no separate flag/mapping needed). The `usb`
block drives auto-detection (§11.2): `capability.find_capability_by_usb(vid, pid)`
scans all descriptors, checking model-specific files before falling back to
`generic`, so a model with its own descriptor always wins over generic's broad PID
allowlist even when the same PID appears in both. Adding a new mouse later is a new
YAML file, not new Python.

**YAML gotcha**: bare `off` in a YAML list is parsed as the boolean `False` (YAML 1.1
inherited quirk, also true for `on`/`yes`/`no`) — every lightmode list must quote it
as `"off"`. This bit us once already (§3.2's restricted enum and the shared enum both
needed the fix); a schema/test should catch a regression here, not just eyeballing.

## 4. Architecture

```
┌─────────────────────────┐
│   GTK4 / libadwaita UI   │   (Adw.ApplicationWindow, per-profile Adw.ViewStack pages)
└───────────┬─────────────┘
            │ binds to
┌───────────▼─────────────┐
│   In-memory data model   │   MouseConfig (5x ProfileConfig), loaded from capability descriptor
└───────────┬─────────────┘
            │ (de)serialized by
┌───────────▼─────────────┐
│   INI parser / writer    │   round-trips comments & metadata (# Model:, # Currently active profile:)
└───────────┬─────────────┘
            │ read/write
┌───────────▼─────────────┐
│        config.ini        │
└───────────┬─────────────┘
            │ passed to
┌───────────▼─────────────┐
│  CLI wrapper (subprocess)│   mouse_m908 -c / -R / -p / -M
└──────────────────────────┘
```

### 4.1 INI parser/writer

Python's `configparser` loses comments on write, and this file's comments carry real
metadata (`# Model: 908`, `# Currently active profile: N`, inline macro definitions as
`;##`/`;#` comment blocks). Plan: a small custom read/write layer that:
- Parses key/value pairs per `[profileN]` section normally.
- Separately extracts the header metadata comments and the trailing macro comment block,
  storing them as structured data (`model`, `active_profile`, `macros: {slot: [actions]}`)
  rather than discarding them.
- Reserializes in the same shape mouse_m908 expects, so a file we didn't fully understand
  (e.g. macros, since v1 doesn't edit them) survives a load→save round trip unchanged.

### 4.2 CLI wrapper

Thin subprocess layer, one function per operation:
- `apply_config(path, model=None)` → `mouse_m908 -c <path> [-M <model>]`
- `read_config(path, model=None)` → `mouse_m908 -R <path> [-M <model>]`
- `set_active_profile(n, model=None)` → `mouse_m908 -p <n> [-M <model>]`

All calls run async (GLib subprocess or a worker thread) so the UI doesn't block, with
errors surfaced via `Adw.Toast` rather than silently failing. udev/permissions errors
(common with libusb + kernel driver detach) get a specific, actionable message rather
than a raw stack trace.

### 4.3 Why not just write the file and expect the user to run the CLI?

Because the stated goal is ease of use — a GUI that still requires a terminal step
defeats the purpose. The app will have explicit "Apply to Mouse" and "Read from Mouse"
actions in the header bar, backed by the wrapper above.

## 5. UI layout

See accompanying mockup (`mouse_gui_mockup.html`). Summary:

- **Header bar:** app title, model selector (only relevant if running against a config
  file rather than a live-detected device), "Read from Mouse" and "Apply to Mouse" buttons.
- **View switcher (tabs):** one per profile, fixed at 5, labelled "Profile 1"–"Profile 5".
  Each tab's label swatch is tinted with that profile's configured LED color for quick
  visual identification (mirrors the physical mouse's own per-profile color indicator).
- **Per-profile page**, in `Adw.PreferencesGroup` cards:
  - **LED group:** lightmode dropdown, color picker button, brightness dropdown, speed
    dropdown, scrollspeed dropdown (hidden entirely for models that don't support it,
    e.g. M908).
  - **Performance group:** report rate dropdown.
  - **DPI group:** 5 rows, each: enable checkbox, dropdown of common presets for that
    model, and a custom value entry that only accepts the model's valid format (actual
    decimal in range, or `0xHHHH` bytecode, depending on capability descriptor). Enforces
    "at least one slot enabled" by disabling the checkbox on the last remaining enabled row.
  - **Button mapping group:** present but disabled, labeled "Coming in a future version"
    (v2 placeholder, see §10) so the layout doesn't need rework later.

## 6. Field validation summary

| Field | Widget | Validation |
|---|---|---|
| color | `Gtk.ColorDialogButton` | stored as 6-hex `RRGGBB`, no `#` |
| brightness | dropdown | model's `brightness_range` |
| speed | dropdown | model's `speed_range`; see §8 re: read-back |
| lightmode | dropdown | shared enum (§3.2) |
| scrollspeed | dropdown, hidden if unsupported | 1–0x3f where supported |
| report_rate | dropdown | fixed set: 125/250/500/1000 |
| dpi (preset) | dropdown | model-specific common values |
| dpi (custom) | validated entry | regex/range per model's `dpi.formats` |
| dpi enable | checkbox | can't disable the last enabled slot |

## 7. Known quirks to design around

- **`speed` read-back is unreliable.** Multiple independently-reported `mouse_m908 -R`
  dumps (M908 and M721) show `speed=0` regardless of what's actually configured on the
  mouse — writing appears to work, reading back does not. When loading a config with
  `speed=0`, the UI should not treat that as a confident "off" state; consider defaulting
  the dropdown to `1` with a small hint rather than silently displaying 0 as if it were
  trustworthy.
- **`scrollspeed` is entirely unreadable on M908** (tool prints this warning itself)
  — omit the field for that model rather than showing a value that's never accurate.
- **Empty `[profileN]` sections are valid** and mean "inherit tool defaults," not
  "misconfigured" — the UI shouldn't flag them as errors.
- **At least one DPI slot must stay enabled** — enforce in the UI, not just on write.
- **Active DPI slot / active profile are read-only runtime state**, not something this
  GUI writes back the same way as other fields (the "# Active dpi level" and
  "# Currently active profile" comments are informational, produced by `-R`, not settings
  `-c` consumes) — display them, don't expose them as editable widgets that silently
  no-op on apply.

## 8. Round-trip / non-destructive editing

Since v1 doesn't edit button mappings or macros, the parser must preserve both
unmodified when saving — a file with a `button_fire=fire:mouse_left:5:1` line or a
macro comment block must come back out identical, not dropped, even though the GUI
doesn't have UI for them yet. This is also what makes v2 (button editor) a additive
change rather than a rewrite of the file layer.

## 9. Multi-device support

All 12 models `mouse_m908` supports (§3.1) now have their own capability descriptor —
not just the 4 example `.ini` files originally reviewed. M990 Chroma turned out to
*not* be identical to `generic`: it has richer per-lightmode RGB packet encoding and,
unlike `generic`, no ambiguity about which specific mouse it is (own dedicated VID/PID),
even though both are currently bytecode-only for DPI. The model dropdown in the header
bar lists whichever descriptor files are present in the app's `capabilities/` directory,
so adding a new mouse later is just dropping in a new YAML file — no Python changes,
no separate `-M` name-mapping step since the descriptor's `model:` field *is* the `-M`
argument.

## 10. Deferred to v2: button mapping & macros

Explicitly out of scope for v1 per your call — flagged here so the data layer (§8)
doesn't paint us into a corner:
- Button mapping editor: needs the full valid-key list from `keymap.md` (ideally parsed
  at runtime from the installed doc path rather than hardcoded, so it stays correct across
  `mouse_m908` versions), a way to express the `fire:key:count:interval` structured action,
  key-combo strings (`super_l+shift_l+2`), and special tokens (`dpi+`, `dpi-cycle`,
  `report_rate+/-`, `profile_switch`, `macro<N>` references).
- Macro editor: a recorder/sequencer for the shared 15-slot, 67-action-max macro store,
  supporting `down`/`up`/`delay`/`move_*` actions, in both the old one-macro-per-file format
  and the new inline `;##`/`;#` comment format.

## 11. Open questions before implementation — resolved

1. `keymap.md` will live in `design_docs/` alongside the other design references for now
   (v2 concern; not parsed by v1 code).
2. **Auto-detect**: the app will auto-detect the connected mouse by parsing `lsusb`/udev
   for VID `0x04d9`, pre-selecting the matching model descriptor. Manual override via the
   header bar model dropdown should remain available for the config-file-only workflow
   (no device attached) and for the rare case of multiple compatible devices attached at
   once.
3. **Read from Mouse**: if there are unapplied in-memory edits, "Read from Mouse" must
   warn before overwriting them (e.g. an `Adw.AlertDialog` confirmation) rather than
   silently discarding unsaved changes. A future version could offer a diff view, but v1
   only needs the warn-and-confirm gate.
