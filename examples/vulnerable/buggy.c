#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(int argc, char *argv[]) {
    if (argc != 3) {
        fprintf(stderr, "Usage: %s (-c | -l | -f) <word>\n", argv[0]);
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
         */
        char *status = "READY";

        if (word[0] != '\0') {
            status[0] = word[0];         /* Intentional write to read-only memory */
        }

        printf("Status: %s\n", status);

    } else if (strcmp(mode, "-f") == 0) {
        /*
         * Bug 3: Free error
         *
         * Allocate heap memory, then free a shifted pointer instead of
         * the original base pointer.
         */
        size_t len = strlen(word);
        char *heap = malloc(len + 1);

        if (heap == NULL) {
            fprintf(stderr, "malloc failed\n");
            return 1;
        }

        strcpy(heap, word);

        if (len > 0) {
            free(heap + 1);              /* Intentional invalid free */
        } else {
            free(heap);                  /* Avoid freeing heap+1 when word is empty */
        }

        printf("Freed word buffer\n");

    } else {
        fprintf(stderr, "Usage: %s (-c | -l | -f) <word>\n", argv[0]);
        return 1;
    }

    return 0;
}