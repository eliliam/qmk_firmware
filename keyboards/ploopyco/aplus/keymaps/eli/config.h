/* Copyright 2020 Christopher Courtney, aka Drashna Jael're  (@drashna) <drashna@live.com>
 * Copyright 2019 Sunjun Kim
 * Copyright 2020 Ploopy Corporation
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 2 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 */

#pragma once

#define DYNAMIC_KEYMAP_LAYER_COUNT 8

/* Eli: tuning values are runtime settings now (settings.toml). */

/* Settings live in the VIA custom config after the accel module's 20 bytes.
   Never change this size: it moves the dynamic keymap. settings_catalog.h
   checks it against settings.toml. */
#define VIA_EEPROM_CUSTOM_CONFIG_SIZE 128
#define VIA_EEPROM_CUSTOM_CONFIG_ERROR_OVERRIDE

/* Drag scroll (Bottom Right in drag mode) reads its divisors from settings.
   ploopyco.c uses these macros, so it needs the prototypes. */
#undef PLOOPY_DRAGSCROLL_DIVISOR_H
#define PLOOPY_DRAGSCROLL_DIVISOR_H eli_dragscroll_divisor_h()
#undef PLOOPY_DRAGSCROLL_DIVISOR_V
#define PLOOPY_DRAGSCROLL_DIVISOR_V eli_dragscroll_divisor_v()
#if !defined(__ASSEMBLER__)
float eli_dragscroll_divisor_h(void);
float eli_dragscroll_divisor_v(void);
#endif
