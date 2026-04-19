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

#define CHIP_PATH "/dev/gpiochip0"
#define BUTTON_PIN 17
#define ARMED_PIN  27

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



int main(int argc, char *argv[])
{
  struct gpiod_chip *chip = 0;
  struct gpiod_request_config *req_cfg = 0;
  struct gpiod_line_settings *settings = 0;
  struct gpiod_line_config *line_cfg = 0;
  struct gpiod_line_request *request = 0;
  unsigned int offsets[2] = {17, 27};
  if (argc != 3)
  {
    fprintf(stderr, "Usage: %s <max_polls> <digit>\n", argv[0]);
    return 1;
  }
  int max_polls = atoi(argv[1]);
  char digit = argv[2][0];
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
  gpiod_request_config_set_consumer(req_cfg, "alarm-code-collector");
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
  if (gpiod_line_config_add_line_settings(line_cfg, offsets, 2, settings) < 0)
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
  char code[8];
  int code_len = 0;
  for (int i = 0; i < max_polls; i++)
  {
    int __eclipse_gpio_value_0;
    klee_make_symbolic(&__eclipse_gpio_value_0, sizeof(__eclipse_gpio_value_0), "__eclipse_gpio_value_0");
    int button = __eclipse_gpio_value_0;
    int __eclipse_gpio_value_1;
    klee_make_symbolic(&__eclipse_gpio_value_1, sizeof(__eclipse_gpio_value_1), "__eclipse_gpio_value_1");
    int armed = __eclipse_gpio_value_1;
    if ((button < 0) || (armed < 0))
    {
      perror("gpiod_line_request_get_value");
      cleanup_request(request);
      cleanup_config(line_cfg, settings, req_cfg, chip);
      return 1;
    }
    if ((button == 1) && (armed == 1))
    {
      code[code_len++] = digit;
    }
  }

  code[code_len] = '\0';
  printf("Collected code: %s\n", code);
  cleanup_request(request);
  cleanup_config(line_cfg, settings, req_cfg, chip);
  return 0;
}
