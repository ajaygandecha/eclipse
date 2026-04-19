#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <gpiod.h>

/*
 * irrigation_controller.c
 *
 * A small intentionally vulnerable embedded-style irrigation controller.
 *
 * Usage:
 *   ./irrigation_controller <cycles> <zone>
 *
 * Example:
 *   ./irrigation_controller 6 n1
 *
 * Arguments:
 *   <cycles>  Number of times to poll the GPIO pins and process irrigation logic.
 *   <zone>    Short irrigation zone name, such as "n1" or "b2".
 *
 * GPIO meaning:
 *   MOISTURE_PIN:
 *     0 = dry
 *     1 = wet
 *
 *   OVERRIDE_PIN:
 *     0 = no manual override
 *     1 = manual override active
 *
 *   TANK_EMPTY_PIN:
 *     0 = water available
 *     1 = tank empty
 *
 * Intentional vulnerability:
 *   Ptr - a specific multi-step GPIO history reaches an unchecked strcat chain
 *         into a too-small stack buffer.
 */

#define CHIP_PATH "/dev/gpiochip0"
#define MOISTURE_PIN 17
#define OVERRIDE_PIN 27
#define TANK_EMPTY_PIN 22

static void cleanup_request(struct gpiod_line_request *request) {
    if (request != NULL) {
        gpiod_line_request_release(request);
    }
}

static void cleanup_config(struct gpiod_line_config *line_cfg,
                           struct gpiod_line_settings *settings,
                           struct gpiod_request_config *req_cfg,
                           struct gpiod_chip *chip) {
    if (line_cfg != NULL) {
        gpiod_line_config_free(line_cfg);
    }
    if (settings != NULL) {
        gpiod_line_settings_free(settings);
    }
    if (req_cfg != NULL) {
        gpiod_request_config_free(req_cfg);
    }
    if (chip != NULL) {
        gpiod_chip_close(chip);
    }
}

int main(int argc, char *argv[]) {
    struct gpiod_chip *chip = NULL;
    struct gpiod_request_config *req_cfg = NULL;
    struct gpiod_line_settings *settings = NULL;
    struct gpiod_line_config *line_cfg = NULL;
    struct gpiod_line_request *request = NULL;

    unsigned int offsets[3] = {MOISTURE_PIN, OVERRIDE_PIN, TANK_EMPTY_PIN};

    if (argc != 3) {
        fprintf(stderr, "Usage: %s <cycles> <zone>\n", argv[0]);
        return 1;
    }

    int cycles = atoi(argv[1]);
    char *zone = argv[2];

    chip = gpiod_chip_open(CHIP_PATH);
    if (chip == NULL) {
        perror("gpiod_chip_open");
        return 1;
    }

    req_cfg = gpiod_request_config_new();
    if (req_cfg == NULL) {
        perror("gpiod_request_config_new");
        cleanup_config(NULL, NULL, NULL, chip);
        return 1;
    }
    gpiod_request_config_set_consumer(req_cfg, "irrigation-controller");

    settings = gpiod_line_settings_new();
    if (settings == NULL) {
        perror("gpiod_line_settings_new");
        cleanup_config(NULL, NULL, req_cfg, chip);
        return 1;
    }

    if (gpiod_line_settings_set_direction(settings, GPIOD_LINE_DIRECTION_INPUT) < 0) {
        perror("gpiod_line_settings_set_direction");
        cleanup_config(NULL, settings, req_cfg, chip);
        return 1;
    }

    line_cfg = gpiod_line_config_new();
    if (line_cfg == NULL) {
        perror("gpiod_line_config_new");
        cleanup_config(NULL, settings, req_cfg, chip);
        return 1;
    }

    if (gpiod_line_config_add_line_settings(line_cfg, offsets, 3, settings) < 0) {
        perror("gpiod_line_config_add_line_settings");
        cleanup_config(line_cfg, settings, req_cfg, chip);
        return 1;
    }

    request = gpiod_chip_request_lines(chip, req_cfg, line_cfg);
    if (request == NULL) {
        perror("gpiod_chip_request_lines");
        cleanup_config(line_cfg, settings, req_cfg, chip);
        return 1;
    }

    /*
     * The controller only arms its vulnerable maintenance action after seeing
     * a very specific GPIO history across consecutive polls:
     *
     *   1. dry,  no override, water available
     *   2. wet,  no override, water available
     *   3. dry,  override,    water available
     *   4. wet,  override,    water available
     *   5. dry,  override,    tank empty
     *
     * Any other combination resets the state machine. This makes the GPIO
     * history, not the CLI, dominate the interesting search.
     */
    int protocol_state = 0;

    for (int i = 0; i < cycles; i++) {
        int moisture = gpiod_line_request_get_value(request, MOISTURE_PIN);
        int override = gpiod_line_request_get_value(request, OVERRIDE_PIN);
        int tankempty = gpiod_line_request_get_value(request, TANK_EMPTY_PIN);

        if (moisture < 0 || override < 0 || tankempty < 0) {
            perror("gpiod_line_request_get_value");
            cleanup_request(request);
            cleanup_config(line_cfg, settings, req_cfg, chip);
            return 1;
        }

        if (protocol_state == 0 &&
            moisture == 0 && override == 0 && tankempty == 0) {
            protocol_state = 1;
        } else if (protocol_state == 1 &&
                   moisture == 1 && override == 0 && tankempty == 0) {
            protocol_state = 2;
        } else if (protocol_state == 2 &&
                   moisture == 0 && override == 1 && tankempty == 0) {
            protocol_state = 3;
        } else if (protocol_state == 3 &&
                   moisture == 1 && override == 1 && tankempty == 0) {
            protocol_state = 4;
        } else if (protocol_state == 4 &&
                   moisture == 0 && override == 1 && tankempty == 1) {
            char event[8];

            event[0] = '\0';
            strcpy(event, "ZONE:");
            strcat(event, zone);
            strcat(event, ":OPEN");

            printf("Maintenance event for %s\n", event);
            cleanup_request(request);
            cleanup_config(line_cfg, settings, req_cfg, chip);
            return 0;
        } else {
            protocol_state = 0;
        }
    }

    printf("No maintenance action for zone %s\n", zone);

    cleanup_request(request);
    cleanup_config(line_cfg, settings, req_cfg, chip);
    return 0;
}
