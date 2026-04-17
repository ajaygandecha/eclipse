int same_flag(char *left, char *right) {
    int i = 0;

    while (left[i] != '\0' && right[i] != '\0') {
        if (left[i] != right[i]) {
            return 0;
        }
        i++;
    }

    return left[i] == right[i];
}

int main(int argc, char **argv) {
    int index = 1;
    int no_newline = 0;
    int total = 0;

    if (index < argc && same_flag(argv[index], "-n")) {
        no_newline = 1;
        index++;
    }

    while (index < argc) {
        total += argv[index][0];
        index++;
    }

    return no_newline + total;
}
