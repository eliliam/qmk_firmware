# Runtime Configuration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the A+ button map and every tuning value changeable at runtime, through VIA or a `ploopy` CLI, with a dotfiles **mouse config** as the source of truth.

**Architecture:** A TOML **setting catalog** in the keymap folder is the one list of settings and custom keycodes. A Python generator turns it into a C header (firmware) and a VIA definition (GUI). The firmware keeps all settings in VIA's custom EEPROM area and answers VIA custom-value commands on its own channel. A Python CLI speaks the same raw HID protocol to diff, apply, pull, get and set. A udev-triggered user unit restarts Voxtype and auto-applies after a reset or wipe.

**Tech Stack:** QMK (Ploopy fork, branch `eli-aplus`, C, Docker `ghcr.io/qmk/qmk_cli`), Python ≥3.12 via a uv project (`hidapi`, `tomlkit`, `jinja2`, `pytest`), udev + systemd user units, GNU stow.

**Spec:** `keyboards/ploopyco/aplus/keymaps/eli/docs/specs/2026-10-21-runtime-config-design.md` and `keyboards/ploopyco/aplus/keymaps/eli/GLOSSARY.md`.

Paths below are relative to `keyboards/ploopyco/aplus/keymaps/eli/` (written `eli/`) unless they start with `~` or are repo-root paths.

## Global Constraints

- Firmware stays on Ploopy's QMK fork, branch `eli-aplus`, target `ploopyco/aplus/rev2_001`, keymap `eli`. No Vial.
- Build command (repo root): `docker run --rm -v $PWD:/qmk_firmware -w /qmk_firmware -u $(id -u):$(id -g) -e HOME=/tmp ghcr.io/qmk/qmk_cli qmk compile -kb ploopyco/aplus/rev2_001 -km eli`.
- The firmware build never reads from `~/dotfiles`. Generated files (`settings_catalog.h`, `via.json`, `tools/keycodes.json`) are committed.
- Do **not** build with `SKIP_VERSION` for normal builds.
- USB IDs: vendor `0x5043`, product `0x81DB`. Raw HID: usage page `0xFF60`, usage `0x61`, 32-byte reports; with hidapi, prepend a `0x00` report id on write.
- VIA protocol commands: `0x01` version, `0x04` get keycode `[0x04,layer,row,col]` → bytes 4-5 BE, `0x05` set keycode `[0x05,layer,row,col,hi,lo]`, `0x07` custom set, `0x08` custom get, `0x09` custom save (`[cmd,channel,value_id,data…]`), `0x11` layer count. Byte 0 `0xFF` = unhandled.
- Our VIA channel is **42**. The accel module's channel is **24** (value ids 1 takeoff, 2 growth rate, 3 offset, 4 limit, 5 enabled; 2-byte values projected linearly from 0..60000 onto takeoff 0..5, growth 0.01..5, offset 0..15, limit 0..1).
- Value id **254** on channel 42 is the apply marker (not a setting).
- `VIA_EEPROM_CUSTOM_CONFIG_SIZE` = **128** (with `VIA_EEPROM_CUSTOM_CONFIG_ERROR_OVERRIDE`). Accel uses offsets 0-19; our store starts at offset **20**.
- Positions, in `LAYOUT()` order, map to matrix row 0 columns: `TLL`=1, `TL`=2, `TR`=3, `TRR`=4, `BL`=0, `BR`=5, `LW`=6, `RW`=7. 8 layers.
- Firmware defaults equal today's values: Niri 200 / 250 / 200 ms, drag scroll divisors 0.8 / 0.24, both scroll-arrow toggles off, Bottom Right = middle click, LED brightness 4, DPI 900, accel on with takeoff 2.0, growth 0.25, offset 2.2, limit 0.2.
- Custom keycodes (`PKC_*`) move to `QK_KB_2` onward (the board owns `QK_KB_0` DPI_CONFIG and `QK_KB_1` DRAG_SCROLL). The `PKC_UNUSED_*` entries are dropped.
- Mouse config TOML stores real-world values (DPI 900, divisor 0.8, takeoff 2.0) and keycodes as QMK names.
- Dotfiles package: `~/dotfiles/ploopy/` in stow layout (`.config/ploopy/…`, `.local/bin/ploopy`, `.config/systemd/user/…`). The CLI writes through `~/.config/ploopy` in place; it never replaces files by rename.
- Any error while validating input means nothing is written to the mouse or the file.
- Use `sudo -A` for root commands.

## Review Focus

1. **First boot of the new firmware over old EEPROM data:** the store magic is wrong and the accel floats may be zero or garbage. Expected: every setting is at its firmware default, accel is not NaN, and the marker reads invalid. Test: T3 Step 6 (hardware), T4 `test_marker_invalid_on_fresh_store`.
2. **Unplugged mouse, or no hidraw permission:** expected one clear error line naming the cause, exit code 2, and no traceback. Test: T5 `test_no_device_message`.
3. **Mouse config hand-edited with a typo** (unknown setting, out-of-range value, unknown keycode): expected an error naming the TOML path and nothing written. Test: T5 `test_invalid_config_writes_nothing`.
4. **Accel float round trip:** pull then diff must show no drift caused only by projection rounding. Test: T1 `test_accel_roundtrip_within_one_step`, T5 `test_pull_then_diff_clean`.
5. **Mouse config is a stow symlink target:** `set` and `pull` must keep comments and must not replace the symlinked file. Test: T5 `test_set_preserves_comments_and_symlink`.

---

### Task 1: Setting catalog, loader, and generator

**Files:**
- Create: `eli/settings.toml` (the setting catalog)
- Create: `eli/tools/pyproject.toml` (uv project `ploopy-tools`, script entry `ploopy = "ploopy_tools.cli:main"`, deps `hidapi`, `tomlkit`, `jinja2`; dev dep `pytest`)
- Create: `eli/tools/ploopy_tools/__init__.py`, `eli/tools/ploopy_tools/catalog.py`, `eli/tools/ploopy_tools/gen.py`
- Create (generated, committed): `eli/settings_catalog.h`, `eli/via.json`
- Test: `eli/tools/tests/test_catalog.py`, `eli/tools/tests/test_gen.py`

**Interfaces:**
- Produces, in `catalog.py`:
  - `class CatalogError(Exception)`
  - `@dataclass(frozen=True) class Setting`: `name: str` (dotted, such as `niri.flick_threshold`), `id: int`, `channel: int`, `type: Literal["u8","u16","bool","enum","accel"]`, `min: float`, `max: float`, `default: int | float | bool | str`, `label: str`, `group: str`, `options: tuple[str, ...] = ()`, `scale: float = 1.0`, `step: int = 1`. Methods: `validate(value) -> None` (raises `ValueError` with the setting name), `encode(value) -> bytes`, `decode(data: bytes) -> int | float | bool | str`, `size -> int` (property), `c_name -> str` (property, dots to underscores).
  - `@dataclass(frozen=True) class Keycode`: `name: str`, `value: int`, `label: str`.
  - `@dataclass(frozen=True) class Catalog`: `channel: int`, `store_offset: int`, `custom_config_size: int`, `settings: tuple[Setting, ...]`, `keycodes: tuple[Keycode, ...]`; `setting(name) -> Setting` (raises `KeyError`).
  - `load_catalog(path: Path) -> Catalog`, `CATALOG_PATH: Path` (resolves to `eli/settings.toml` from the package location).
- Produces, in `gen.py`: `render_header(cat: Catalog) -> str`, `render_via(cat: Catalog, info_json: dict, accel_menu: dict) -> dict`, `main(argv) -> int` (`--check` exits 1 if committed outputs differ).

The catalog format:

```toml
channel = 42
store_offset = 20
custom_config_size = 128

[[keycode]]            # values are QK_KB_2 (0x7E02) onward, in this order
name = "PKC_TGL_VERT_SCRL"
label = "Toggle vertical scroll arrows"

[[setting]]
name = "niri.flick_threshold"
id = 1                 # VIA value id on `channel`; stable, never reused, append-only
type = "u16"
min = 20
max = 2000
default = 200
label = "Flick threshold (counts per step)"
group = "Niri navigation"
```

Settings, in id order (ids on channel 42; the `accel` rows use `channel = 24`):

| id | name | type | range | default | notes |
|---|---|---|---|---|---|
| 1 | niri.flick_threshold | u16 | 20–2000 | 200 | |
| 2 | niri.tap_term | u16 | 50–1000 | 250 | ms |
| 3 | niri.idle_reset | u16 | 50–2000 | 200 | ms |
| 4 | drag_scroll.divisor_h | u16 | 5–1000 | 80 | `scale = 0.01`, so the config shows 0.8 (lower = faster) |
| 5 | drag_scroll.divisor_v | u16 | 5–1000 | 24 | `scale = 0.01` |
| 6 | wheels.vertical_arrows | bool | | false | |
| 7 | wheels.horizontal_arrows | bool | | false | |
| 8 | bottom_right.mode | enum | middle_click, drag_scroll | middle_click | |
| 9 | led.brightness | u8 | 1–4 | 4 | |
| 10 | pointer.dpi | u16 | 100–12000 | 900 | `step = 100` |
| 5 @24 | accel.enabled | bool | | true | |
| 1 @24 | accel.takeoff | accel | 0.5–5 | 2.0 | the projection uses the module's 0–5 |
| 2 @24 | accel.growth_rate | accel | 0.01–5 | 0.25 | |
| 3 @24 | accel.offset | accel | 0–15 | 2.2 | |
| 4 @24 | accel.limit | accel | 0–1 | 0.2 | |

Keycodes, in order: `PKC_TGL_VERT_SCRL`, `PKC_TGL_HORIZ_SCRL`, `PKC_NIRI`, `PKC_ADJUST_LED_BRIGHTNESS`, `PKC_BLINKY_DPI_CONFIG`, `PKC_TGL_BOTTOM_RIGHT`, `PKC_BOTTOM_RIGHT`.

The `accel` type needs its own projection range, separate from the validation range. Store it as `via_min` / `via_max` keys on those rows (takeoff 0/5, growth 0.01/5, offset 0/15, limit 0/1) and add `via_min: float | None`, `via_max: float | None` to `Setting`.

- [ ] **Step 1: Write failing tests** in `test_catalog.py`:
  - `test_loads_all_settings`: `load_catalog(CATALOG_PATH)` has 15 settings and 7 keycodes; `cat.setting("pointer.dpi").default == 900`; `cat.keycodes[2] == Keycode("PKC_NIRI", 0x7E04, ...)`.
  - `test_u16_encode_big_endian`: `cat.setting("pointer.dpi").encode(900) == bytes([0x03, 0x84])`.
  - `test_scale`: `s = cat.setting("drag_scroll.divisor_h")`; `s.encode(0.8) == bytes([0, 80])`; `s.decode(bytes([0, 24])) == 0.24`.
  - `test_enum`: `bottom_right.mode` encodes `"drag_scroll"` to `b"\x01"` and decodes `b"\x00"` to `"middle_click"`.
  - `test_validate_rejects`: DPI 50 and 150 (not a multiple of `step`), takeoff 0.4, an unknown enum option, and `True` for a u16 each raise a `ValueError` whose message contains the setting name.
  - `test_accel_roundtrip_within_one_step`: for each accel setting and the values 0.5, 2.0, 2.2, 0.25 and 0.2 (where they're in range), `abs(s.decode(s.encode(v)) - v) <= (s.via_max - s.via_min) / 60000`, and `decode` rounds to 4 decimals.
  - `test_ids_unique_per_channel` and `test_store_fits`: the sum of channel-42 setting sizes plus 5 header bytes is at most `custom_config_size - store_offset`.
- [ ] **Step 2: Run** `uv run --project eli/tools pytest eli/tools/tests -q`. Expected: FAIL (module missing).
- [ ] **Step 3: Implement `catalog.py` and write `settings.toml`** with the table above. The loader rejects duplicate ids per channel, duplicate names, and a default outside its range (`CatalogError`).
- [ ] **Step 4: Run the tests.** Expected: PASS.
- [ ] **Step 5: Write failing tests** in `test_gen.py`:
  - `test_header_has_struct_and_ids`: `render_header(cat)` contains `#define ELI_SETTINGS_CHANNEL 42`, `#define ELI_SETTINGS_STORE_OFFSET 20`, `#define ELI_SETTINGS_MARKER_ID 254`, an `X(niri_flick_threshold, 1, uint16_t, 200, 20, 2000)` row in an `ELI_SETTINGS(X)` X-macro (channel-42 settings only; bool and enum rows use `uint8_t`; scaled rows hold raw integers such as `80`), and `PKC_NIRI = QK_KB_4`.
  - `test_via_definition`: `render_via(...)` has `vendorId "0x5043"`, `productId "0x81DB"`, `matrix {rows 1, cols 8}`, `layouts.keymap` built from `info.json`'s LAYOUT x/y/w/h with `"0,col"` legends, `customKeycodes` with 9 entries (`DPI Config`, `Drag Scroll`, then the 7 PKC keycodes by label, in order), and a menu with one section per `group` plus the accel module's section. Controls: u8/u16 → `range` with `[min, max]`, bool → `toggle`, enum → `dropdown` with `[label, index]` options, content `[ "id_<c_name>", channel, id ]`.
  - `test_check_detects_stale`: with a temporary copy of the outputs edited, `main(["--check", ...])` returns 1.
- [ ] **Step 6: Run.** Expected: FAIL.
- [ ] **Step 7: Implement `gen.py`.** `info.json` has trailing commas, so strip them with a regex before `json.loads`. `accel_menu` is read from `modules/drashna/pointing_device_accel/assets/via.json`. The header also emits a packed `eli_settings_t` with `uint8_t magic; uint8_t length; uint8_t marker[3];` followed by the fields in id order, plus `#define ELI_SETTINGS_MAGIC 0xE1`. The header gets a banner saying it's generated from `settings.toml` by `tools/ploopy_tools/gen.py`.
- [ ] **Step 8: Generate** with `uv run --project eli/tools python -m ploopy_tools.gen`, then run all tests. Expected: PASS, and `--check` returns 0.
- [ ] **Step 9: Commit** with `git add eli/settings.toml eli/tools eli/settings_catalog.h eli/via.json` and `git commit -m "ploopyco/aplus: add eli setting catalog and generator"`.

---

### Task 2: Keycode table and codec

**Files:**
- Create (generated, committed): `eli/tools/keycodes.json`
- Create: `eli/tools/ploopy_tools/keycodes.py`
- Test: `eli/tools/tests/test_keycodes.py`

**Interfaces:**
- Consumes: `Catalog.keycodes` (Task 1).
- Produces: `class KeycodeError(ValueError)`; `class Codec`: `Codec(table: dict, catalog: Catalog)`, `Codec.load(catalog) -> Codec` (reads `tools/keycodes.json`), `encode(name: str) -> int`, `decode(code: int) -> str`.

- [ ] **Step 1: Generate `keycodes.json`** from QMK's merged spec:
  `docker run --rm -v $PWD:/qmk_firmware -w /qmk_firmware -u $(id -u):$(id -g) -e HOME=/tmp -e PYTHONPATH=lib/python ghcr.io/qmk/qmk_cli python3 -c "import json; from qmk.keycodes import load_spec; print(json.dumps(load_spec('0.0.8'), indent=1, sort_keys=True))" > keyboards/ploopyco/aplus/keymaps/eli/tools/keycodes.json`.
  Then add the accel module keycodes `MA_TOGG, MA_TKOF, MA_GROW, MA_OFST, MA_LMT` = 0x77C0–0x77C4 to the codec as a constant, read in order from `modules/drashna/pointing_device_accel/qmk_module.json`. Add the board's `DPI_CONFIG` = 0x7E00 and `DRAG_SCROLL` = 0x7E01 the same way.
- [ ] **Step 2: Write failing tests**, using parametrized pairs, with each pair checked in both directions:
  - `("MS_BTN1", …)` and `("KC_TRNS", 0x0001)`. `"_______"` encodes to 1, and 1 decodes to `"KC_TRNS"`.
  - `("HYPR(KC_LEFT)", 0x0F50)`, `("MEH(KC_SPC)", 0x072C)`, `("LCTL(KC_A)", 0x0104)`.
  - `("TG(1)", QK_TOGGLE_LAYER | 1)`, `("MO(2)", …)`, `("LT(1,KC_A)", 0x4104)`. Take the base values from `keycodes.json` ranges.
  - `("QK_BOOT", …)`, `("PKC_NIRI", 0x7E04)`, `("MA_TOGG", 0x77C0)`, `("DPI_CONFIG", 0x7E00)`.
  - Unknown code: `decode(0x7FFF) == "0x7FFF"` and `encode("0x7FFF") == 0x7FFF`.
  - `encode("KC_NOPE")` raises `KeycodeError` naming `KC_NOPE`.
  - The canonical decode of an alias is the spec's primary `key` (for example `decode(0x29) == "KC_ESCAPE"`), and encoding accepts aliases (`"KC_ESC"`).
- [ ] **Step 3: Run.** Expected: FAIL.
- [ ] **Step 4: Implement `Codec`.** Decode order: an exact table entry, then a custom or module keycode, then the modifier wrappers (`HYPR` 0x0F00, `MEH` 0x0700, and the `LCTL/LSFT/LALT/LGUI/RCTL/RSFT/RALT/RGUI` bits from `quantum_keycodes.h:27-32`; on decode, prefer `HYPR` and `MEH` when the bits match), then the layer functions `TO MO DF TG OSL TT` and `LT(layer,kc)`, then hex.
- [ ] **Step 5: Run.** Expected: PASS.
- [ ] **Step 6: Commit** with `git commit -m "ploopyco/aplus: add keycode codec for eli tools"`.

---

### Task 3: Firmware settings store and VIA channel

**Files:**
- Create: `eli/settings.c`, `eli/settings.h`
- Modify: `eli/keymap.c` (replace `user_config`, the custom keycode enum, the Niri `#define` uses, the DPI cycle, LED brightness and init)
- Modify: `eli/config.h` (custom config size, drag-scroll divisor macros, remove `NIRI_*` constants)
- Modify: `eli/rules.mk` (`SRC += settings.c`, `POINTING_DEVICE_ACCEL_VIA_ENABLE = yes`)

**Interfaces:**
- Consumes: `settings_catalog.h` (Task 1): `eli_settings_t`, `ELI_SETTINGS(X)`, `ELI_SETTINGS_*` macros, and the `PKC_*` enum.
- Produces, in `settings.h`:
  - `extern eli_settings_t eli_settings;`
  - `void settings_init(void);` loads at boot, migrates, and applies.
  - `void settings_reset(void);` resets to defaults, clears the marker, resets accel to defaults, and saves.
  - `void settings_save(void);`
  - `void settings_apply(void);` pushes values to hardware: DPI via `pointing_device_set_cpi`, LED via `rgblight_sethsv_noeeprom(0, 0, RGBLIGHT_VAL_STEP * brightness)`.
  - `float eli_dragscroll_divisor_h(void); float eli_dragscroll_divisor_v(void);`
  - `void via_custom_value_command_kb(uint8_t *data, uint8_t length);` (strong).

Behavior to pin:
- **Load:** read `sizeof(eli_settings_t)` bytes at `ELI_SETTINGS_STORE_OFFSET` with `via_read_custom_config`.
  - If `magic != ELI_SETTINGS_MAGIC` or `length < 5`: call `settings_reset()`.
  - Else if `length < sizeof`: keep the first `length` bytes, fill the newer fields with defaults, set `length = sizeof`, and save. That is the append-only migration.
  - Then clamp every field to its catalog range; out of range means default.
- **Accel sanity:** in `keyboard_post_init_pointing_device_accel_kb()`, if any accel float is NaN or outside its module range, or takeoff < 0.5, call `eeconfig_init_pointing_device()`.
- **Wipe:** `eeconfig_init_user()` calls `settings_reset()`.
- **Channel 42 handler:**
  - set (0x07) decodes BE by field size, clamps, assigns, and calls `settings_apply()`;
  - get (0x08) writes BE;
  - save (0x09) calls `settings_save()`;
  - an unknown id gets `id_unhandled`.
  - Channel 24 goes to `via_custom_value_command_accel`. Every other channel gets `data[0] = id_unhandled`.
- **Marker (id 254):** `marker` stores the 3-byte build stamp, made the same way `via.c:70-82` makes its magic from `QMK_BUILDDATE`.
  - get returns `1` if `marker` equals the current stamp, else `0`.
  - set stores the current stamp and saves (payload ignored).
- **Control layer:**
  - The scroll-arrow and Bottom Right toggles, and LED brightness, change `eli_settings` and call `settings_save()`. They keep their current blink feedback.
  - `PKC_BLINKY_DPI_CONFIG` sets `pointer_dpi` to the next preset in {600, 900, 1200, 1600, 2400} that is strictly greater than the current value, wrapping to 600. It applies, saves, and blinks (preset index + 1) times.
  - The board's `cycle_dpi()` is no longer called.
- **DPI at boot:** `settings_init()` runs from `keyboard_post_init_user()`, after the board code has set its own DPI, and overrides it.
- **Drag scroll:** `config.h` defines `PLOOPY_DRAGSCROLL_DIVISOR_H eli_dragscroll_divisor_h()` (and V), with the prototypes declared in `config.h` under `#if !defined(__ASSEMBLER__)`, so that `keyboards/ploopyco/ploopyco.c` compiles unchanged.

- [ ] **Step 1: Make the edits above.** Keep the comment style of `keymap.c`, and update its header comment block (settings now live in the catalog).
- [ ] **Step 2: Build** with the Global Constraints command. Expected: `ploopyco_aplus_rev2_001_eli.uf2` is produced with no warnings from `eli/` files.
- [ ] **Step 3: Check the symbols:** `grep -c via_custom_value_command_accel .build/ploopyco_aplus_rev2_001_eli.map` is at least 1.
- [ ] **Step 4: Commit** with `git commit -m "ploopyco/aplus: store eli settings in VIA custom config"`.

(Task 7 does the hardware checks. Review Focus item 1 is checked there: Step 6.)

---

### Task 4: CLI protocol layer

**Files:**
- Create: `eli/tools/ploopy_tools/protocol.py`
- Create: `eli/tools/tests/fake_mouse.py` (an in-memory firmware emulator for tests)
- Test: `eli/tools/tests/test_protocol.py`

**Interfaces:**
- Consumes: `Catalog`, `Setting.encode/decode/size` (Task 1).
- Produces:
  - `class MouseError(Exception)`, `class NoDeviceError(MouseError)`.
  - `class Transport(Protocol)`: `exchange(packet: bytes) -> bytes` (32 bytes in, 32 out).
  - `class HidTransport`: `open() -> HidTransport` finds the interface with usage page 0xFF60 and usage 0x61 for 0x5043:0x81DB. It raises `NoDeviceError("Ploopy A+ not found: is it plugged in, and does udev grant hidraw access?")`. The timeout is 1000 ms.
  - `POSITIONS: dict[str, int]` (position name → matrix column, from Global Constraints).
  - `class Mouse(transport)`:
    - `protocol_version() -> int`, `layer_count() -> int`
    - `get_keycode(layer, col) -> int`, `set_keycode(layer, col, code)`
    - `get_setting(s: Setting) -> value`, `set_setting(s: Setting, value)`, `save(channel: int)`
    - `marker_valid() -> bool`, `set_marker()`
  - Every reply is checked: byte 0 must echo the command, and `0xFF` raises `MouseError("unhandled: …")`.
- `FakeMouse` implements `Transport`. It holds 8×8 keycodes, a dict of channel 42 and 24 values, a `saved` copy, and a `marker` flag. It answers like the firmware.

- [ ] **Step 1: Write failing tests:** `test_version`, `test_keycode_roundtrip` (`set_keycode(1, POSITIONS["BL"], 0x7C00)` then get), `test_setting_roundtrip_each_type` (u16, scaled, bool, enum and accel), `test_save_sends_channel`, `test_unhandled_raises`, `test_marker_invalid_on_fresh_store` (a new `FakeMouse()` gives `marker_valid() is False`, and after `set_marker()` it's `True`), `test_packets_are_32_bytes`.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.** `HidTransport.exchange` writes `b"\x00" + packet` and reads 32 bytes.
- [ ] **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Commit** with `git commit -m "ploopyco/aplus: add VIA raw HID protocol for eli tools"`.

---

### Task 5: Mouse config and the `ploopy` commands

**Files:**
- Create: `eli/tools/ploopy_tools/mouseconfig.py`, `eli/tools/ploopy_tools/cli.py`
- Test: `eli/tools/tests/test_mouseconfig.py`, `eli/tools/tests/test_cli.py`

**Interfaces:**
- Consumes: Tasks 1, 2 and 4. `render_cheatsheet` from Task 6 is called through `cli.py` but stubbed in this task's tests.
- Produces:
  - `@dataclass class MouseState`: `settings: dict[str, value]`, `layers: dict[int, dict[str, str]]` (all 8 layers, all 8 positions, as QMK names).
  - `class ConfigError(ValueError)`: its message starts with the TOML path, for example `settings.niri.flick_threshold`.
  - `read_state(mouse, cat, codec) -> MouseState`
  - `load_config(path, cat, codec) -> MouseState` validates everything before returning. A missing setting is a `ConfigError`. A missing layer or position means `KC_TRNS`.
  - `@dataclass class Difference`: `path: str`, `mouse: str`, `config: str`. `diff(mouse: MouseState, config: MouseState) -> list[Difference]`. Accel values count as equal within one projection step.
  - `write_state(mouse, target: MouseState, current: MouseState, cat, codec) -> int` writes only the differences, saves each touched channel once, and returns the number of writes.
  - `save_config(path, state, cat)` updates values in the existing tomlkit document in place, keeping comments. It writes by opening the path for writing, so a symlink stays a symlink. It drops layers that are all `KC_TRNS`.
  - `cli.main(argv) -> int` with subcommands `diff`, `apply`, `pull`, `get NAME`, `set NAME VALUE`, `on-plug`, and the global options `--config PATH` (default `$PLOOPY_CONFIG` or `~/.config/ploopy/mouse.toml`).
  - The cheat sheet files sit next to the config: `labels.toml`, `cheatsheet.json.j2`, and the output `cheatsheet.html`.
  - Note: the spec said "single-file script with inline dependencies". This plan uses a small uv project instead, so the generator, codec, protocol and CLI can be tested separately. The `uv run` invocation is unchanged in spirit.

Mouse config shape:

```toml
[settings.niri]
flick_threshold = 200
tap_term = 250
idle_reset = 200
# … one table per group prefix, all 15 settings

[layers.0]
TLL = "MS_BTN4"
TL = "MS_BTN5"
TR = "MEH(KC_SPC)"
TRR = "MS_BTN2"
BL = "MS_BTN1"
BR = "PKC_BOTTOM_RIGHT"
LW = "PKC_NIRI"
RW = "TG(1)"
```

Command behavior:
- `diff` prints one `path: mouse=X config=Y` line per difference. Exit 0 if clean, 1 if there's drift.
- `apply`: load the config (a validation failure means nothing is written), read the state, write the differences, set the marker, render the cheat sheet, and print the number of writes.
- `pull`: read the state, `save_config`, and render the cheat sheet.
- `get NAME` prints the value.
- `set NAME VALUE` parses VALUE by type (`true`/`false`, enum option, number), validates it, writes and saves it on the mouse, updates that one key with `save_config`, and renders the cheat sheet.
- `on-plug`:
  1. Run `systemctl --user restart voxtype`; a failure is logged, not fatal.
  2. Retry opening the device for up to 10 s.
  3. If `marker_valid()` is false, run `apply` and `notify-send "Ploopy" "Restored mouse config after reset"`.
  4. On any error, `notify-send -u critical "Ploopy" "<error>"` and exit 1.
- A `MouseError`, `ConfigError` or `KeycodeError` prints `ploopy: <message>` to stderr and exits 2, with no traceback.

- [ ] **Step 1: Write failing tests**, using `FakeMouse` and `tmp_path`:
  - `test_read_state_names` (layer 0 BR reads back as `"PKC_BOTTOM_RIGHT"`)
  - `test_diff_lists_drift`
  - `test_apply_writes_only_changes` (a second apply makes 0 writes)
  - `test_apply_sets_marker`
  - `test_pull_then_diff_clean`
  - `test_invalid_config_writes_nothing` (unknown setting, DPI 50, and keycode `KC_NOPE` each exit 2 with the TOML path in stderr, and the `FakeMouse` write count stays 0)
  - `test_set_preserves_comments_and_symlink` (the config is a symlink to a file with comments; after `set niri.flick_threshold 240`, the link is still a link, the comments are intact, and the value is 240 on both the mouse and the file)
  - `test_no_device_message` (the transport factory raises `NoDeviceError`; output has one line, the exit code is 2, and there's no "Traceback")
  - `test_on_plug_applies_only_when_marker_invalid` (patch `subprocess.run`, then assert the `notify-send` call and that a valid marker leads to no writes)
  - `cli.main` takes an injectable `transport_factory` and `run` (subprocess) for the tests.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Commit** with `git commit -m "ploopyco/aplus: add ploopy diff/apply/pull/get/set"`.

---

### Task 6: Cheat sheet rendering

**Files:**
- Create: `eli/tools/ploopy_tools/cheatsheet.py`
- Create: `eli/tools/ploopy_tools/drawing.html`: the drawing code and styles from today's `eli/keymap.html`, with the `KEYMAP` JSON block replaced by a `__KEYMAP_JSON__` slot
- Test: `eli/tools/tests/test_cheatsheet.py`

**Interfaces:**
- Consumes: `MouseState`, `Catalog`.
- Produces: `render_cheatsheet(state: MouseState, cat: Catalog, template: Path, labels: Path, out: Path) -> None`.
  - The template is a Jinja2 file that renders the `KEYMAP` JSON (the schema in the `keymap.html` header comment). Its context:
    - `s`: setting name → display value
    - `key(layer, pos)`: `{name, label, detail}` from the labels table, falling back to `{name, label: name, detail: ""}`
    - `layers`: layers that are not all `KC_TRNS`
    - `today`
  - The labels table is TOML: `[MS_BTN1] label = "Left\nClick"`, `detail = "…"`.
  - The rendered JSON is checked with `json.loads` before it's written; a template error raises `ConfigError`. The output is written into `drawing.html`'s slot.
  - A missing template or labels file skips rendering and prints a warning. It is not an error.

- [ ] **Step 1: Write failing tests:**
  - `test_label_fallback` (an unknown keycode shows its QMK name)
  - `test_setting_in_text` (a template quoting `{{ s["niri.flick_threshold"] }}` renders `240` after a change)
  - `test_empty_layers_skipped`
  - `test_bad_template_raises`
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Commit** with `git commit -m "ploopyco/aplus: render eli cheat sheet from mouse config"`.

---

### Task 7: Dotfiles package, hook, flash and hardware check

**Files (in `~/dotfiles`, a separate git repo):**
- Create: `ploopy/.config/ploopy/mouse.toml`: today's button map (layer 0 and layer 1 from `keymap.c`) and every setting at its firmware default, with a short comment on each group.
- Create: `ploopy/.config/ploopy/labels.toml`: every label and detail in today's `keymap.html`, keyed by keycode.
- Create: `ploopy/.config/ploopy/cheatsheet.json.j2`: today's `keymap.html` KEYMAP data turned into a template. The setting-dependent text uses `s[...]` (the Niri instructions, Bottom Right text by `bottom_right.mode`, wheel turn text by the scroll-arrow settings), and there's a generic panel loop for any non-empty layer above 1.
- Create: `ploopy/.local/bin/ploopy`, a POSIX `sh` wrapper: `exec uv run --quiet --project "$PLOOPY_TOOLS" ploopy "$@"`, where `PLOOPY_TOOLS` defaults to `$HOME/Source/qmk_firmware/keyboards/ploopyco/aplus/keymaps/eli/tools`.
- Create: `ploopy/.config/systemd/user/ploopy-plugged.service` (`Type=oneshot`, `ExecStart=%h/.local/bin/ploopy on-plug`)
- Create: `ploopy/udev/72-ploopy-aplus-config.rules` (not stowed): `SUBSYSTEM=="hidraw", ATTRS{idVendor}=="5043", ATTRS{idProduct}=="81db", TAG+="uaccess", TAG+="systemd", ENV{SYSTEMD_USER_WANTS}+="ploopy-plugged.service"`. Use `udevadm info` to limit it to the raw HID interface if more than one hidraw node appears, so the unit starts once.

- [ ] **Step 1: Create the files**, then run `stow -d ~/dotfiles -t ~ ploopy`. Install the rule with `sudo -A install -m644 ~/dotfiles/ploopy/udev/72-ploopy-aplus-config.rules /etc/udev/rules.d/` and `sudo -A udevadm control --reload`. Then run `systemctl --user daemon-reload`.
- [ ] **Step 2: Check the template offline:** `ploopy --help` works, and a test render against a `FakeMouse` state (`uv run … python -c`) writes `~/.config/ploopy/cheatsheet.html`. Open it in the browser pane and check that nothing overlaps.
- [ ] **Step 3: Flash the Task 3 firmware.** Ask Eli to press Control layer, then Bottom Left, and copy the UF2 to `RPI-RP2`.
- [ ] **Step 4: Verify auto-apply.** After re-enumeration, `journalctl --user -u ploopy-plugged` shows that Voxtype restarted and the config was applied, a notification appeared, and `ploopy diff` exits 0.
- [ ] **Step 5: Verify live settings.**
  - `ploopy set niri.flick_threshold 400` makes Niri steps visibly coarser, `mouse.toml` shows 400, and the cheat sheet quotes 400.
  - Set it back to 200.
  - A Control-layer DPI press shows up as drift in `ploopy diff`.
- [ ] **Step 6: Verify a fresh store.** The first boot above came from old EEPROM data: the pointer moves normally (accel is not NaN), and `ploopy get accel.takeoff` prints 2.0.
- [ ] **Step 7: Verify a same-day reflash.** Reflash the same UF2. The marker stays valid, so the hook doesn't apply (the journal says so). Then build once with `SKIP_VERSION=yes` (`qmk compile … -e SKIP_VERSION=yes`) and flash it. The marker is now invalid and auto-apply restores the config. Rebuild normally and flash back.
- [ ] **Step 8: Check VIA.** In Chromium, open usevia.app, go to the Design tab, untick "Use V2 definitions", and load `eli/via.json`. Check four things:
  1. The keymap shows the 8 buttons.
  2. `PKC_*` keys show their labels.
  3. The "Eli" settings panel and the accel panel move values live.
  4. `ploopy diff` then shows that drift.
  If `PKC_*` labels don't show, record what VIA displays in the plan's notes and fix `render_via`'s `customKeycodes` before continuing.
- [ ] **Step 9: Commit the dotfiles**, in `~/dotfiles`: `git add ploopy && git commit -m "ploopy: add A+ mouse config, cheat sheet and plug hook"`.

---

### Task 8: Documentation and cleanup

**Files:**
- Modify: `eli/AGENTS.md`. The "Keep keymap.html in sync" section becomes: when a keycode or behavior is added, update `settings.toml` and regenerate, add its label in `~/dotfiles/ploopy/.config/ploopy/labels.toml`, update the cheat sheet template, and run `ploopy apply`. Add how to add a setting (catalog row with a new id, never reuse ids, regenerate, use `eli_settings.<c_name>`) and the test command.
- Modify: the `keymap.c` header comment (point to `settings.toml`, `AGENTS.md`, and the spec).
- Delete: `eli/keymap.html` (moved to dotfiles).
- Modify: the memory note `~/.claude/projects/-home-eli-Source-qmk-firmware/memory/ploopy-aplus-setup.md`, covering the `ploopy` CLI, the auto-apply hook, VIA sideloading, the fact that a reflash resets only the button map and auto-apply restores it, and that tuning is now `ploopy set`.

- [ ] **Step 1: Make the edits**, then run `uv run --project eli/tools pytest eli/tools/tests -q` and `uv run --project eli/tools python -m ploopy_tools.gen --check`. Expected: all pass, exit 0.
- [ ] **Step 2: Commit** with `git commit -m "ploopyco/aplus: document eli runtime configuration"`.
