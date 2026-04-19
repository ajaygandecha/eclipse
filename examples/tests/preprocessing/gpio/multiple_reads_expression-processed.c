extern int snprintf(char *str, unsigned long size, const char *format, ...);
extern void klee_assert(int condition);

static char *__eclipse_int_to_string(int value, char *buffer, int buffer_size)
{
  snprintf(buffer, buffer_size, "%d", value);
  return buffer;
}


struct gpiod_line;

void klee_make_symbolic(void *addr, int nbytes, char *name);
void klee_assume(int expr);
int gpiod_line_get_value(struct gpiod_line *line);

int __eclipse_original_main()
{
  struct gpiod_line *left;
  struct gpiod_line *right;
  int __eclipse_gpio_value_0;
  klee_make_symbolic(&__eclipse_gpio_value_0, sizeof(__eclipse_gpio_value_0), "__eclipse_gpio_value_0");
  klee_assume((__eclipse_gpio_value_0 == 0) || (__eclipse_gpio_value_0 == 1));
  int __eclipse_gpio_value_1;
  klee_make_symbolic(&__eclipse_gpio_value_1, sizeof(__eclipse_gpio_value_1), "__eclipse_gpio_value_1");
  klee_assume((__eclipse_gpio_value_1 == 0) || (__eclipse_gpio_value_1 == 1));
  if (__eclipse_gpio_value_0 && __eclipse_gpio_value_1)
  {
    return 1;
  }
  return 0;
}

int main(void)
{
  return __eclipse_original_main();
}


