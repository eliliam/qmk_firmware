# Eli's Ploopy A+ keymap: agent instructions

## Keep `keymap.html` in sync (required)

`keymap.html` is Eli's visual reference for this keymap. Eli relies on it when
they forget a binding. Update it in the same change as any change to what a
control does. The following count as such changes:

- `keymap.c`: a `LAYOUT()` entry, a custom keycode's behaviour, wheel turn or
  press handling, LED colours or blink counts, or EEPROM defaults such as
  scroll direction.
- `config.h`: a tunable that the sheet quotes, such as `NIRI_FLICK_THRESHOLD`
  or `NIRI_TAP_TERM`.
- A change that alters what the user sees, such as host bindings in Niri's
  `keybinds.kdl` for the Hyper chords the sheet lists.

How to update it:

1. Edit only the JSON in `<script type="application/json" id="KEYMAP">`. The
   comment at the top of the file describes the schema. The SVG drawing is
   generated from that data, so don't edit the drawing code to change labels.
2. Map `LAYOUT()` arguments to the sheet's position keys in this order:
   `TLL, TL, TR, TRR, BL, BR, LW, RW`. These are the four top buttons from
   left to right, then the bottom-left and bottom-right buttons, then the left
   and right wheels. Wheels have both `turn` and `press` entries.
3. A new layer gets its own `"buttons"` panel. A layer that is gone has its
   panel removed.
4. Set `"updated"` to today's date.
5. Open the file in a browser and check that nothing overlaps or clips. The
   viewBox grows to fit, but long lines should still use `\n` breaks.

Tell Eli in your summary that you updated the sheet. If a change has no
visible effect, say that the sheet didn't need changes.

## Build and flash

This keymap lives on branch `eli-aplus` of Ploopy's fork, and the target is
`rev2_001`. `modules/drashna` must be a clone of drashna/qmk_modules. Run the
build from the repository root:

    docker run --rm -v $PWD:/qmk_firmware -w /qmk_firmware -u $(id -u):$(id -g) \
      -e HOME=/tmp ghcr.io/qmk/qmk_cli qmk compile -kb ploopyco/aplus/rev2_001 -km eli

To flash, enter the bootloader with the Control layer's Bottom Left key
(`QK_BOOT`). That keeps the saved settings. Holding Left click while plugging
in also enters the bootloader, but bootmagic wipes the EEPROM. Copy the UF2 to
the `RPI-RP2` drive. The stock image to roll back to is
`ploopyco_aplus_stock.uf2` in the repository root.
