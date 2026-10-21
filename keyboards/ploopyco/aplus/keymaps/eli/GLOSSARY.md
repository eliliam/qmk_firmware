# Eli's A+ mouse

Eli's Ploopy A+ firmware and the tooling that changes its behavior while it is plugged in, without rebuilding or reflashing.

## Language

**Setting**:
A named value stored on the mouse that changes how a behavior acts, such as the Niri flick threshold or the Bottom Right mode.
_Avoid_: knob, option, parameter, tunable

**Button map**:
The keycode assigned to each button on each layer, as stored on the mouse.
_Avoid_: keymap (that word means the firmware source folder), layout, bindings

**Mouse config**:
The file in dotfiles that holds the full desired button map and every setting. It is the source of truth.
_Avoid_: profile, backup, snapshot

**Setting catalog**:
The single list that names every setting, with its range, firmware default and label. Everything else that knows about settings follows it.
_Avoid_: schema, registry, settings list

**Cheat sheet**:
Eli's visual reference showing what every button and wheel does on each layer.
_Avoid_: keymap.html, visual keymap, reference

**Firmware default**:
The value a setting or button takes when the mouse's stored state is empty or wiped.
_Avoid_: factory setting, reset value

**Reset**:
The mouse's button map falling back to firmware defaults, which a reflash built on a different day causes. Settings survive a reset.
_Avoid_: wipe (that is the bigger event)

**Wipe**:
Clearing all stored state, button map and settings both, back to firmware defaults. Holding Left click while plugging in causes one.
_Avoid_: reset, factory reset

**Auto-apply**:
An apply that runs by itself when the mouse is plugged in after a reset or wipe.

**Drift**:
A difference between what the mouse holds and what the mouse config says, usually from an edit in VIA.

**Apply**:
Writing the mouse config onto the mouse, replacing any drift.
_Avoid_: push, sync, flash

**Pull**:
Copying the mouse's current button map and settings into the mouse config, keeping drift on purpose.
_Avoid_: backup, export, sync
