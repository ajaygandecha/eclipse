extern int snprintf(char *str, unsigned long size, const char *format, ...);
extern void klee_make_symbolic(void *addr, unsigned long nbytes, const char *name);
extern void klee_assume(int condition);
extern void klee_assert(int condition);

static char *__eclipse_int_to_string(int value, char *buffer, int buffer_size)
{
  snprintf(buffer, buffer_size, "%d", value);
  return buffer;
}


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

static void cleanup_request(struct gpiod_line_request *request)
{
  if (request != 0)
  {
    gpiod_line_request_release(request);
  }
}



static void cleanup_config(struct gpiod_line_config *line_cfg, struct gpiod_line_settings *settings, struct gpiod_request_config *req_cfg, struct gpiod_chip *chip)
{
  if (line_cfg != 0)
  {
    gpiod_line_config_free(line_cfg);
  }
  if (settings != 0)
  {
    gpiod_line_settings_free(settings);
  }
  if (req_cfg != 0)
  {
    gpiod_request_config_free(req_cfg);
  }
  if (chip != 0)
  {
    gpiod_chip_close(chip);
  }
}



int __eclipse_original_main(int argc, char *argv[])
{
  struct gpiod_chip *chip = 0;
  struct gpiod_request_config *req_cfg = 0;
  struct gpiod_line_settings *settings = 0;
  struct gpiod_line_config *line_cfg = 0;
  struct gpiod_line_request *request = 0;
  unsigned int offsets[3] = {17, 27, 22};
  if (argc != 3)
  {
    fprintf(stderr, "Usage: %s <cycles> <zone>\n", argv[0]);
    return 1;
  }
  int cycles = atoi(argv[1]);
  char *zone = argv[2];
  chip = gpiod_chip_open("/dev/gpiochip0");
  if (chip == 0)
  {
    perror("gpiod_chip_open");
    return 1;
  }
  req_cfg = gpiod_request_config_new();
  if (req_cfg == 0)
  {
    perror("gpiod_request_config_new");
    cleanup_config(0, 0, 0, chip);
    return 1;
  }
  gpiod_request_config_set_consumer(req_cfg, "irrigation-controller");
  settings = gpiod_line_settings_new();
  if (settings == 0)
  {
    perror("gpiod_line_settings_new");
    cleanup_config(0, 0, req_cfg, chip);
    return 1;
  }
  if (gpiod_line_settings_set_direction(settings, 1) < 0)
  {
    perror("gpiod_line_settings_set_direction");
    cleanup_config(0, settings, req_cfg, chip);
    return 1;
  }
  line_cfg = gpiod_line_config_new();
  if (line_cfg == 0)
  {
    perror("gpiod_line_config_new");
    cleanup_config(0, settings, req_cfg, chip);
    return 1;
  }
  if (gpiod_line_config_add_line_settings(line_cfg, offsets, 3, settings) < 0)
  {
    perror("gpiod_line_config_add_line_settings");
    cleanup_config(line_cfg, settings, req_cfg, chip);
    return 1;
  }
  request = gpiod_chip_request_lines(chip, req_cfg, line_cfg);
  if (request == 0)
  {
    perror("gpiod_chip_request_lines");
    cleanup_config(line_cfg, settings, req_cfg, chip);
    return 1;
  }
  int protocol_state = 0;
  {
    int __eclipse_loop_bound_0 = 0;
    for (int i = 0; (i < cycles) && (__eclipse_loop_bound_0 < 10); i++)
    {
      int __eclipse_gpio_value_0;
      klee_make_symbolic(&__eclipse_gpio_value_0, sizeof(__eclipse_gpio_value_0), "__eclipse_gpio_value_0");
      klee_assume((__eclipse_gpio_value_0 == 0) || (__eclipse_gpio_value_0 == 1));
      int moisture = __eclipse_gpio_value_0;
      int __eclipse_gpio_value_1;
      klee_make_symbolic(&__eclipse_gpio_value_1, sizeof(__eclipse_gpio_value_1), "__eclipse_gpio_value_1");
      klee_assume((__eclipse_gpio_value_1 == 0) || (__eclipse_gpio_value_1 == 1));
      int override = __eclipse_gpio_value_1;
      int __eclipse_gpio_value_2;
      klee_make_symbolic(&__eclipse_gpio_value_2, sizeof(__eclipse_gpio_value_2), "__eclipse_gpio_value_2");
      klee_assume((__eclipse_gpio_value_2 == 0) || (__eclipse_gpio_value_2 == 1));
      int tankempty = __eclipse_gpio_value_2;
      if (((moisture < 0) || (override < 0)) || (tankempty < 0))
      {
        perror("gpiod_line_request_get_value");
        cleanup_request(request);
        cleanup_config(line_cfg, settings, req_cfg, chip);
        return 1;
      }
      if ((((protocol_state == 0) && (moisture == 0)) && (override == 0)) && (tankempty == 0))
      {
        protocol_state = 1;
      }
      else
        if ((((protocol_state == 1) && (moisture == 1)) && (override == 0)) && (tankempty == 0))
      {
        protocol_state = 2;
      }
      else
        if ((((protocol_state == 2) && (moisture == 0)) && (override == 1)) && (tankempty == 0))
      {
        protocol_state = 3;
      }
      else
        if ((((protocol_state == 3) && (moisture == 1)) && (override == 1)) && (tankempty == 0))
      {
        protocol_state = 4;
      }
      else
        if ((((protocol_state == 4) && (moisture == 0)) && (override == 1)) && (tankempty == 1))
      {
        char event[8];
        event[0] = '\0';
        strcpy(event, "ZONE:");
        strcat(event, zone);
        strcat(event, ":OPEN");
        printf("Maintenance event for %s\n", event);
        cleanup_request(request);
        cleanup_config(line_cfg, settings, req_cfg, chip);
        return 0;
      }
      else
      {
        protocol_state = 0;
      }
      __eclipse_loop_bound_0++;
    }

  }
  printf("No maintenance action for zone %s\n", zone);
  cleanup_request(request);
  cleanup_config(line_cfg, settings, req_cfg, chip);
  return 0;
}

int main(void)
{
  int __eclipse_argc = 1;
  char *__eclipse_argv[4];
  __eclipse_argv[0] = "irrigation-controller";
  int sym_cycles;
  klee_make_symbolic(&sym_cycles, sizeof(sym_cycles), "cycles");
  klee_assume((sym_cycles >= 1) && (sym_cycles <= 99999));
  char __eclipse_cycles_value[6];
  int __eclipse_zone_length;
  klee_make_symbolic(&__eclipse_zone_length, sizeof(__eclipse_zone_length), "zone_length");
  klee_assume((__eclipse_zone_length >= 1) && (__eclipse_zone_length <= 5));
  char sym_zone[6];
  klee_make_symbolic(sym_zone, sizeof(sym_zone), "zone");
  klee_assume(sym_zone[__eclipse_zone_length] == '\0');
  klee_assume((__eclipse_zone_length <= 0) || (sym_zone[0] != '\0'));
  klee_assume((__eclipse_zone_length <= 1) || (sym_zone[1] != '\0'));
  klee_assume((__eclipse_zone_length <= 2) || (sym_zone[2] != '\0'));
  klee_assume((__eclipse_zone_length <= 3) || (sym_zone[3] != '\0'));
  klee_assume((__eclipse_zone_length <= 4) || (sym_zone[4] != '\0'));
  __eclipse_argv[__eclipse_argc] = __eclipse_int_to_string(sym_cycles, __eclipse_cycles_value, sizeof(__eclipse_cycles_value));
  __eclipse_argc++;
  __eclipse_argv[__eclipse_argc] = sym_zone;
  __eclipse_argc++;
  __eclipse_argv[__eclipse_argc] = 0;
  return __eclipse_original_main(__eclipse_argc, __eclipse_argv);
}


