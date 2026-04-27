extern int snprintf(char *str, unsigned long size, const char *format, ...);
extern void klee_make_symbolic(void *addr, unsigned long nbytes, const char *name);
extern void klee_assume(int condition);
extern void klee_assert(int condition);

static char *__eclipse_int_to_string(int value, char *buffer, int buffer_size)
{
  snprintf(buffer, buffer_size, "%d", value);
  return buffer;
}




int __eclipse_original_main()
{
  int __eclipse_loop_bound_0 = 0;
  for (int i = 0; (i < 1000) && (__eclipse_loop_bound_0 < 10); i++)
  {
    i++;
    __eclipse_loop_bound_0++;
  }

  return 0;
}

int main(void)
{
  return __eclipse_original_main();
}


