extern int snprintf(char *str, unsigned long size, const char *format, ...);
extern void klee_make_symbolic(void *addr, unsigned long nbytes, const char *name);
extern void klee_assume(int condition);
extern void klee_assert(int condition);

static char *__eclipse_int_to_string(int value, char *buffer, int buffer_size)
{
  snprintf(buffer, buffer_size, "%d", value);
  return buffer;
}


static int parse_int(const char *text)
{
  int value = 0;
  int index = 0;
  int __eclipse_loop_bound_0 = 0;
  while ((text[index] != '\0') && (__eclipse_loop_bound_0 < 10))
  {
    char digit = text[index];
    if ((digit < '0') || (digit > '9'))
    {
      return -1;
    }
    value = (value * 10) + (digit - '0');
    index++;
    __eclipse_loop_bound_0++;
  }

  return value;
}



int __eclipse_original_main(int argc, char **argv)
{
  int cursor = 1;
  int count = 1;
  if (((cursor + 1) < argc) && (argv[cursor][0] == '-'))
  {
    count = parse_int(argv[cursor + 1]);
    cursor += 2;
  }
  if ((cursor < argc) && (argv[cursor][0] != '\0'))
  {
    return count + argv[cursor][0];
  }
  return count;
}

int main(void)
{
  int __eclipse_argc = 1;
  char *__eclipse_argv[5];
  __eclipse_argv[0] = "count-and-label";
  int __eclipse_use_count_flag;
  klee_make_symbolic(&__eclipse_use_count_flag, sizeof(__eclipse_use_count_flag), "count_flag_present");
  klee_assume((__eclipse_use_count_flag == 0) || (__eclipse_use_count_flag == 1));
  int __eclipse_count_flag_spelling;
  klee_make_symbolic(&__eclipse_count_flag_spelling, sizeof(__eclipse_count_flag_spelling), "count_flag_spelling");
  klee_assume((__eclipse_count_flag_spelling >= 0) && (__eclipse_count_flag_spelling <= 1));
  int sym_count_value;
  klee_make_symbolic(&sym_count_value, sizeof(sym_count_value), "count_value");
  klee_assume((sym_count_value >= 1) && (sym_count_value <= 12));
  char __eclipse_count_value_value[3];
  int __eclipse_use_label;
  klee_make_symbolic(&__eclipse_use_label, sizeof(__eclipse_use_label), "label_present");
  klee_assume((__eclipse_use_label == 0) || (__eclipse_use_label == 1));
  int __eclipse_label_length;
  klee_make_symbolic(&__eclipse_label_length, sizeof(__eclipse_label_length), "label_length");
  klee_assume((__eclipse_label_length >= 1) && (__eclipse_label_length <= 5));
  char sym_label[6];
  klee_make_symbolic(sym_label, sizeof(sym_label), "label");
  klee_assume(sym_label[__eclipse_label_length] == '\0');
  klee_assume((__eclipse_label_length <= 0) || (sym_label[0] != '\0'));
  klee_assume((__eclipse_label_length <= 1) || (sym_label[1] != '\0'));
  klee_assume((__eclipse_label_length <= 2) || (sym_label[2] != '\0'));
  klee_assume((__eclipse_label_length <= 3) || (sym_label[3] != '\0'));
  klee_assume((__eclipse_label_length <= 4) || (sym_label[4] != '\0'));
  if (__eclipse_use_count_flag)
  {
    if (__eclipse_count_flag_spelling == 0)
    {
      __eclipse_argv[__eclipse_argc] = "-n";
      __eclipse_argc++;
    }
    if (__eclipse_count_flag_spelling == 1)
    {
      __eclipse_argv[__eclipse_argc] = "--count";
      __eclipse_argc++;
    }
  }
  if (__eclipse_use_count_flag)
  {
    __eclipse_argv[__eclipse_argc] = __eclipse_int_to_string(sym_count_value, __eclipse_count_value_value, sizeof(__eclipse_count_value_value));
    __eclipse_argc++;
  }
  if (__eclipse_use_label)
  {
    __eclipse_argv[__eclipse_argc] = sym_label;
    __eclipse_argc++;
  }
  __eclipse_argv[__eclipse_argc] = 0;
  return __eclipse_original_main(__eclipse_argc, __eclipse_argv);
}


