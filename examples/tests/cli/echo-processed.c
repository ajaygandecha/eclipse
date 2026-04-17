extern int snprintf(char *str, int size, const char *format, ...);
extern void klee_make_symbolic(void *addr, unsigned long nbytes, const char *name);
extern void klee_assume(int condition);
extern void klee_assert(int condition);

static char *__eclipse_int_to_string(int value, char *buffer, int buffer_size)
{
  snprintf(buffer, buffer_size, "%d", value);
  return buffer;
}

int same_flag(char *left, char *right)
{
  int i = 0;
  int __eclipse_loop_bound_0 = 0;
  while (((left[i] != '\0') && (right[i] != '\0')) && (__eclipse_loop_bound_0 < 10))
  {
    if (left[i] != right[i])
    {
      return 0;
    }
    i++;
    __eclipse_loop_bound_0++;
  }

  return left[i] == right[i];
}

int __eclipse_original_main(int argc, char **argv)
{
  int index = 1;
  int no_newline = 0;
  int total = 0;
  if ((index < argc) && same_flag(argv[index], "-n"))
  {
    no_newline = 1;
    index++;
  }
  int __eclipse_loop_bound_1 = 0;
  while ((index < argc) && (__eclipse_loop_bound_1 < 10))
  {
    total += argv[index][0];
    index++;
    __eclipse_loop_bound_1++;
  }

  return no_newline + total;
}

int main(void)
{
  int __eclipse_argc = 1;
  char *__eclipse_argv[5];
  __eclipse_argv[0] = "echo";
  int __eclipse_use_no_newline;
  klee_make_symbolic(&__eclipse_use_no_newline, sizeof(__eclipse_use_no_newline), "no_newline_present");
  klee_assume((__eclipse_use_no_newline == 0) || (__eclipse_use_no_newline == 1));
  int __eclipse_use_msg1;
  klee_make_symbolic(&__eclipse_use_msg1, sizeof(__eclipse_use_msg1), "msg1_present");
  klee_assume((__eclipse_use_msg1 == 0) || (__eclipse_use_msg1 == 1));
  int __eclipse_msg1_length;
  klee_make_symbolic(&__eclipse_msg1_length, sizeof(__eclipse_msg1_length), "msg1_length");
  klee_assume((__eclipse_msg1_length >= 0) && (__eclipse_msg1_length <= 4));
  char sym_msg1[5];
  klee_make_symbolic(sym_msg1, sizeof(sym_msg1), "msg1");
  klee_assume(sym_msg1[__eclipse_msg1_length] == '\0');
  klee_assume((__eclipse_msg1_length <= 0) || (sym_msg1[0] != '\0'));
  klee_assume((__eclipse_msg1_length <= 1) || (sym_msg1[1] != '\0'));
  klee_assume((__eclipse_msg1_length <= 2) || (sym_msg1[2] != '\0'));
  klee_assume((__eclipse_msg1_length <= 3) || (sym_msg1[3] != '\0'));
  int __eclipse_use_msg2;
  klee_make_symbolic(&__eclipse_use_msg2, sizeof(__eclipse_use_msg2), "msg2_present");
  klee_assume((__eclipse_use_msg2 == 0) || (__eclipse_use_msg2 == 1));
  int __eclipse_msg2_length;
  klee_make_symbolic(&__eclipse_msg2_length, sizeof(__eclipse_msg2_length), "msg2_length");
  klee_assume((__eclipse_msg2_length >= 0) && (__eclipse_msg2_length <= 4));
  char sym_msg2[5];
  klee_make_symbolic(sym_msg2, sizeof(sym_msg2), "msg2");
  klee_assume(sym_msg2[__eclipse_msg2_length] == '\0');
  klee_assume((__eclipse_msg2_length <= 0) || (sym_msg2[0] != '\0'));
  klee_assume((__eclipse_msg2_length <= 1) || (sym_msg2[1] != '\0'));
  klee_assume((__eclipse_msg2_length <= 2) || (sym_msg2[2] != '\0'));
  klee_assume((__eclipse_msg2_length <= 3) || (sym_msg2[3] != '\0'));
  if (__eclipse_use_no_newline)
  {
    __eclipse_argv[__eclipse_argc] = "-n";
    __eclipse_argc++;
  }
  if (__eclipse_use_msg1)
  {
    __eclipse_argv[__eclipse_argc] = sym_msg1;
    __eclipse_argc++;
  }
  if (__eclipse_use_msg2)
  {
    __eclipse_argv[__eclipse_argc] = sym_msg2;
    __eclipse_argc++;
  }
  __eclipse_argv[__eclipse_argc] = 0;
  return __eclipse_original_main(__eclipse_argc, __eclipse_argv);
}

