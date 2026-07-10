# Macro editor design

Split out from the main design doc (§10 there just points here) because the
macro editor grew its own data model, two local file formats, and enough UX
decisions that folding it all into the main doc would swamp the rest of it —
same reasoning `keymap.md` is its own file rather than inlined.

## 1. Scope

A manual sequencer for the mouse's 15 shared macro slots
(`down`/`up`/`delay`/`move_left`/`move_right`/`move_up`/`move_down`
actions), plus two app-side additions `mouse_m908` has no concept of at all:
naming a slot, and a local library of saved macros you can swap into any
slot on demand. Deliberately out of scope: live key-capture recording (you
build a macro by picking actions from a form, not by pressing real keys),
and in the library, no "just play a preview."

## 2. Data model

- `MacroAction(kind, value)` (`models.py`) — one action. `kind` is one of
  the seven above; `value` is a key/mouse-button name for `down`/`up`, or a
  decimal string for `delay`/`move_*`.
- `MouseConfig.macros: dict[int, list[MacroAction]]` — the 15 slots, keyed
  1-15. A slot absent from the dict means empty, matching how a real `-R`
  read never mentions a slot with all-zero macro data (verified against
  `mouse_m908`'s `read_and_print_settings`: `if (macro_bytes[i] == 0...)
  continue;`).
- `MouseConfig.macro_names: dict[int, str]` — see §3.

Grammar/range validation (`keymap.py`'s `is_valid_macro_action`,
`MAX_MACRO_ACTIONS`) was checked directly against `mouse_m908`'s
`_i_encode_macro`/`_i_decode_macro` (`include/rd_mouse.cpp`), not just
`keymap.md`:
- `down`/`up` accept a keyboard key or one of 5 mouse buttons
  (`mouse_left/right/middle/forward/backward` — notably including
  forward/backward, which the *button-mapping* `fire:` grammar's button set
  does not).
- `delay` is 10ms units, 1-255; `move_*` is 1-120.
- The byte budget is 3 bytes/action into a 256-byte buffer starting at
  offset 8, stopping once the offset exceeds 212 — simulated exactly:
  **69 actions max**, not the 67 originally guessed in the main design doc.

## 3. Naming: why a `.ini` comment, not a separate config file

`mouse_m908`'s macro protocol has no name field anywhere — confirmed from
`set_macro`/`set_all_macros` (`include/m908/setters.cpp`) and the on-device
byte layout. A name is therefore purely an app-side label, and the natural
question is where it lives.

**Decision: `# Macro N name: <text>` inside the same `.ini` file**, parsed/
written by `ini_io.py`, instead of a separate app config file. Verified
safe by reading `set_all_macros`'s actual parsing loop: it only recognizes
two `std::regex_match` (full-line match) patterns per line — `;## macro
[0-9]*` for headers and `;# .*` for actions. A line starting with a single
`#` (not `;`) matches neither, so a real `mouse_m908 -m <file>` call
silently ignores it, exactly like it already ignores `# Model:` and
`# Currently active profile:`. Keeping the name in the same file means it
travels with the config if you save/share/back it up, consistent with how
every other field in this app already works — no second data-model story.

The name line is written immediately before its macro's `;## macroN`
header. Loading tolerates it appearing anywhere `#`-prefixed lines are
scanned (order isn't load-bearing).

## 4. Why names still needed a *second*, local-only store

`mouse_m908 -R` always returns fresh device state with no name data (there's
nowhere on the mouse to store one) — so a plain "Read from Mouse", including
the automatic one on app launch, was wiping every name on every read, since
the `.ini`-comment mechanism from §3 only round-trips a name if you keep
working from the *same saved file* rather than re-reading the device.

**Fix**: `macro_library.py` also persists slot names, keyed by slot number,
to `$XDG_CONFIG_HOME/mouse-config-gui/macro_slot_names.yaml` (falls back to
`~/.config`), written immediately on every name change — independent of
Apply/Save, the same way a browser saves bookmarks. `window.py`'s
`_populate_from_config()` (called by every read/load path) merges in the
remembered name for any slot that still has content but wasn't explicitly
named by what was just loaded; an explicit `# Macro N name:` from a loaded
file still wins, and a slot that comes back genuinely empty never gets a
stale name reattached to it.

This is why `ButtonGroup`/`ButtonRow`/`button_picker.py`'s `macro_names`
parameter needs to be the *same live dict object* MainWindow holds, mutated
in place rather than rebound on every config load (`window.py`'s
`_populate_from_config` does `self._macro_names.clear(); .update(...)`, not
`self._macro_names = dict(...)`) — button pickers capture that reference
once at construction time and never rebuild otherwise.

## 5. Macro library

A local, named collection of saved action lists, independent of whichever
`.ini` is currently loaded — lets you keep more than 15 macros around and
swap them into a live slot as needed. Stored at
`$XDG_CONFIG_HOME/mouse-config-gui/macro_library.yaml`, shape
`{entry_name: [{kind, value}, ...]}`. Also saves immediately on every
change, also not part of `MouseConfig`/the dirty-tracking/Apply flow.

- **Save to Library…**: snapshots the selected slot's current actions under
  a chosen name (prompt prefilled with the slot's current name, if any).
- **Load from Library…**: a popover listing entries (name + action count);
  clicking one copies its actions *and* name into the selected slot.
- **Rename**: a pencil icon per entry in the same popover; renames in place
  (pop the old key, set the new one, re-save) rather than requiring a
  separate delete + re-save under a new name.
- **Delete**: a trash icon per entry in the same popover.

**Copy to Slot…** duplicates the selected slot's actions directly into
another slot, without a library detour — no library entry is created or
required. Only the action list copies over; the target slot's own name (if
it has one) is left as-is. Same replace-confirmation + reference-warning
treatment as Load from Library when the target slot already has content.

Deliberately not built: in-place editing of a library entry (load it into a
slot, edit there, re-save under the same name instead) — kept the surface
area small since it has a working, if slightly more steps, path through
what already exists.

## 6. Confirmations

Four destructive actions, all gated behind `Adw.AlertDialog` (`_confirm()`
helper): **Clear Macro**, **Load from Library** and **Copy to Slot**
(both only when the target slot already has content — proceeding into an
empty slot immediately, no unnecessary friction), and **Delete from
Library**. All of these also surface
`_reference_warning()`: if the slot being cleared/replaced is currently
mapped to by a button on *any* profile (`window.py`'s
`_find_macro_references`, scanning every `ButtonGroup.mappings` for
`macroN`/`macroN:repeats`/`macroN:while`/`macroN:until`), the dialog names
exactly which "Profile X: Button" locations reference it — since button
mappings reference a macro by number, not name, clearing/replacing a slot's
content doesn't itself update or warn any button that points at it.

None of this touches the physical mouse — every dialog says so explicitly,
since nothing is written to hardware until "Apply to Mouse" regardless of
what happens in the editor.

## 7. Editing

Add/reorder (up/down)/edit/delete, one action at a time. Edit opens an
"Edit Action" dialog reusing the exact same kind-dropdown + value-widget
construction the Add form uses (`_build_kind_value_widgets()`, one factory
for both so they can't drift apart), pre-populated with the action's
current kind/value, replacing it in place on Save (same index, order
preserved) rather than requiring delete-then-re-add.

## 8. Verified, not just read from docs

Two corrections to `keymap.md`/the original design doc came from reading
`mouse_m908`'s actual C++ source rather than trusting it (§2's action limit,
§3's safe-comment claim). A live end-to-end test also ran against a real
M908: built a macro on an unused slot, saved it to the library, loaded it
back, applied both `mouse_m908 -c` and `-m` to real hardware, then read the
device back and confirmed the untouched slot (24 actions) was byte-for-byte
unchanged and the new slot matched exactly what was sent.
