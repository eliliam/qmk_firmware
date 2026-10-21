// Generated from settings.toml by tools/ploopy_tools/gen.py. Do not edit.
#pragma once

#include <stdint.h>
#include "quantum_keycodes.h"

#define ELI_SETTINGS_CHANNEL 42
#define ELI_SETTINGS_STORE_OFFSET 20
#define ELI_SETTINGS_MARKER_ID 254
#define ELI_SETTINGS_MAGIC 0xE1

_Static_assert(VIA_EEPROM_CUSTOM_CONFIG_SIZE == 128, "VIA_EEPROM_CUSTOM_CONFIG_SIZE must match settings.toml");

/* X(field, value id, type, default, min, max), in id order. Values are the
   stored integers: scaled settings hold value / scale, bools 0/1, enums an
   option index. */
#define ELI_SETTINGS(X) \
    X(niri_flick_threshold, 1, uint16_t, 200, 20, 2000) \
    X(niri_tap_term, 2, uint16_t, 250, 50, 1000) \
    X(niri_idle_reset, 3, uint16_t, 200, 50, 2000) \
    X(drag_scroll_divisor_h, 4, uint16_t, 80, 5, 1000) \
    X(drag_scroll_divisor_v, 5, uint16_t, 24, 5, 1000) \
    X(wheels_vertical_arrows, 6, uint8_t, 0, 0, 1) \
    X(wheels_horizontal_arrows, 7, uint8_t, 0, 0, 1) \
    X(bottom_right_mode, 8, uint8_t, 0, 0, 1) \
    X(led_brightness, 9, uint8_t, 4, 1, 4) \
    X(pointer_dpi, 10, uint16_t, 900, 100, 12000)

/* Stored at ELI_SETTINGS_STORE_OFFSET in the VIA custom config. New fields
   are only ever appended. */
typedef struct __attribute__((packed)) {
    uint8_t magic;
    uint8_t length;
    uint8_t marker[3];
    uint16_t niri_flick_threshold;
    uint16_t niri_tap_term;
    uint16_t niri_idle_reset;
    uint16_t drag_scroll_divisor_h;
    uint16_t drag_scroll_divisor_v;
    uint8_t wheels_vertical_arrows;
    uint8_t wheels_horizontal_arrows;
    uint8_t bottom_right_mode;
    uint8_t led_brightness;
    uint16_t pointer_dpi;
} eli_settings_t;

_Static_assert(ELI_SETTINGS_STORE_OFFSET + sizeof(eli_settings_t) <= VIA_EEPROM_CUSTOM_CONFIG_SIZE, "settings store does not fit");

enum eli_keycodes {
    PKC_TGL_VERT_SCRL = QK_KB_2,
    PKC_TGL_HORIZ_SCRL = QK_KB_3,
    PKC_NIRI = QK_KB_4,
    PKC_ADJUST_LED_BRIGHTNESS = QK_KB_5,
    PKC_BLINKY_DPI_CONFIG = QK_KB_6,
    PKC_TGL_BOTTOM_RIGHT = QK_KB_7,
    PKC_BOTTOM_RIGHT = QK_KB_8
};
