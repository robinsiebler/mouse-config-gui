# Using the macro editor

A macro is a saved sequence of key presses, mouse clicks, pauses, and cursor
movements that plays back when you trigger it — useful for anything you do
repeatedly, or for making a mouse button type out a whole command. Your
mouse can hold **15 macros** at once, numbered 1–15.

Open the editor from the **"Macros…"** button in the top-left of the window.

## Building a macro

Pick a macro slot from the list on the left, then use the **Down / Up /
Delay / Move Left / Move Right / Move Up / Move Down** dropdown at the
bottom to add one action at a time:

- **Down** / **Up** — press or release a key or mouse button. A tap is a
  `Down` immediately followed by an `Up` of the same key; holding a
  modifier while you press another key is a `Down` for the modifier, then
  `Down`/`Up` for the key, then `Up` for the modifier.
- **Delay** — pause before the next action. The number you enter is in
  **units of 10 milliseconds** — entering `10` waits 100ms (a tenth of a
  second), not 10ms. This trips people up, so it's worth double-checking:
  the row shows the real time next to it (e.g. "Delay: 10 (100 ms)") so you
  don't have to do the math yourself.
- **Move Left / Right / Up / Down** — nudge the cursor by that many pixels
  (roughly) in that direction.

Click **Add** to append it to the sequence. Actions play back top to
bottom, so build them in the order you want them to happen.

Each macro can hold up to **69 actions**. The counter above the list
("12 / 69 actions") tracks how close you are.

### Fixing a mistake

- **Reorder**: the ▲/▼ arrows on a row move it up or down.
- **Edit**: the pencil icon opens that action's kind and value again so you
  can change it, without deleting and re-adding.
- **Delete**: the trash icon removes just that one action.
- **Clear Macro**: wipes every action (and the macro's name) in one go —
  asks for confirmation first, since there's no undo once you confirm.

## Naming a macro

Type a name into the **"Name (optional)"** field above the action list.
Once named, that macro shows its name instead of just "Macro 3" everywhere
in the app — including the list of macros you can pick from when mapping a
mouse button. Names are entirely optional and don't do anything on their
own; they're just there so you can tell your macros apart.

## The macro library

You only have 15 slots on the mouse, but you can keep as many macros as you
want saved locally and swap them in when needed:

- **Save to Library…** copies the currently selected macro's actions (under
  a name you choose) into your library. It doesn't touch the mouse or clear
  the slot — it's just a backup copy.
- **Load from Library…** shows your saved macros; clicking one copies its
  actions and name into whichever slot you currently have selected. If that
  slot already has something in it, you'll be asked to confirm before it's
  replaced.
- Each saved macro in the list has a **pencil icon** to rename it and a
  **trash icon** to delete it from the library (deleting asks for
  confirmation).

Want to duplicate a macro straight into another slot without keeping a
library copy around? Use **Copy to Slot…** instead — pick the destination
slot and its actions are copied directly over. If that slot already has
content, you'll be asked to confirm before it's replaced.

Loading from the library doesn't apply anything to your mouse by itself —
see below.

## Applying to the mouse

Nothing you do in the macro editor touches the physical mouse until you
close the editor and click **"Apply to Mouse"** in the main window. Until
then, feel free to experiment — worst case, click **"Read from Mouse"** to
throw away your unsaved changes and start over from what's actually on the
device.

## Using a macro on a button

To make a mouse button trigger a macro, map that button to `macro3` (or
whichever slot number you used) — the button-mapping picker's **Macro**
submenu lists all 15 slots by name (if named) so you don't have to remember
numbers.

One thing worth knowing: because a button mapping refers to a macro by
**slot number**, if you later clear or replace that slot's content, any
button still pointing at it will do whatever's *now* in that slot — not
what used to be there. If you try to clear or replace a slot that's
currently used by a button mapping, the confirmation dialog will tell you
exactly which button(s) and profile(s) reference it, so this isn't a silent
surprise.

## Where this is all stored

Macro names and your library are saved on your computer, not on the mouse
(the mouse itself has no way to store either) — see the note in the
project's [README](../README.md#status) if you want to back them up.
