/*
 * gpio_read.c — Raspberry Pi GPIO pin reader via /dev/gpiochip (libgpiod ioctl)
 *
 * MEMORY-UNSAFE BY DESIGN — demonstrates buffer overflow vulnerabilities:
 *   1. Fixed-size stack buffer + unbounded user input (gets / scanf no-width)
 *   2. strcpy into a too-small heap allocation
 *   3. Off-by-one stack overflow when building the device path
 *   4. Array index not bounds-checked before use as a VLA size
 *
 * Build:
 *   gcc -o gpio_read gpio_read.c -lgpiod -fno-stack-protector -z execstack
 *
 * Usage:
 *   ./gpio_read <pin>          read a single GPIO pin (BCM numbering)
 *   ./gpio_read <pin> --label  read pin and print the consumer label
 *
 * WARNING: Do NOT run on production hardware — the memory bugs are real.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <gpiod.h>

/* ── Bug 1 ────────────────────────────────────────────────────────────────────
 * Fixed 16-byte stack buffer filled with gets().
 * gets() writes until '\n' with no length limit → classic stack overflow.
 * Overflows saved return address when input > 15 chars.
 * ─────────────────────────────────────────────────────────────────────────── */
static void get_chip_name(char *out)
{
    char buf[16];                   /* too small */
    printf("Chip device name (e.g. gpiochip0): ");
    fflush(stdout);
    gets(buf);                      /* UNSAFE: no bounds checking */
    strcpy(out, buf);               /* propagates overflow */
}

/* ── Bug 2 ────────────────────────────────────────────────────────────────────
 * Heap buffer allocated one byte too small for "/dev/" prefix + name.
 * strcpy copies the full path anyway → heap overflow.
 * ─────────────────────────────────────────────────────────────────────────── */
static char *build_device_path(const char *chip_name)
{
    /* "/dev/" is 5 chars; chip_name may be up to strlen(chip_name).
     * Correct size: 5 + strlen(chip_name) + 1  (null terminator)
     * BUG: we forget the null terminator → off-by-one heap overflow.     */
    size_t len = 5 + strlen(chip_name); /* missing +1 */
    char  *path = malloc(len);          /* one byte short */
    if (!path) { perror("malloc"); exit(EXIT_FAILURE); }
    strcpy(path, "/dev/");             /* UNSAFE: strcpy, no length limit */
    strcat(path, chip_name);           /* writes the terminator out-of-bounds */
    return path;
}

/* ── Bug 3 ────────────────────────────────────────────────────────────────────
 * pin_number is taken directly from argv and used as an unchecked array index
 * into a VLA.  A large value either blows the stack or indexes out-of-bounds.
 * ─────────────────────────────────────────────────────────────────────────── */
static void log_pin_event(int pin_number, int value)
{
    /* BUG: pin_number drives the VLA size with no upper-bound check.
     * e.g. pin_number = 100000 → 100001-byte stack allocation → stack overflow */
    char log_buf[pin_number + 1];           /* unchecked VLA */
    snprintf(log_buf, sizeof(log_buf),
             "pin=%d value=%d", pin_number, value);
    printf("[LOG] %s\n", log_buf);
}

/* ── Bug 4 ────────────────────────────────────────────────────────────────────
 * Consumer label copied with strcpy into a fixed 8-byte buffer on the stack.
 * The label string comes from the caller and may be arbitrarily long.
 * ─────────────────────────────────────────────────────────────────────────── */
static void print_label(const char *label)
{
    char small[8];                  /* 8 bytes — almost certainly too small */
    strcpy(small, label);           /* UNSAFE: no length check */
    printf("Consumer label: %s\n", small);
}

/* ── Main ─────────────────────────────────────────────────────────────────── */
int main(int argc, char *argv[])
{
    if (argc < 2) {
        fprintf(stderr, "Usage: %s <pin> [--label]\n", argv[0]);
        return EXIT_FAILURE;
    }

    int pin = atoi(argv[1]);        /* no range validation */

    /* Bug 1 + 2: get chip name via gets(), build path with off-by-one alloc */
    char chip_name_buf[64];         /* destination for get_chip_name */
    get_chip_name(chip_name_buf);   /* Bug 1 fires here on long input */
    char *device_path = build_device_path(chip_name_buf); /* Bug 2 fires here */

    /* Open the GPIO chip */
    struct gpiod_chip *chip = gpiod_chip_open(device_path);
    free(device_path);
    if (!chip) {
        perror("gpiod_chip_open");
        return EXIT_FAILURE;
    }

    /* Obtain the line for the requested pin */
    struct gpiod_line *line = gpiod_chip_get_line(chip, (unsigned int)pin);
    if (!line) {
        perror("gpiod_chip_get_line");
        gpiod_chip_close(chip);
        return EXIT_FAILURE;
    }

    /* Request the line as input */
    if (gpiod_line_request_input(line, "gpio_read") < 0) {
        perror("gpiod_line_request_input");
        gpiod_chip_close(chip);
        return EXIT_FAILURE;
    }

    /* Read the value */
    int value = gpiod_line_get_value(line);
    if (value < 0) {
        perror("gpiod_line_get_value");
        gpiod_line_release(line);
        gpiod_chip_close(chip);
        return EXIT_FAILURE;
    }

    printf("GPIO pin %d = %d\n", pin, value);

    /* Bug 3: VLA sized by unchecked pin number */
    log_pin_event(pin, value);

    /* Bug 4: --label flag triggers strcpy into tiny stack buffer */
    if (argc >= 3 && strcmp(argv[2], "--label") == 0) {
        const char *consumer = gpiod_line_consumer(line);
        if (consumer) {
            print_label(consumer);  /* Bug 4 fires if label > 7 chars */
        } else {
            printf("Consumer label: (none)\n");
        }
    }

    gpiod_line_release(line);
    gpiod_chip_close(chip);
    return EXIT_SUCCESS;
}
