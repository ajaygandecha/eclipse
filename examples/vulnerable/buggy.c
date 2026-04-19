#include <stdio.h>
#include <stdlib.h>
#include <string.h>


int main(int argc, char *argv[]) {
    if (argc != 3) {
        fprintf(stderr, "Usage: %s (-c (copy) | -l (literal)) <word>\n", argv[0]);
        return 1;
    }

    char *mode = argv[1];
    char *word = argv[2];

    if (strcmp(mode, "-c") == 0) {
        /*
         * Bug 1: Ptr error
         *
         * Repeatedly copy the input word into a small fixed-size buffer.
         * If the input is long enough, or repeated enough times, this
         * writes past the end of the buffer.
         */
        char buffer[4];
        int j = 0;
        size_t len = strlen(word);

        for (int r = 0; r < 3; r++) {
            for (size_t i = 0; i < len; i++) {
                buffer[j++] = word[i];   /* Intentional out-of-bounds write */
            }
        }

        buffer[j] = '\0';                /* Also unsafe if j overflowed */
        printf("Copied string: %s\n", buffer);

    } else if (strcmp(mode, "-l") == 0) {
        /*
         * Bug 2: ReadOnly error
         *
         * Point at a string literal and then attempt to modify it.
         * KLEE should treat this as a write to read-only memory.
         */
        char *status = "READY";

        if (word[0] != '\0') {
            status[0] = word[0];         /* Intentional write to read-only memory */
        }

        printf("Status: %s\n", status);

    } else {
        fprintf(stderr, "Usage: %s (-c | -l) <word>\n", argv[0]);
        return 1;
    }

    return 0;
}