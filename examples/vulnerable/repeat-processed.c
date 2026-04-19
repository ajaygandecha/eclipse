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

int main(int argc, char *argv[])
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
  int __eclipse_loop_bound_0 = 0;
  for (int k = 0; (k < count) && (__eclipse_loop_bound_0 < 10); k++)
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
  printf("Expanded word: %s\n", buffer);
  free(buffer);
  return 0;
}
