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

int helper(int pin) {
    return pin + 1;
}

int main(int argc, char **argv) {
    if (argc != 3) {
        return 1;
    }

    if (!same_flag(argv[1], "--pin")) {
        return 2;
    }

    return helper(parse_int(argv[2]));
}
