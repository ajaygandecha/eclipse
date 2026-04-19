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

int __eclipse_original_main(int argc, char *argv[])
{
  if (argc != 3)
  {
    fprintf(stderr, "Usage: %s (-c | -l | -f) <word>\n", argv[0]);
    return 1;
  }
  char *mode = argv[1];
  char *word = argv[2];
  if (strcmp(mode, "-c") == 0)
  {
    char buffer[4];
    int j = 0;
    size_t len = strlen(word);
    int __eclipse_loop_bound_0 = 0;
    for (int r = 0; (r < 3) && (__eclipse_loop_bound_0 < 10); r++)
    {
      int __eclipse_loop_bound_1 = 0;
      for (size_t i = 0; (i < len) && (__eclipse_loop_bound_1 < 10); i++)
      {
        buffer[j++] = word[i];
        __eclipse_loop_bound_1++;
      }

      __eclipse_loop_bound_0++;
    }

    buffer[j] = '\0';
    printf("Copied string: %s\n", buffer);
  }
  else
    if (strcmp(mode, "-l") == 0)
  {
    char *status = "READY";
    if (word[0] != '\0')
    {
      status[0] = word[0];
    }
    printf("Status: %s\n", status);
  }
  else
    if (strcmp(mode, "-f") == 0)
  {
    size_t len = strlen(word);
    char *heap = malloc(len + 1);
    if (heap == 0)
    {
      fprintf(stderr, "malloc failed\n");
      return 1;
    }
    strcpy(heap, word);
    if (len > 0)
    {
      free(heap + 1);
    }
    else
    {
      free(heap);
    }
    printf("Freed word buffer\n");
  }
  else
  {
    fprintf(stderr, "Usage: %s (-c | -l | -f) <word>\n", argv[0]);
    return 1;
  }
  return 0;
}

int main(void)
{
  int __eclipse_argc = 1;
  char *__eclipse_argv[4];
  __eclipse_argv[0] = "buggy";
  int __eclipse_mode_spelling;
  klee_make_symbolic(&__eclipse_mode_spelling, sizeof(__eclipse_mode_spelling), "mode_spelling");
  klee_assume((__eclipse_mode_spelling >= 0) && (__eclipse_mode_spelling <= 2));
  int __eclipse_word_length;
  klee_make_symbolic(&__eclipse_word_length, sizeof(__eclipse_word_length), "word_length");
  klee_assume((__eclipse_word_length >= 1) && (__eclipse_word_length <= 4));
  char sym_word[5];
  klee_make_symbolic(sym_word, sizeof(sym_word), "word");
  klee_assume(sym_word[__eclipse_word_length] == '\0');
  klee_assume((__eclipse_word_length <= 0) || (sym_word[0] != '\0'));
  klee_assume((__eclipse_word_length <= 1) || (sym_word[1] != '\0'));
  klee_assume((__eclipse_word_length <= 2) || (sym_word[2] != '\0'));
  klee_assume((__eclipse_word_length <= 3) || (sym_word[3] != '\0'));
  if (__eclipse_mode_spelling == 0)
  {
    __eclipse_argv[__eclipse_argc] = "-c";
    __eclipse_argc++;
  }
  if (__eclipse_mode_spelling == 1)
  {
    __eclipse_argv[__eclipse_argc] = "-l";
    __eclipse_argc++;
  }
  if (__eclipse_mode_spelling == 2)
  {
    __eclipse_argv[__eclipse_argc] = "-f";
    __eclipse_argc++;
  }
  __eclipse_argv[__eclipse_argc] = sym_word;
  __eclipse_argc++;
  __eclipse_argv[__eclipse_argc] = 0;
  return __eclipse_original_main(__eclipse_argc, __eclipse_argv);
}


