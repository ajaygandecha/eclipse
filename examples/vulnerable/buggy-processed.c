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


int main(int argc, char *argv[])
{
  if (argc != 3)
  {
    fprintf(stderr, "Usage: %s (--copy | --literal) <word>\n", argv[0]);
    return 1;
  }
  char *mode = argv[1];
  char *word = argv[2];
  if (strcmp(mode, "--copy") == 0)
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
    if (strcmp(mode, "--literal") == 0)
  {
    char *status = "READY";
    if (word[0] != '\0')
    {
      status[0] = word[0];
    }
    printf("Status: %s\n", status);
  }
  else
  {
    fprintf(stderr, "Usage: %s (--copy | --literal) <word>\n", argv[0]);
    return 1;
  }
  return 0;
}
