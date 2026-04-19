//
// This program repeats the input string `count` times.
// The bug is that the output buffer is only sized for 4x the input length.
//

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(int argc, char *argv[]) {
    if (argc != 3) {
        fprintf(stderr, "Usage: %s <word> <count>\n", argv[0]);
        return 1;
    }

    char *word = argv[1];
    int count = atoi(argv[2]);
    size_t len = strlen(word);

    if(count > 9999) return 0;

    char *buffer = malloc((4 * len) + 1);
    if (buffer == NULL) {
        fprintf(stderr, "malloc failed\n");
        return 1;
    }

    size_t j = 0;

    for (int k = 0; k < count; k++) {
        for (size_t i = 0; i < len; i++) {
            buffer[j++] = word[i];   // safe for count <= 4, overflow for count > 4
        }
    }

    buffer[j] = '\0';

    printf("Expanded word: %s\n", buffer);

    free(buffer);
    return 0;
}
