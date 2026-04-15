#ifndef _UCHAR_H
#define _UCHAR_H

#include <stddef.h>

typedef int mbstate_t;
typedef int char16_t;
typedef int char32_t;

size_t mbrtoc32(char32_t *, const char *, size_t, mbstate_t *);
size_t c32rtomb(char *, char32_t, mbstate_t *);

#endif
