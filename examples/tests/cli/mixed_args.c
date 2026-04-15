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

int parse_int(char *value) {
    int result = 0;
    int i = 0;

    while (value[i] != '\0') {
        result = (result * 10) + (value[i] - '0');
        i++;
    }

    return result;
}

int main(int argc, char **argv) {
    int verbose = argc == 6;

    if (argc != 5 && argc != 6) {
        return 1;
    }

    if (!same_flag(argv[1], "--pin")) {
        return 2;
    }

    if (!same_flag(argv[3], "--mode")) {
        return 3;
    }

    if (verbose && !same_flag(argv[5], "--verbose")) {
        return 4;
    }

    return (parse_int(argv[2]) == 7) && (argv[4][0] == 'r') && verbose;
}
