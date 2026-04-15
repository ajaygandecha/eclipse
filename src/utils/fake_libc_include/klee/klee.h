#ifndef KLEE_KLEE_H
#define KLEE_KLEE_H

#include <stddef.h>

void klee_make_symbolic(void *addr, size_t nbytes, const char *name);
void klee_assume(int condition);
void klee_assert(int condition);
void klee_warning(const char *message);
void klee_warning_once(const char *message);
void klee_print_expr(const char *message, ...);
void klee_report_error(const char *file, int line, const char *message, const char *suffix);

#endif
