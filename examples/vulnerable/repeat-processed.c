extern int snprintf(char *str, unsigned long size, const char *format, ...);
extern void klee_make_symbolic(void *addr, unsigned long nbytes, const char *name);
extern void klee_assume(int condition);
extern void klee_assert(int condition);

static char *__eclipse_int_to_string(int value, char *buffer, int buffer_size)
{
  snprintf(buffer, buffer_size, "%d", value);
  return buffer;
}


//
// This program repeats the input string `count` times.
// The bug is that the output buffer is only sized for 4x the input length.
//

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int __eclipse_original_main(int argc, char *argv[])
{
  if (argc != 3)
  {
    fprintf(stderr, "Usage: %s <word> <count>\n", argv[0]);
    return 1;
  }
  char *word = argv[1];
  int count = atoi(argv[2]);
  size_t len = strlen(word);
  if (count > 9999)
    return 0;
  char *buffer = malloc((4 * len) + 1);
  if (buffer == 0)
  {
    fprintf(stderr, "malloc failed\n");
    return 1;
  }
  size_t j = 0;
  {
    int __eclipse_loop_bound_0 = 0;
    for (int k = 0; (k < count) && (__eclipse_loop_bound_0 < 10); k++)
    {
      {
        int __eclipse_loop_bound_1 = 0;
        for (size_t i = 0; (i < len) && (__eclipse_loop_bound_1 < 10); i++)
        {
          buffer[j++] = word[i];
          __eclipse_loop_bound_1++;
        }

      }
      __eclipse_loop_bound_0++;
    }

  }
  buffer[j] = '\0';
  printf("Expanded word: %s\n", buffer);
  free(buffer);
  return 0;
}

int main(void)
{
  int __eclipse_argc = 1;
  char *__eclipse_argv[4];
  __eclipse_argv[0] = "repeat";
  int __eclipse_word_length;
  klee_make_symbolic(&__eclipse_word_length, sizeof(__eclipse_word_length), "word_length");
  klee_assume((__eclipse_word_length >= 1) && (__eclipse_word_length <= 5));
  char sym_word[6];
  klee_make_symbolic(sym_word, sizeof(sym_word), "word");
  klee_assume(sym_word[__eclipse_word_length] == '\0');
  klee_assume((__eclipse_word_length <= 0) || (sym_word[0] != '\0'));
  klee_assume((__eclipse_word_length <= 1) || (sym_word[1] != '\0'));
  klee_assume((__eclipse_word_length <= 2) || (sym_word[2] != '\0'));
  klee_assume((__eclipse_word_length <= 3) || (sym_word[3] != '\0'));
  klee_assume((__eclipse_word_length <= 4) || (sym_word[4] != '\0'));
  int sym_count;
  klee_make_symbolic(&sym_count, sizeof(sym_count), "count");
  klee_assume((sym_count >= 1) && (sym_count <= 99999));
  char __eclipse_count_value[6];
  __eclipse_argv[__eclipse_argc] = sym_word;
  __eclipse_argc++;
  __eclipse_argv[__eclipse_argc] = __eclipse_int_to_string(sym_count, __eclipse_count_value, sizeof(__eclipse_count_value));
  __eclipse_argc++;
  __eclipse_argv[__eclipse_argc] = 0;
  return __eclipse_original_main(__eclipse_argc, __eclipse_argv);
}


