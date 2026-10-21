/* Copyright 2026 Eli
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "settings.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

#include "via.h"
#include "rgblight.h"
#include "pointing_device_accel.h"
#include "version.h"

/* Defined in pointing_device_accel.c but not declared in its header. */
void eeconfig_init_pointing_device(void);

eli_settings_t eli_settings;

/* magic, length and marker come before the settings. */
#define STORE_HEADER_SIZE (offsetof(eli_settings_t, marker) + sizeof(eli_settings.marker))
/* The accel module's VIA channel (id_maccel in pointing_device_accel_via.c). */
#define ACCEL_CHANNEL 24

/* The 3-byte build stamp VIA uses as its EEPROM magic (via.c). A reflash
   built on another day changes it and resets the button map, so an apply
   marker that no longer matches it means the mouse config needs applying. */
static void build_stamp(uint8_t stamp[3]) {
    const char *p = QMK_BUILDDATE; // e.g. "2019-11-05-11:29:54"
    stamp[0]      = ((p[2] & 0x0F) << 4) | (p[3] & 0x0F);
    stamp[1]      = ((p[5] & 0x0F) << 4) | (p[6] & 0x0F);
    stamp[2]      = ((p[8] & 0x0F) << 4) | (p[9] & 0x0F);
}

static void set_defaults(void) {
#define X(field, id, type, def, lo, hi) eli_settings.field = def;
    ELI_SETTINGS(X)
#undef X
}

/* Out-of-range stored values fall back to their firmware default. */
static void clamp_all(void) {
#define X(field, id, type, def, lo, hi) \
    if (eli_settings.field < (lo) || eli_settings.field > (hi)) eli_settings.field = def;
    ELI_SETTINGS(X)
#undef X
}

static bool accel_valid(void) {
    const pointing_device_accel_config_t *c = &g_pointing_device_accel_config;
    return !isnan(c->takeoff) && !isnan(c->growth_rate) && !isnan(c->offset) && !isnan(c->limit) && c->takeoff >= 0.5f && c->takeoff <= 5.0f && c->growth_rate >= 0.01f && c->growth_rate <= 5.0f && c->offset >= 0.0f && c->offset <= 15.0f && c->limit >= 0.0f && c->limit <= 1.0f;
}

void settings_save(void) {
    eli_settings.magic  = ELI_SETTINGS_MAGIC;
    eli_settings.length = sizeof(eli_settings_t);
    via_update_custom_config(&eli_settings, ELI_SETTINGS_STORE_OFFSET, sizeof(eli_settings_t));
}

void settings_reset(void) {
    memset(&eli_settings, 0, sizeof(eli_settings_t));
    set_defaults();
    settings_save();
    eeconfig_init_pointing_device();
}

void settings_apply(void) {
    pointing_device_set_cpi(eli_settings.pointer_dpi);
    rgblight_sethsv_noeeprom(0, 0, RGBLIGHT_VAL_STEP * eli_settings.led_brightness);
}

void settings_init(void) {
    via_read_custom_config(&eli_settings, ELI_SETTINGS_STORE_OFFSET, sizeof(eli_settings_t));
    uint8_t stored_length = eli_settings.length;

    if (eli_settings.magic != ELI_SETTINGS_MAGIC || stored_length < STORE_HEADER_SIZE) {
        settings_reset();
    } else if (stored_length < sizeof(eli_settings_t)) {
        /* Firmware with more settings than the store holds: keep what was
           stored and start the new fields at their defaults. */
        eli_settings_t stored = eli_settings;
        set_defaults();
        memcpy(&eli_settings, &stored, stored_length);
        clamp_all();
        settings_save();
    } else {
        clamp_all();
    }

    /* The accel module loads its floats before this runs. Stale or never
       written bytes give NaN or nonsense, so fall back to its defaults. */
    if (!accel_valid()) {
        eeconfig_init_pointing_device();
        /* The configured curve is gone: invalidate the apply marker so the
           plug-in hook restores it. */
        memset(eli_settings.marker, 0, sizeof(eli_settings.marker));
        settings_save();
    }

    settings_apply();
}

/* Runs inside via_init(), before VIA checks its magic. With no settings
   store, the custom config size has just changed (or EEPROM is fresh), so
   the dynamic keymap has moved: make VIA reset it instead of reading it from
   the wrong place. */
void via_init_kb(void) {
    uint8_t magic = 0;
    via_read_custom_config(&magic, ELI_SETTINGS_STORE_OFFSET, 1);
    if (magic != ELI_SETTINGS_MAGIC) {
        via_eeprom_set_valid(false);
    }
}

static bool marker_valid(void) {
    uint8_t stamp[3];
    build_stamp(stamp);
    return memcmp(stamp, eli_settings.marker, sizeof(stamp)) == 0;
}

static void settings_set_value(uint8_t *data) {
    uint8_t  id    = data[0];
    uint8_t *value = &data[1];

    if (id == ELI_SETTINGS_MARKER_ID) {
        build_stamp(eli_settings.marker);
        settings_save();
        return;
    }
    switch (id) {
#define X(field, vid, type, def, lo, hi)                                                          \
    case vid: {                                                                                   \
        uint16_t raw = sizeof(type) == 2 ? (uint16_t)((value[0] << 8) | value[1]) : value[0];   \
        eli_settings.field = (raw < (lo) || raw > (hi)) ? (type)(def) : (type)raw;                \
        break;                                                                                    \
    }
        ELI_SETTINGS(X)
#undef X
    }
    settings_apply();
}

static void settings_get_value(uint8_t *data) {
    uint8_t  id    = data[0];
    uint8_t *value = &data[1];

    if (id == ELI_SETTINGS_MARKER_ID) {
        value[0] = marker_valid();
        return;
    }
    switch (id) {
#define X(field, vid, type, def, lo, hi)               \
    case vid:                                          \
        if (sizeof(type) == 2) {                       \
            value[0] = eli_settings.field >> 8;        \
            value[1] = eli_settings.field & 0xFF;      \
        } else {                                       \
            value[0] = eli_settings.field;             \
        }                                              \
        break;
        ELI_SETTINGS(X)
#undef X
    }
}

static bool settings_known_id(uint8_t id) {
    switch (id) {
        case ELI_SETTINGS_MARKER_ID:
#define X(field, vid, type, def, lo, hi) case vid:
            ELI_SETTINGS(X)
#undef X
            return true;
        default:
            return false;
    }
}

/* QMK has one VIA custom value hook, so this handles our channel and hands
   the accel module its own. */
void via_custom_value_command_kb(uint8_t *data, uint8_t length) {
    uint8_t *command_id = &data[0];
    uint8_t  channel_id = data[1];

    if (channel_id == ACCEL_CHANNEL) {
        /* The module's setter skips its own takeoff floor, and accel_valid()
           would reset a lower value at the next boot. */
        if (*command_id == id_custom_set_value && data[2] == 1 && ((data[3] << 8) | data[4]) < ELI_ACCEL_TAKEOFF_MIN_RAW) {
            data[3] = ELI_ACCEL_TAKEOFF_MIN_RAW >> 8;
            data[4] = ELI_ACCEL_TAKEOFF_MIN_RAW & 0xFF;
        }
        via_custom_value_command_accel(data, length);
        return;
    }
    if (channel_id != ELI_SETTINGS_CHANNEL || (*command_id != id_custom_save && !settings_known_id(data[2]))) {
        *command_id = id_unhandled;
        return;
    }
    switch (*command_id) {
        case id_custom_set_value:
            settings_set_value(&data[2]);
            break;
        case id_custom_get_value:
            settings_get_value(&data[2]);
            break;
        case id_custom_save:
            settings_save();
            break;
        default:
            *command_id = id_unhandled;
            break;
    }
}
