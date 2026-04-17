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
    int index = 1;
    int count = -1;

    if (index < argc &&
        (same_flag(argv[index], "-n") || same_flag(argv[index], "--lines"))) {
        if (index + 1 >= argc) {
            return 2;
        }
        count = parse_int(argv[index + 1]);
        index += 2;
    }

    if (index < argc) {
        return (count == 7) && (argv[index][0] == 'f');
    }

    return count == 7;
}
