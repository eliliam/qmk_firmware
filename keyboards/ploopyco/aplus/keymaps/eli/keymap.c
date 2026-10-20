/* Copyright 2023 Colin Lam (Ploopy Corporation)
 * Copyright 2020 Christopher Courtney, aka Drashna Jael're  (@drashna) <drashna@live.com>
 * Copyright 2019 Sunjun Kim
 * Copyright 2026 Eli
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

/* Eli's keymap, forked from the A+ default keymap. Differences:
   - Top Right sends MEH(Space) for Voxtype push-to-talk dictation.
   - Holding the left wheel navigates Niri instead of making mouse gestures
     (see "Niri navigation" below). The gestures module is not used.
   - Right-handed only: the mirror layer and drag scroll are removed.
   - Left wheel clockwise scrolls up (stock scrolls down).
   - Control layer: Bottom Left enters the bootloader, Bottom Right flips the
     vertical wheel direction.
   keymap.html is a visual reference of this keymap; update its KEYMAP data
   block whenever the mapping changes. */

#include QMK_KEYBOARD_H

#include <stdlib.h>

#include "rgblight.h"
#include "printf.h"

#include "../../../common/tmag5273wheel.h"

/* State variables for wheels. */
uint16_t leftwheel_deadzone_center = 0;
uint16_t rightwheel_deadzone_center = 0;

uint16_t leftwheel_current_position = 0;
uint16_t rightwheel_current_position = 0;
uint32_t last_scroll_time = 0;

/* Layer lighting, used to blink when navigating Niri. */
const rgblight_segment_t PROGMEM righty_nav_layer_colour[] =        RGBLIGHT_LAYER_SEGMENTS( {0, 2, HSV_NAVBLUE} );
const rgblight_segment_t PROGMEM control_layer_colour[] =           RGBLIGHT_LAYER_SEGMENTS( {0, 2, HSV_RED} );
const rgblight_segment_t PROGMEM gesture_layer_colour[] =           RGBLIGHT_LAYER_SEGMENTS( {0, 2, HSV_GESTUREYELLOW} );
const rgblight_segment_t PROGMEM option_changed_layer_colour[] =    RGBLIGHT_LAYER_SEGMENTS( {0, 2, HSV_OPTIONCHANGED} );

/* Lighting layer definitions. Later layers take precedence, so these
   are defined in the order that they will be displayed in. */
const rgblight_segment_t* const PROGMEM my_rgb_layers[] = RGBLIGHT_LAYERS_LIST(
    righty_nav_layer_colour,
    control_layer_colour,
    gesture_layer_colour,
    option_changed_layer_colour
);

/* Colour layer names. */
enum {
    RIGHTY_NAV_LAYER_COLOUR = 0,
    CONTROL_LAYER_COLOUR,
    GESTURE_LAYER_COLOUR,
    OPTION_CHANGED_LAYER_COLOUR
};

 /* EEPROM memory for the various persistent states that the A+ can have.
    See eeconfig_init_user() for default values and meanings. The unused bits
    keep the stock layout, so settings saved by stock firmware still load. */
typedef union {
  uint32_t raw;
  struct {
    bool    unused_left_handed :1;
    bool    horizontal_scroll_arrows :1;
    bool    vertical_scroll_arrows :1;
    bool    unused_drag_scroll_mode :1;
    uint8_t led_brightness: 8;
    bool    vertical_scroll_inverted :1;
  };
} user_config_t;

user_config_t user_config;

/* Add custom keycodes for control layer. Unused entries keep the stock
   keycode values, so VIA keeps showing the same codes. */
enum my_keycodes {
  PKC_UNUSED_TGL_MIRROR = SAFE_RANGE,
  PKC_TGL_VERT_SCRL,
  PKC_TGL_HORIZ_SCRL,
  PKC_UNUSED_TGL_DRAG_SCRL,
  PKC_NIRI,
  PKC_UNUSED_DRAG_SCROLL,
  PKC_ADJUST_LED_BRIGHTNESS,
  PKC_BLINKY_DPI_CONFIG,
  PKC_TGL_VERT_SCRL_DIR
};

/* Layer names. */
enum {
    LAYER_NAV = 0,
    LAYER_CONTROL
};

/* Keymap. */
const uint16_t PROGMEM keymaps[][MATRIX_ROWS][MATRIX_COLS] = {
    // Base layer with all of the mouse-related stuff for everyday use.
    [LAYER_NAV] = LAYOUT(               MS_BTN4, MS_BTN5, MEH(KC_SPC), MS_BTN2,
                                        MS_BTN1, MS_BTN3,
                                        PKC_NIRI, TG(LAYER_CONTROL) ),
    // Layer for all of the customization options.
    [LAYER_CONTROL] = LAYOUT(           PKC_BLINKY_DPI_CONFIG, PKC_ADJUST_LED_BRIGHTNESS, PKC_TGL_VERT_SCRL, PKC_TGL_HORIZ_SCRL,
                                        QK_BOOT, PKC_TGL_VERT_SCRL_DIR,
                                        TG(LAYER_CONTROL), TG(LAYER_CONTROL) ),
    [2] = LAYOUT( _______, _______, _______, _______, _______, _______, _______, _______ ),
    [3] = LAYOUT( _______, _______, _______, _______, _______, _______, _______, _______ ),
    [4] = LAYOUT( _______, _______, _______, _______, _______, _______, _______, _______ ),
    [5] = LAYOUT( _______, _______, _______, _______, _______, _______, _______, _______ ),
    [6] = LAYOUT( _______, _______, _______, _______, _______, _______, _______, _______ ),
    [7] = LAYOUT( _______, _______, _______, _______, _______, _______, _______, _______ )
};

/* ============================ Niri navigation ============================ */

/* While PKC_NIRI is held, the pointer stays still and ball motion becomes
   Niri steps, one per NIRI_FLICK_THRESHOLD counts on the dominant axis. The
   first step opens the overview; releasing closes it. A short press with no
   step and no other button toggles the overview.
   Bound in ~/.config/niri/cfg/keybinds.kdl ("Ploopy hold mode"). */
#define NIRI_LEFT HYPR(KC_LEFT)
#define NIRI_RIGHT HYPR(KC_RIGHT)
#define NIRI_UP HYPR(KC_UP)
#define NIRI_DOWN HYPR(KC_DOWN)
#define NIRI_OVERVIEW_OPEN HYPR(KC_O)
#define NIRI_OVERVIEW_CLOSE HYPR(KC_C)
#define NIRI_OVERVIEW_TOGGLE HYPR(KC_T)

static bool     niri_hold          = false;
static bool     niri_acted         = false;
static bool     niri_overview_open = false;
static uint16_t niri_press_timer;
static uint16_t niri_motion_timer;
static int32_t  niri_acc_x         = 0;
static int32_t  niri_acc_y         = 0;

static void niri_step(uint16_t chord) {
    if (!niri_overview_open) {
        tap_code16(NIRI_OVERVIEW_OPEN);
        niri_overview_open = true;
    }
    tap_code16(chord);
    niri_acted = true;
}

static void niri_press(void) {
    niri_hold         = true;
    niri_acted        = false;
    niri_acc_x        = 0;
    niri_acc_y        = 0;
    niri_press_timer  = timer_read();
    niri_motion_timer = niri_press_timer;
    rgblight_set_layer_state(GESTURE_LAYER_COLOUR, true);
}

static void niri_release(void) {
    niri_hold = false;
    rgblight_set_layer_state(GESTURE_LAYER_COLOUR, false);
    if (niri_overview_open) {
        tap_code16(NIRI_OVERVIEW_CLOSE);
        niri_overview_open = false;
    } else if (!niri_acted && timer_elapsed(niri_press_timer) < NIRI_TAP_TERM) {
        tap_code16(NIRI_OVERVIEW_TOGGLE);
    }
}

/* Freeze the pointer and turn raw ball motion into Niri steps. */
static report_mouse_t niri_task(report_mouse_t mouse_report) {
    if (mouse_report.x != 0 || mouse_report.y != 0) {
        niri_motion_timer = timer_read();
    } else if (timer_elapsed(niri_motion_timer) > NIRI_IDLE_RESET_MS) {
        niri_acc_x = 0;
        niri_acc_y = 0;
    }

    niri_acc_x += mouse_report.x;
    niri_acc_y += mouse_report.y;
    mouse_report.x = 0;
    mouse_report.y = 0;

    if (abs(niri_acc_x) >= NIRI_FLICK_THRESHOLD || abs(niri_acc_y) >= NIRI_FLICK_THRESHOLD) {
        if (abs(niri_acc_x) >= abs(niri_acc_y)) {
            niri_step(niri_acc_x > 0 ? NIRI_RIGHT : NIRI_LEFT);
        } else {
            niri_step(niri_acc_y > 0 ? NIRI_DOWN : NIRI_UP);
        }
        niri_acc_x = 0;
        niri_acc_y = 0;
    }

    return mouse_report;
}

/* Skip pointer acceleration while navigating, so the step threshold is in
   raw sensor counts and doesn't depend on flick speed. */
bool pointing_device_accel_should_process(void) {
    return !niri_hold;
}

/* ========================================================================= */

/* Called whenever layers are modified. */
layer_state_t layer_state_set_user(layer_state_t state) {
    /* Set layer colours. */
    switch (get_highest_layer(state)) {
        case LAYER_NAV:
            rgblight_set_layer_state(RIGHTY_NAV_LAYER_COLOUR, true);

            rgblight_set_layer_state(CONTROL_LAYER_COLOUR, false);

            dprintf("change layer: right-handed nav\n");
            break;
        case LAYER_CONTROL:
            rgblight_set_layer_state(CONTROL_LAYER_COLOUR, true);

            rgblight_set_layer_state(RIGHTY_NAV_LAYER_COLOUR, false);

            dprintf("change layer: control\n");
            break;
        default:
            rgblight_setrgb(RGB_CYAN);
            dprintf("change layer: oopsie, invalid layer!\n");
            break;
    }
    return state;
}

/* Set sane defaults when EEPROM is reset. */
void eeconfig_init_user(void) {

    user_config.raw = 0;

    user_config.horizontal_scroll_arrows = false;   // False = Scroll events, True = left/right arrows.
    user_config.vertical_scroll_arrows = false;     // False = Scroll events, True = up/down arrows.
    user_config.led_brightness = 4;                 // Brightest mode by default.
    user_config.vertical_scroll_inverted = false;   // False = clockwise scrolls up.

    eeconfig_update_user(user_config.raw);
}

void keyboard_pre_init_user(void) {

    /* Set up GPIO for both TMAG sensors. */
    gpio_set_pin_output_push_pull(TMAG5273_D0_PWR_PIN);
    gpio_set_pin_output_push_pull(TMAG5273_D1_PWR_PIN);
    gpio_write_pin_low(TMAG5273_D0_PWR_PIN);
    gpio_write_pin_low(TMAG5273_D1_PWR_PIN);

}

void keyboard_post_init_user(void) {
    /* ============================ Debug Setup ============================ */

    /* If you turn these on, also uncomment CONSOLE_ENABLE = yes in
       post_rules.mk! */
    //debug_enable = true;
    //debug_matrix=true;
    //debug_keyboard=true;
    //debug_mouse=true;

    /* ========================== Scroll Wheel Setup ======================= */

    /* Start up the two wheels. */
    tmag5273_init();

    /* Init TMAG5273 D0 (left wheel) */
    gpio_write_pin_high(TMAG5273_D0_PWR_PIN);
    wait_us(370);  // TMAG tstart_power_up, plus 100us margin
    tmag5273_init_device(TMAG5273_D0_I2C_ADDRESS);
    wait_ms(20);
    leftwheel_current_position = tmag5273_get_angle(TMAG5273_D0_I2C_ADDRESS);
    leftwheel_deadzone_center = leftwheel_current_position;


    /* Init TMAG5273 D1 (right wheel) */
    gpio_write_pin_high(TMAG5273_D1_PWR_PIN);
    wait_us(370);  // TMAG tstart_power_up, plus 100us margin
    tmag5273_init_device(TMAG5273_D1_I2C_ADDRESS);
    wait_ms(20);
    rightwheel_current_position = tmag5273_get_angle(TMAG5273_D1_I2C_ADDRESS);
    rightwheel_deadzone_center = rightwheel_current_position;


    /* =================== Persistent Configuration Setup ================== */

    /* Load up configuration details from the EEPROM. */
    user_config.raw = eeconfig_read_user();


    /* ============================ Lighting Setup ========================= */

    /* Enable the LED layers. */
    rgblight_layers = my_rgb_layers;

    /* Enable RGB lighting for layer indicators. */
    rgblight_enable_noeeprom();
    rgblight_mode_noeeprom(RGBLIGHT_MODE_STATIC_LIGHT);

    /* Set an initial colour to establish a baseline brightness for the RGB layers. */
    rgblight_sethsv(0, 0, RGBLIGHT_VAL_STEP * user_config.led_brightness);
}

bool process_record_user(uint16_t keycode, keyrecord_t* record) {
    /* Any other button pressed during a Niri hold cancels the overview tap. */
    if (niri_hold && keycode != PKC_NIRI && record->event.pressed) {
        niri_acted = true;
    }

    switch (keycode) {
        case PKC_TGL_VERT_SCRL:
            if (record->event.pressed) {
                user_config.vertical_scroll_arrows ^= 1;
                eeconfig_update_user(user_config.raw);

                if( user_config.vertical_scroll_arrows ) {
                    rgblight_blink_layer(OPTION_CHANGED_LAYER_COLOUR, OPTION_CHANGE_BLINK_TIMEOUT*2);
                    dprintf("Vert. scroll = arrows.\n");
                }
                else {
                    rgblight_blink_layer_repeat(OPTION_CHANGED_LAYER_COLOUR, OPTION_CHANGE_BLINK_TIMEOUT, 2);
                    dprintf("Vert. scroll = scroll events.\n");
                }
            }
            return true;
        case PKC_TGL_HORIZ_SCRL:
            if (record->event.pressed) {
                user_config.horizontal_scroll_arrows ^= 1;
                eeconfig_update_user(user_config.raw);

                if( user_config.horizontal_scroll_arrows ) {
                    rgblight_blink_layer(OPTION_CHANGED_LAYER_COLOUR, OPTION_CHANGE_BLINK_TIMEOUT*2);
                    dprintf("Horiz. scroll = arrows.\n");
                }
                else {
                    rgblight_blink_layer_repeat(OPTION_CHANGED_LAYER_COLOUR, OPTION_CHANGE_BLINK_TIMEOUT, 2);
                    dprintf("Horiz. scroll = scroll events.\n");
                }
            }
            return true;
        case PKC_TGL_VERT_SCRL_DIR:
            if (record->event.pressed) {
                user_config.vertical_scroll_inverted ^= 1;
                eeconfig_update_user(user_config.raw);

                if( user_config.vertical_scroll_inverted ) {
                    rgblight_blink_layer(OPTION_CHANGED_LAYER_COLOUR, OPTION_CHANGE_BLINK_TIMEOUT*2);
                    dprintf("Vert. scroll direction = clockwise down.\n");
                }
                else {
                    rgblight_blink_layer_repeat(OPTION_CHANGED_LAYER_COLOUR, OPTION_CHANGE_BLINK_TIMEOUT, 2);
                    dprintf("Vert. scroll direction = clockwise up.\n");
                }
            }
            return true;
        case PKC_NIRI:
            if (record->event.pressed) {
                niri_press();
            }
            else {
                niri_release();
            }
            return true;
        case PKC_ADJUST_LED_BRIGHTNESS:
            /* Increase brightness in RGBLIGHT_VAL_STEP steps.
               Go to minimum brightness if the max brightness is hit. */
            if (record->event.pressed) {
                if( rgblight_get_val() >= RGBLIGHT_VAL_STEP * 4 ) {
                    rgblight_decrease_val_noeeprom();
                    rgblight_decrease_val_noeeprom();
                    rgblight_decrease_val_noeeprom();
                    user_config.led_brightness = 1;
                    eeconfig_update_user(user_config.raw);
                }
                else {
                    rgblight_increase_val_noeeprom();
                    user_config.led_brightness += 1;
                    eeconfig_update_user(user_config.raw);
                }

                dprintf("Adjusted LED brightness. Current brightness = %d/255\n", rgblight_get_val());
            }
            return true;
        case PKC_BLINKY_DPI_CONFIG:
            if (record->event.pressed) {
                cycle_dpi();

                dprintf("DPI changed. Current DPI = %d\n", dpi_array[keyboard_config.dpi_config]);
                rgblight_blink_layer_repeat(OPTION_CHANGED_LAYER_COLOUR, OPTION_CHANGE_BLINK_TIMEOUT, keyboard_config.dpi_config + 1);
            }
            return true;
        default:
            return true;
    }
}

/* State variables for the scroll wheels. */
int16_t leftwheel_lowres_scroll_tick = 0;
int16_t rightwheel_lowres_scroll_tick = 0;

int16_t leftwheel_arrow_scroll_tick = 0;
int16_t rightwheel_arrow_scroll_tick = 0;

int16_t leftwheel_volume_scroll_tick = 0;
int16_t rightwheel_volume_scroll_tick = 0;

uint32_t leftwheel_timeout = 0;
uint32_t rightwheel_timeout = 0;

report_mouse_t pointing_device_task_user(report_mouse_t mouse_report) {
    if (niri_hold) {
        mouse_report = niri_task(mouse_report);
    }

    // throttle reads
    if (timer_elapsed32(last_scroll_time) > 10) {
        uint16_t leftwheel_rawangle = tmag5273_get_angle(TMAG5273_D0_I2C_ADDRESS);
        uint16_t rightwheel_rawangle = tmag5273_get_angle(TMAG5273_D1_I2C_ADDRESS);

        int16_t leftwheel_deadzone_distance = calculate_deadzone_distance( leftwheel_rawangle, &leftwheel_deadzone_center );
        int16_t rightwheel_deadzone_distance = calculate_deadzone_distance( rightwheel_rawangle, &rightwheel_deadzone_center );

        int16_t leftwheel_delta = calculate_wheel_delta( leftwheel_rawangle, leftwheel_current_position );
        leftwheel_current_position = leftwheel_rawangle;

        int16_t rightwheel_delta = calculate_wheel_delta( rightwheel_rawangle, rightwheel_current_position );
        rightwheel_current_position = rightwheel_rawangle;

        /* If either wheel moved, we reset the timeout counter. Else, we start
           counting inactivity. */
        if( abs(leftwheel_delta) > 2 ) {
            leftwheel_timeout = 0;
        }
        else {
            /* Don't increment forever, you'll get rollover. */
            if( leftwheel_timeout < TMAG5273_DEADZONE_PROTECTOR_TIMEOUT ) {
                leftwheel_timeout += timer_elapsed32(last_scroll_time);
            }
        }
        if( abs(rightwheel_delta) > 2 ) {
            rightwheel_timeout = 0;
        }
        else {
            /* Don't increment forever, you'll get rollover. */
            if( rightwheel_timeout < TMAG5273_DEADZONE_PROTECTOR_TIMEOUT ) {
                rightwheel_timeout += timer_elapsed32(last_scroll_time);
            }
        }

        /* Reset the counter so we know when to next perform all this scroll processing. */
        last_scroll_time = timer_read32();

        /* If either of the wheels times out, we move the deadzone window to
           where the position is. This prevents spurious scroll events. */
        if( leftwheel_timeout >= TMAG5273_DEADZONE_PROTECTOR_TIMEOUT &&
            leftwheel_timeout < TMAG5273_DEADZONE_PROTECTOR_TIMEOUT * 2 ) {

            leftwheel_deadzone_center = leftwheel_current_position;
            dprintf("Left wheel timeout, deadzone moved to: %d\n", leftwheel_deadzone_center);

            /* Set the timeout to a large number so that we only shift the window once. */
            leftwheel_timeout = TMAG5273_DEADZONE_PROTECTOR_TIMEOUT * 4;
        }
        if( rightwheel_timeout >= TMAG5273_DEADZONE_PROTECTOR_TIMEOUT &&
            rightwheel_timeout < TMAG5273_DEADZONE_PROTECTOR_TIMEOUT * 2 ) {

            rightwheel_deadzone_center = rightwheel_current_position;
            dprintf("Right wheel timeout, deadzone moved to: %d\n", rightwheel_deadzone_center);

            /* Set the timeout to a large number so that we only shift the window once. */
            rightwheel_timeout = TMAG5273_DEADZONE_PROTECTOR_TIMEOUT * 4;
        }

        /* If we're on the control layers, both wheels adjust the volume. */
        if( layer_state_is(LAYER_CONTROL) ) {

            leftwheel_volume_scroll_tick += leftwheel_delta;
            rightwheel_volume_scroll_tick += rightwheel_delta;

            if( leftwheel_volume_scroll_tick > TMAG5273_VOLUME_SCROLL_TICK_SIZE ) {
                tap_code(KC_VOLU);
                leftwheel_volume_scroll_tick = 0;
            }
            else if( leftwheel_volume_scroll_tick < -TMAG5273_VOLUME_SCROLL_TICK_SIZE ) {
                tap_code(KC_VOLD);
                leftwheel_volume_scroll_tick = 0;
            }
            if( rightwheel_volume_scroll_tick > TMAG5273_VOLUME_SCROLL_TICK_SIZE ) {
                tap_code(KC_VOLU);
                rightwheel_volume_scroll_tick = 0;
            }
            else if( rightwheel_volume_scroll_tick < -TMAG5273_VOLUME_SCROLL_TICK_SIZE ) {
                tap_code(KC_VOLD);
                rightwheel_volume_scroll_tick = 0;
            }

            /* Return early -- no other scrolling activity happens in the
               control layer. */
            return mouse_report;
        }

        /* The left wheel scrolls vertically. Stock turns clockwise into scrolling
           down; flip it so clockwise scrolls up, unless the user flipped it back. */
        if( !user_config.vertical_scroll_inverted ) {
            leftwheel_delta = -leftwheel_delta;
        }

        /* If scroll arrow mode is activated for horizontal scrolling, then we do that.
           This behaviour is the same across OSes. */
        if( user_config.horizontal_scroll_arrows ) {

            rightwheel_arrow_scroll_tick += rightwheel_delta;

            if( rightwheel_arrow_scroll_tick > TMAG5273_HORIZ_SCROLL_TICK_SIZE ) {
                tap_code(KC_RIGHT);
                rightwheel_arrow_scroll_tick = 0;
            }
            else if( rightwheel_arrow_scroll_tick < -TMAG5273_HORIZ_SCROLL_TICK_SIZE ) {
                tap_code(KC_LEFT);
                rightwheel_arrow_scroll_tick = 0;
            }
            /* Set the delta to zero so we don't scroll *and* arrow at the same time. */
            rightwheel_delta = 0;
        }

        /* If scroll arrow mode is activated for vertical scrolling, then we do that.
           This behaviour is the same across OSes. */
        if( user_config.vertical_scroll_arrows ) {

            leftwheel_arrow_scroll_tick += leftwheel_delta;

            if( leftwheel_arrow_scroll_tick > TMAG5273_VERT_SCROLL_TICK_SIZE ) {
                tap_code(KC_DOWN);
                leftwheel_arrow_scroll_tick = 0;
            }
            else if( leftwheel_arrow_scroll_tick < -TMAG5273_VERT_SCROLL_TICK_SIZE ) {
                tap_code(KC_UP);
                leftwheel_arrow_scroll_tick = 0;
            }
            /* Set the delta to zero so we don't scroll *and* arrow at the same time. */
            leftwheel_delta = 0;
        }

        /* If we're on Windows or Linux, send hi-res scroll events. */
        if ( (detected_host_os() == OS_WINDOWS || detected_host_os() == OS_LINUX) ) {

            if ( leftwheel_deadzone_distance > (TMAG5273_WHEEL_DEADZONE - 10) ||
                 leftwheel_deadzone_distance < (-TMAG5273_WHEEL_DEADZONE + 10)) {

                mouse_report.v = -leftwheel_delta / TMAG5273_VERTICAL_WHEEL_SPEED_DIV;
            }
            if ( rightwheel_deadzone_distance > (TMAG5273_WHEEL_DEADZONE - 10) ||
                 rightwheel_deadzone_distance < (-TMAG5273_WHEEL_DEADZONE + 10)) {

                mouse_report.h = rightwheel_delta / TMAG5273_HORIZONAL_WHEEL_SPEED_DIV;
            }

        } else {
            /* In this case, we're on another OS, so we just send regular scroll events. */
            /* Certain operating systems, like MacOS, don't play well with the
               high-res scrolling implementation. For more details, see:
               https://github.com/qmk/qmk_firmware/issues/17585#issuecomment-2325248167
               128 gives the scroll wheels "ticks". */

            leftwheel_lowres_scroll_tick += leftwheel_delta;
            rightwheel_lowres_scroll_tick += rightwheel_delta;

            if( leftwheel_lowres_scroll_tick > TMAG5273_LOWRES_TICK_SIZE ) {
                mouse_report.v = -1;
                leftwheel_lowres_scroll_tick = 0;
            }
            else if( leftwheel_lowres_scroll_tick < -TMAG5273_LOWRES_TICK_SIZE ) {
                mouse_report.v = 1;
                leftwheel_lowres_scroll_tick = 0;
            }

            if( rightwheel_lowres_scroll_tick > TMAG5273_LOWRES_TICK_SIZE ) {
                if( !user_config.horizontal_scroll_arrows ) {
                    mouse_report.h = 1;
                }
                rightwheel_lowres_scroll_tick = 0;
            }
            else if( rightwheel_lowres_scroll_tick < -TMAG5273_LOWRES_TICK_SIZE ) {
                if( !user_config.horizontal_scroll_arrows ) {
                    mouse_report.h = -1;
                }
                rightwheel_lowres_scroll_tick = 0;
            }
        }

        /* Set scroll data to zero if the corresponding button is
           currently being held down. */

        /* Check left knob. */
        if( matrix_is_on(0,6) ) {
            mouse_report.v = 0;
        }
        /* Check right knob. */
        if( matrix_is_on(0,7) ) {
            mouse_report.h = 0;
        }

    }

    return mouse_report;
}
