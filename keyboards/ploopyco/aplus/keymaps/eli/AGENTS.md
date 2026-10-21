# Eli's Ploopy A+ keymap: agent instructions

The mouse is configured at **runtime**: the button map and every tuning value
live on the mouse and change through VIA or the `ploopy` CLI without a
reflash. The **mouse config** in dotfiles (`~/.config/ploopy/mouse.toml`,
stowed from `~/dotfiles/ploopy/`) is the source of truth. Terms are defined in
[GLOSSARY.md](GLOSSARY.md); the design and its reasons are in
[docs/specs/2026-10-21-runtime-config-design.md](docs/specs/2026-10-21-runtime-config-design.md).

Verify against the real mouse before you report a change as working: run
`ploopy diff` (exit 0 = mouse matches the config), and ask Eli to try the
behavior.

## Where things live

| What | Where |
|---|---|
| Setting catalog (every setting + custom keycode) | `settings.toml` |
| Generated from it (commit both, never edit) | `settings_catalog.h`, `via.json` |
| Firmware settings store and VIA channel 42 | `settings.c` |
| Behaviors that read settings | `keymap.c` (`eli_settings.<field>`) |
| CLI, generator, cheat sheet renderer, tests | `tools/` (uv project, `ploopy_tools/`) |
| Mouse config, cheat sheet labels and template | `~/dotfiles/ploopy/.config/ploopy/` |
| Plug-in hook (Voxtype restart + auto-apply) | `~/dotfiles/ploopy/` (see its README.md) |

## Change a value or a button

This needs no build. Run `ploopy set <setting> <value>` (for example
`ploopy set niri.flick_threshold 240`). It writes the mouse and the mouse
config, then redraws the cheat sheet. For buttons, edit `[layers.N]` in the
mouse config and run `ploopy apply`. `ploopy --help` lists the commands; the
catalog lists the settings and their ranges.

## Add a setting

1. Add a `[[setting]]` to `settings.toml` with the next unused `id`. Ids are
   stable: never reuse or renumber one, because channel-42 settings are stored
   in id order and a new one must append.
2. Regenerate: `uv run --project tools python -m ploopy_tools.gen`.
3. Use it in firmware as `eli_settings.<name with dots as underscores>`. If
   hardware holds the value, push it in `settings_apply()`.
4. Add the setting to the mouse config (`load_config` rejects a config that
   lacks one), and mention it in the cheat sheet template if Eli should see
   it.
5. Build, flash, and check that `ploopy get <name>` returns the default.

Done when the tests pass, `gen --check` exits 0, and `ploopy diff` is clean
on the flashed mouse.

## Add a keycode or behavior

1. Append a `[[keycode]]` to `settings.toml`. Values are assigned from
   `QK_KB_2` in list order, so append only: reordering changes the codes
   stored on the mouse. Regenerate.
2. Handle it in `process_record_user()` in `keymap.c`. Expose its tuning
   values as settings (see above) so they can change without a reflash.
3. Add a label for it in `~/dotfiles/ploopy/.config/ploopy/labels.toml`, and
   update `cheatsheet.json.j2` if its text depends on settings or its
   position.
4. Build and flash, then `ploopy apply`. Have Eli load the regenerated
   `via.json` in VIA (Design tab) if the VIA panel or key names changed.

## Build, flash, test

- **Tests** (run after any `tools/` or `settings.toml` change):
  `uv run --project tools pytest tools/tests -q` and
  `uv run --project tools python -m ploopy_tools.gen --check`.
- **Build** (repository root):

      docker run --rm -v $PWD:/qmk_firmware -w /qmk_firmware -u $(id -u):$(id -g) \
        -e HOME=/tmp ghcr.io/qmk/qmk_cli qmk compile -kb ploopyco/aplus/rev2_001 -km eli

  This keymap lives on branch `eli-aplus` of Ploopy's fork. `modules/drashna`
  must be a clone of drashna/qmk_modules.
- **Flash:** ask Eli to press the right wheel (Control layer), then Bottom
  Left (`QK_BOOT`). The `RPI-RP2` drive does not automount: run
  `udisksctl mount -b "$(readlink -f /dev/disk/by-label/RPI-RP2)"`, then copy
  `ploopyco_aplus_rev2_001_eli.uf2` to the mount point it prints. The stock rollback image is `ploopyco_aplus_stock.uf2` in the
  repository root.
- **After a flash:** the plug-in hook re-applies the mouse config if the
  button map was reset. Check it with
  `journalctl --user -u ploopy-plugged` and `ploopy diff`.

## Gotchas

These were all verified on the hardware:

- **A reflash built on a different UTC day resets the button map** to
  `keymap.c`, because VIA's EEPROM magic is the build date. Settings
  survive. The plug-in hook restores the button map: the apply marker
  (value id 254 on channel 42) stops matching the build stamp. A same-day
  reflash changes nothing. Test a reset with `-e SKIP_VERSION=yes` (build
  date 1970).
- **Holding Left click while plugging in** runs bootmagic, which wipes all
  settings. The hook restores those too.
- **`VIA_EEPROM_CUSTOM_CONFIG_SIZE` (128) is fixed.** Changing it moves the
  dynamic keymap. `via_init_kb()` resets the keymap cleanly when the settings
  store is missing, but every stored button is lost.
- **One VIA handler for everything.** QMK has no hook chain for VIA custom
  values, so `via_custom_value_command_kb()` in `settings.c` passes channel
  24 to the accel module and handles channel 42 itself.
- **VIA and `ploopy` share replies.** hidraw copies every reply to every open
  handle. `ploopy` skips replies that aren't its own, but VIA does not: after
  running `ploopy` while usevia.app is connected, VIA can fall one reply
  behind ("Receiving incorrect response"). Reloading the VIA tab fixes it.
- **Use hidapi's `hidraw` module.** The `hid` module is the libusb backend
  and reports usage page 0. In hidraw, `read(n, 0)` means "no timeout": it
  blocks.
- **Accel values read back one slider step low**, because the module
  truncates when it projects. `diff` allows ±1 step.
- **The board's `DPI Config` keycode (`QK_KB_0`) bypasses `pointer.dpi`.**
  Use `PKC_BLINKY_DPI_CONFIG`. `QK_KB_0` and `QK_KB_1` stay in `via.json`
  only as index placeholders.
