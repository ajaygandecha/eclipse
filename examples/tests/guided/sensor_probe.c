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

int string_length(char *value) {
    int length = 0;

    while (value[length] != '\0') {
        length++;
    }

    return length;
}

int rolling_checksum(char *payload, int retry_budget) {
    int i = 0;
    int checksum = 0;

    while (payload[i] != '\0') {
        checksum += payload[i] * (i + 1 + retry_budget);
        i++;
    }

    return checksum;
}

int parse_transport_header(char *payload, int sample_count) {
    int payload_length = string_length(payload);
    int score = 0;
    int i = 0;

    while (i < sample_count + 3) {
        int current = payload[i % payload_length];

        if ((current & 1) == 0) {
            score += current;
        } else {
            score -= current;
        }

        if (current == 'A') {
            score += 7;
        } else if (current == 'B') {
            score += 5;
        } else if (current == 'C') {
            score -= 3;
        } else {
            score += i;
        }

        i++;
    }

    return score;
}

int service_watchdog(char *payload, int sample_count) {
    int payload_length = string_length(payload);
    int budget = 0;
    int i = 0;

    while (i < sample_count + 4) {
        int current = payload[(i + 1) % payload_length];

        if (current < 'M') {
            budget += 2;
        } else {
            budget -= 1;
        }

        if (current == 'X' || current == 'Y') {
            budget += 4;
        }

        i++;
    }

    return budget;
}

int collect_telemetry(char *payload, int sample_count) {
    int payload_length = string_length(payload);
    int digest = 1;
    int i = 0;

    while (i < sample_count + 3) {
        int current = payload[i % payload_length];

        if (current == 'Q') {
            digest *= 2;
        } else if (current == 'R') {
            digest += 9;
        } else if ((current % 3) == 0) {
            digest += current;
        } else {
            digest -= i;
        }

        i++;
    }

    return digest;
}

int build_diagnostic_frame(
    char *payload,
    int sample_count,
    int diag_mode
) {
    char frame[4];
    int payload_length = string_length(payload);
    int i = 0;
    int checksum = 0;
    int bytes_to_copy;

    if (payload_length == 0) {
        return 0;
    }

    while (i < 4) {
        frame[i] = 0;
        i++;
    }

    if (diag_mode) {
        bytes_to_copy = sample_count + payload_length + 1;

        i = 0;
        while (i < bytes_to_copy) {
            /* Memory safety bug: bytes_to_copy can exceed the 4-byte frame. */
            frame[i] = payload[i % payload_length];
            i++;
        }
    } else {
        bytes_to_copy = sample_count;
        if (bytes_to_copy > 3) {
            bytes_to_copy = 3;
        }

        i = 0;
        while (i < bytes_to_copy) {
            frame[i] = payload[i % payload_length];
            i++;
        }
    }

    i = 0;
    while (i < 4) {
        checksum += frame[i];
        i++;
    }

    return checksum;
}

int dispatch_probe(char *payload, int sample_count, int diag_mode) {
    int payload_length = string_length(payload);

    if (!diag_mode) {
        return parse_transport_header(payload, sample_count);
    }

    if (payload_length < 2) {
        return service_watchdog(payload, sample_count);
    }

    if (payload[0] == 'Q') {
        return build_diagnostic_frame(payload, sample_count, diag_mode);
    }

    if (payload[0] < 'Q') {
        return collect_telemetry(payload, sample_count);
    }

    return service_watchdog(payload, sample_count);
}

int main(int argc, char **argv) {
    int index = 1;
    int diag_mode = 0;
    int sample_count = 1;
    char *payload = "ok";

    while (index < argc) {
        if (same_flag(argv[index], "-D") || same_flag(argv[index], "--diag")) {
            diag_mode = 1;
            index++;
        } else if (same_flag(argv[index], "-s") || same_flag(argv[index], "--samples")) {
            if (index + 1 >= argc) {
                return 2;
            }
            sample_count = parse_int(argv[index + 1]);
            index += 2;
        } else {
            payload = argv[index];
            break;
        }
    }

    return dispatch_probe(payload, sample_count, diag_mode) +
        rolling_checksum(payload, sample_count);
}
