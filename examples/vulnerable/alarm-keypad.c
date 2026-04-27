#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <gpiod.h>

#define CHIP_PATH "/dev/gpiochip0"
#define BUTTON_PIN 17
#define ARMED_PIN  27

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

    unsigned int offsets[2] = { BUTTON_PIN, ARMED_PIN };

    if (argc != 3) {
        fprintf(stderr, "Usage: %s <max_polls> <digit>\n", argv[0]);
        return 1;
    }

    int max_polls = atoi(argv[1]);
    char digit = argv[2][0];

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
    gpiod_request_config_set_consumer(req_cfg, "alarm-code-collector");

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

    if (gpiod_line_config_add_line_settings(line_cfg, offsets, 2, settings) < 0) {
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
     * Tiny fixed-size buffer storing the collected alarm code.
     * Intentional bug: there is no bounds check before writing.
     */
    char code[8];
    int code_len = 0;

    for (int i = 0; i < max_polls; i++) {
        int button = gpiod_line_request_get_value(request, BUTTON_PIN);
        int armed  = gpiod_line_request_get_value(request, ARMED_PIN);

        if(button < 0 || button > 1) {
            fprintf(stderr, "Invalid button value: %d\n", button);
            return 1;
        }
        if(armed < 0 || armed > 1) {
            fprintf(stderr, "Invalid armed value: %d\n", armed);
            return 1;
        }

        if (button == 1 && armed == 1) {
            code[code_len++] = digit;   /* Intentional memory safety bug */
        }
    }

    code[code_len] = '\0';   /* Also unsafe if code_len overflowed */

    printf("Collected code: %s\n", code);

    cleanup_request(request);
    cleanup_config(line_cfg, settings, req_cfg, chip);
    return 0;
}