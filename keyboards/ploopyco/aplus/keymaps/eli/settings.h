/* Copyright 2026 Eli
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

/* Runtime settings for Eli's A+ keymap. The setting catalog (settings.toml)
   lists them; settings_catalog.h is generated from it. Values live in the VIA
   custom config and are read and written over VIA channel
   ELI_SETTINGS_CHANNEL by VIA and the `ploopy` CLI. */

#pragma once

#include "quantum.h"
#include "settings_catalog.h"

extern eli_settings_t eli_settings;

/* Load at boot, migrate an older store, and apply. Call from
   keyboard_post_init_user(). */
void settings_init(void);
/* Firmware defaults for every setting, a cleared apply marker, and default
   acceleration; then save. */
void settings_reset(void);
void settings_save(void);
/* Push values that hardware holds (DPI, LED brightness). */
void settings_apply(void);
