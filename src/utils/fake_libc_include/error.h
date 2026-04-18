#ifndef _FAKE_ERROR_H
#define _FAKE_ERROR_H

extern void (*error_print_progname)(void);
extern unsigned int error_message_count;
extern int error_one_per_line;

void error(int status, int errnum, const char *format, ...);
void error_at_line(
    int status,
    int errnum,
    const char *filename,
    unsigned int line_number,
    const char *format,
    ...
);

#endif
