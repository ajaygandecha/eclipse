extern int snprintf(char *str, unsigned long size, const char *format, ...);
extern void klee_make_symbolic(void *addr, unsigned long nbytes, const char *name);
extern void klee_assume(int condition);
extern void klee_assert(int condition);

static char *__eclipse_int_to_string(int value, char *buffer, int buffer_size)
{
  snprintf(buffer, buffer_size, "%d", value);
  return buffer;
}


static int starts_with_dash(const char *text)
{
  return (text != 0) && (text[0] == '-');
}



int __eclipse_original_main(int argc, char **argv)
{
  int cursor = 1;
  int loud_mode = 0;
  if ((cursor < argc) && starts_with_dash(argv[cursor]))
  {
    loud_mode = 1;
    cursor++;
  }
  if ((cursor < argc) && (argv[cursor][0] != '\0'))
  {
    return (loud_mode) ? (2) : (1);
  }
  return (loud_mode) ? (3) : (0);
}

int main(void)
{
  int __eclipse_argc = 1;
  char *__eclipse_argv[5];
  __eclipse_argv[0] = "flag-and-message";
  int __eclipse_use_loud;
  klee_make_symbolic(&__eclipse_use_loud, sizeof(__eclipse_use_loud), "loud_present");
  klee_assume((__eclipse_use_loud == 0) || (__eclipse_use_loud == 1));
  int __eclipse_loud_spelling;
  klee_make_symbolic(&__eclipse_loud_spelling, sizeof(__eclipse_loud_spelling), "loud_spelling");
  klee_assume((__eclipse_loud_spelling >= 0) && (__eclipse_loud_spelling <= 1));
  int __eclipse_use_message;
  klee_make_symbolic(&__eclipse_use_message, sizeof(__eclipse_use_message), "message_present");
  klee_assume((__eclipse_use_message == 0) || (__eclipse_use_message == 1));
  int __eclipse_message_length;
  klee_make_symbolic(&__eclipse_message_length, sizeof(__eclipse_message_length), "message_length");
  klee_assume((__eclipse_message_length >= 1) && (__eclipse_message_length <= 6));
  char sym_message[7];
  klee_make_symbolic(sym_message, sizeof(sym_message), "message");
  klee_assume(sym_message[__eclipse_message_length] == '\0');
  klee_assume((__eclipse_message_length <= 0) || (sym_message[0] != '\0'));
  klee_assume((__eclipse_message_length <= 1) || (sym_message[1] != '\0'));
  klee_assume((__eclipse_message_length <= 2) || (sym_message[2] != '\0'));
  klee_assume((__eclipse_message_length <= 3) || (sym_message[3] != '\0'));
  klee_assume((__eclipse_message_length <= 4) || (sym_message[4] != '\0'));
  klee_assume((__eclipse_message_length <= 5) || (sym_message[5] != '\0'));
  int __eclipse_use_suffix;
  klee_make_symbolic(&__eclipse_use_suffix, sizeof(__eclipse_use_suffix), "suffix_present");
  klee_assume((__eclipse_use_suffix == 0) || (__eclipse_use_suffix == 1));
  int __eclipse_suffix_length;
  klee_make_symbolic(&__eclipse_suffix_length, sizeof(__eclipse_suffix_length), "suffix_length");
  klee_assume((__eclipse_suffix_length >= 1) && (__eclipse_suffix_length <= 2));
  char sym_suffix[3];
  klee_make_symbolic(sym_suffix, sizeof(sym_suffix), "suffix");
  klee_assume(sym_suffix[__eclipse_suffix_length] == '\0');
  klee_assume((__eclipse_suffix_length <= 0) || (sym_suffix[0] != '\0'));
  klee_assume((__eclipse_suffix_length <= 1) || (sym_suffix[1] != '\0'));
  if (__eclipse_use_loud)
  {
    if (__eclipse_loud_spelling == 0)
    {
      __eclipse_argv[__eclipse_argc] = "-l";
      __eclipse_argc++;
    }
    if (__eclipse_loud_spelling == 1)
    {
      __eclipse_argv[__eclipse_argc] = "--loud";
      __eclipse_argc++;
    }
  }
  if (__eclipse_use_message)
  {
    __eclipse_argv[__eclipse_argc] = sym_message;
    __eclipse_argc++;
  }
  if (__eclipse_use_suffix)
  {
    __eclipse_argv[__eclipse_argc] = sym_suffix;
    __eclipse_argc++;
  }
  __eclipse_argv[__eclipse_argc] = 0;
  return __eclipse_original_main(__eclipse_argc, __eclipse_argv);
}


