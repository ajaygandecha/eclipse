#ifndef _STDCOUNTOF_H
#define _STDCOUNTOF_H

#include <stddef.h>

#define countof(a) ((size_t) (sizeof (a) / sizeof ((a)[0])))

#endif
