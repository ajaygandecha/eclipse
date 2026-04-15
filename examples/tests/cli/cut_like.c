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
    int i = 1;
    int mode = 0;
    int mode_count = 0;
    int saw_delimiter = 0;
    int saw_whitespace = 0;
    int saw_only_delimited = 0;
    int saw_no_partial = 0;
    int saw_complement = 0;
    int saw_zero_terminated = 0;
    int file_count = 0;

    while (i < argc) {
        if (same_flag(argv[i], "--bytes")) {
            mode = 1;
            mode_count++;
            i += 2;
        } else if (same_flag(argv[i], "--characters")) {
            mode = 2;
            mode_count++;
            i += 2;
        } else if (same_flag(argv[i], "--fields")) {
            mode = 3;
            mode_count++;
            i += 2;
        } else if (same_flag(argv[i], "--delimiter")) {
            saw_delimiter = 1;
            i += 2;
        } else if (same_flag(argv[i], "--whitespace-delimited")
                   || same_flag(argv[i], "--whitespace-delimited=trimmed")) {
            saw_whitespace = 1;
            i++;
        } else if (same_flag(argv[i], "--only-delimited")) {
            saw_only_delimited = 1;
            i++;
        } else if (same_flag(argv[i], "--no-partial")) {
            saw_no_partial = 1;
            i++;
        } else if (same_flag(argv[i], "--output-delimiter")) {
            i += 2;
        } else if (same_flag(argv[i], "--complement")) {
            saw_complement = 1;
            i++;
        } else if (same_flag(argv[i], "--zero-terminated")) {
            saw_zero_terminated = 1;
            i++;
        } else {
            file_count++;
            i++;
        }
    }

    if (mode_count != 1) {
        return 10;
    }

    if (saw_delimiter && saw_whitespace) {
        return 11;
    }

    if (saw_delimiter && mode != 3) {
        return 12;
    }

    if (saw_only_delimited && mode != 3) {
        return 13;
    }

    if (saw_no_partial && mode != 1) {
        return 14;
    }

    return saw_complement + saw_zero_terminated + file_count;
}
