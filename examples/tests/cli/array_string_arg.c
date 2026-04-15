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
    if (argc != 5) {
        return 1;
    }

    if (!same_flag(argv[1], "--name")) {
        return 2;
    }

    if (!same_flag(argv[3], "--limit")) {
        return 3;
    }

    return (argv[2][0] == 'A') && (parse_int(argv[4]) < 10);
}
