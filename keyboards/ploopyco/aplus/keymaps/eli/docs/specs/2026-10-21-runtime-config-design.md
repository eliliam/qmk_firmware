# Runtime configuration for Eli's Ploopy A+

Status: approved in conversation on 2026-10-21. Terms in **bold** are defined
in [GLOSSARY.md](../../GLOSSARY.md).

## Intent

Today every change to the mouse means editing `keymap.c` or `config.h`,
rebuilding in Docker, and reflashing. Eli changes four kinds of things:
button assignments, tuning numbers (such as `NIRI_FLICK_THRESHOLD`), new
behaviors (such as Niri hold mode), and what an action does on the desktop.

The goal is a long-term setup that grows with Eli's needs:

- Button assignments and tuning numbers change at runtime, from a GUI (VIA)
  or by asking Claude, with no rebuild.
- What an action does on the desktop stays on the PC. The mouse sends neutral
  chords and Niri's config decides what they do, as Niri hold mode already
  does.
- New behaviors still need a reflash, but each one is built with its
  **settings** exposed, so after the first flash it only needs tuning.

## Goals

1. Every tuning number and toggle becomes a **setting**: stored on the mouse,
   changed live, and kept across unplugging.
2. VIA (usevia.app in Chromium) shows a panel with a control for each
   setting, and VIA's normal remapping edits the **button map**.
3. A **mouse config** file in dotfiles is the source of truth for the whole
   mouse: the button map on every layer plus every setting.
4. A `ploopy` CLI lets Eli or Claude inspect and change the mouse and keep it
   in line with the mouse config.
5. Reflashing and wipes stop costing anything: **auto-apply** restores the
   mouse config when the mouse is plugged in after a **reset** or **wipe**.
6. The **cheat sheet** always shows what the mouse actually does.

## Non-goals for v1

- Combos. They come later, defined in firmware. Each combo's output should be
  a button-map slot so VIA can remap it.
- Checking that every Hyper chord in the button map has a Niri bind.
- Per-app profiles.
- VIA macros in the mouse config.

## Anti-goals

- Moving to Vial or any other fork of QMK. Eli chose VIA so the firmware stays
  on Ploopy's A+ fork. Vial would mean porting the A+ code to vial-qmk and
  losing VIA's custom settings panels.
- A firmware build that reads from dotfiles.
- Any change that makes reflashing riskier than it is today.

## Decisions

### Platform

- VIA on regular QMK, Ploopy's fork, branch `eli-aplus`. `VIA_ENABLE` is
  already on.
- The A+ has no definition in VIA's repository. Eli sideloads our generated
  definition in usevia.app's Design tab. VIA keeps it per browser profile.

### Settings

- All settings live in one store in VIA's custom config area of the EEPROM.
  This includes the settings that today sit in `user_config`
  (`eeconfig_user`) and DPI (Ploopy's `eeconfig_kb` index).
  `eeconfig_user` and `eeconfig_kb` are no longer the source for these
  values. Rolling back to stock firmware still works; stock just starts from
  its own defaults.
- The v1 settings:
  - **Niri navigation:** flick threshold, tap term, idle reset.
  - **Drag scroll:** horizontal and vertical speed.
  - **Wheels:** vertical scroll arrows and horizontal scroll arrows, both
    on/off.
  - **Bottom Right:** middle click or hold-to-drag-scroll.
  - **LED:** brightness.
  - **DPI:** a free value, about 100 to 12000 in steps of 100.
  - **Acceleration curve:** on/off, takeoff, growth rate, offset and limit.
    These use the drashna `pointing_device_accel` module's existing VIA
    channel (24), enabled with `POINTING_DEVICE_ACCEL_VIA_ENABLE = yes`.
- Each setting has a **firmware default** written by hand in the firmware.
  The defaults match today's compiled values (Niri 200/250/200, drag scroll
  0.8/0.24, and so on).
- The Control-layer buttons stay. They change the same settings: the
  scroll-arrow toggles, the Bottom Right mode, LED brightness, and DPI. The
  DPI button cycles a few presets by setting the DPI value. Using them causes
  **drift**, which `ploopy diff` shows.
- When new firmware adds settings, the existing stored values are kept, and
  the new settings start at their firmware defaults.

### Setting catalog

- One **setting catalog** file in `keymaps/eli` lists every setting: its id,
  type, range, firmware default, VIA label, and its name in the mouse config.
- A script generates two files from it: the VIA definition JSON (the panel,
  merged with the button layout and custom keycodes) and a C header for the
  firmware. The CLI reads the catalog directly.
- Adding a setting means editing the catalog and writing the behavior that
  uses it.

### Mouse config

- TOML, at `~/dotfiles/ploopy/` (follow the stow layout that the rest of
  dotfiles uses).
- It holds the button map for all 8 layers plus every setting.
- Buttons use QMK keycode names exactly as in `keymap.c`, such as `MS_BTN1`,
  `HYPR(KC_LEFT)` and `PKC_NIRI`.
- Accel values are real numbers (takeoff 2.0), not VIA's 0 to 60000 slider
  scale.
- `pull` rewrites values and keeps Eli's comments.

### CLI

- A single-file Python script with inline dependencies, run with `uv run`.
  It lives in `keymaps/eli` because it must match the firmware's catalog. A
  wrapper named `ploopy` in dotfiles goes on `PATH` (`~/.local/bin`).
- It talks to the mouse over VIA's raw HID protocol (usage page 0xFF60, usage
  0x61; this build reports protocol 13). It uses the same commands as VIA for
  the button map and custom values.
- Commands:
  - `diff`: show drift between the mouse and the mouse config.
  - `apply`: write the mouse config onto the mouse. The file wins.
  - `pull`: copy the mouse's state into the mouse config, keeping drift on
    purpose.
  - `get` and `set`: read or change one setting live (for Claude's tuning),
    for example `ploopy set niri.flick_threshold 240`. `set` saves the value
    on the mouse **and** writes it into the mouse config, keeping comments,
    then regenerates the cheat sheet. Tuning never leaves drift behind.
- Keycode names map to numbers for this QMK version: keycodes 0.0.8, `PKC_*`
  from `QK_USER` (0x7E40) in enum order, and the accel module's keycodes from
  0x77C0.
- Unknown setting names, out-of-range values and unknown keycodes are errors.
  Nothing is written when there is an error.

### Plug-in hook

- A udev rule triggers a systemd user unit when the A+ (5043:81db) connects.
  It does two things:
  1. Restarts `voxtype`, which today Eli does by hand after re-enumeration.
  2. Auto-applies only if the mouse was actually reset or wiped since the
     last apply. A reflash built on the same day resets nothing and must not
     trigger it. A normal replug with unpulled VIA tweaks changes nothing.
     `apply` leaves a marker on the mouse that a reset or wipe invalidates.
     How the marker works is left to the builder.
- Auto-apply restores the **whole** mouse config, settings included, even
  after a reset that only lost the button map. Unpulled setting drift is
  discarded on purpose (Eli's choice: the file wins). Because `ploopy set`
  also writes the mouse config, only VIA and Control-layer changes are at
  risk.
- When auto-apply runs or fails, the hook sends a desktop notification with
  `notify-send`.

### Cheat sheet

- It moves from `keymaps/eli/keymap.html` to `~/dotfiles/ploopy/`.
- The CLI regenerates it from the mouse config on every `apply`, `pull` and
  `set`. The existing drawing code stays.
- Its text comes from a hand-kept template in `~/dotfiles/ploopy/`. The
  template has placeholders for keycode labels and for setting values, such
  as `{niri.flick_threshold}`, and the CLI fills them in. That covers layer
  titles and LED colours, wheel text that depends on the scroll-arrow
  settings, the Niri panel, and Bottom Right text that depends on its mode.
  Seed the template from today's `keymap.html` data.
- Keycode labels come from a label table in `~/dotfiles/ploopy/` that maps a
  keycode to a label and a description. A keycode with no entry shows its QMK
  name.
- Layers with no buttons assigned (all transparent) get no panel.
- `AGENTS.md` changes: the rule "keep keymap.html in sync by hand" becomes
  "when a keycode or behavior is added, add its label and update the sheet
  template".

## Constraints and known facts

These come from research into this tree; the file paths are in this repo.

- **A reflash resets the button map.** The VIA EEPROM magic is the build date
  (`quantum/via.c:70-82`), and Docker stamps it in UTC. So any flash built on
  a different day resets the button map to `keymap.c`. The custom area,
  `eeconfig_kb` and `eeconfig_user` survive. Auto-apply covers this, so do
  **not** freeze the date with `SKIP_VERSION`.
- **Custom area size:** the accel module defines
  `VIA_EEPROM_CUSTOM_CONFIG_SIZE` as 20 bytes in its `post_config.h`.
  Overriding it needs `VIA_EEPROM_CUSTOM_CONFIG_ERROR_OVERRIDE`. The module
  uses offsets 0 to 19. Our settings go at offset 20 and above.
- **The size is fixed once.** A change of size moves the dynamic keymap's
  address. Choose a size with plenty of room (macros take the rest of the
  4 KB, and macros are not used).
- **One VIA handler.** QMK has no hook chain for VIA custom values. The keymap
  defines a strong `via_custom_value_command_kb`. It passes channel 24 to
  `via_custom_value_command_accel` and handles our own channel. Avoid channels
  1 to 5 (2 is rgblight, which is enabled).
- **Accel data can be stale.** Nothing writes accel defaults except a full
  init. Stale or zeroed floats give NaN. The settings store has a format
  version, and the accel values are checked at boot and fall back to firmware
  defaults when invalid.
- **Takeoff floor.** The module's VIA setter skips the takeoff ≥ 0.5 guard
  (`pointing_device_accel_via.c:51-56`). The CLI enforces it.
- **DPI bounds bug.** Ploopy's DPI bounds check uses `>` where it needs `>=`
  (`keyboards/ploopyco/ploopyco.c:234`). Fix it, or make it irrelevant now
  that DPI moves into our store.
- **Flashing.** The flash procedure stays: Control layer, then Bottom Left
  (`QK_BOOT`). Holding Left click at plug-in still wipes everything, and
  auto-apply then restores it.

## Left to the builder

- The catalog's file format, the generator, and the byte layout of the
  settings store. Include a format version and room to grow.
- The value encoding on our VIA channel. Follow VIA's range rule: one byte up
  to 255, otherwise two bytes big-endian.
- How the reset marker works.
- How `PKC_*` custom keycodes show by name in VIA. Check how VIA v13 renders
  `QK_USER` codes and choose between `customKeycodes` and moving them into the
  `QK_KB` range.
- Where the CLI gets the keycode name table. QMK's `load_spec('0.0.8')` merges
  several versions; generate or vendor its output.
- The structure of the label table file.
- Updating `AGENTS.md`, the readme, and the memory notes for the new flow.
- How to test. The firmware is checked on the real mouse. The CLI's encoding
  can be unit-tested without hardware.

## Implementation notes (2026-10-21)

Where the build differs from the text above, the code and `AGENTS.md` win:

- The CLI is a small uv project (`tools/`), not a single-file script.
- `pointer.dpi` has no step. VIA's slider sets any value, and the sensor
  driver rounds down to 100.
- The CLI uses hidapi's `hidraw` module, and it skips replies meant for VIA.
- The udev rule matches `ENV{ID_USB_INTERFACE_NUM}`, and it has no uaccess
  tag: the hidraw nodes are already `root:users 0660`.
- Accel drift allows ±1 slider step, because the module truncates.
- `via_init_kb()` resets the dynamic keymap when the settings store is
  missing (first flash, or a size change).
