typedef struct {
    int values[32];
    int head;
    int tail;
    int size;
} Queue;

int global_counter = 0;
int device_status = 0;
int checksum_acc = 0;

void q_init(Queue *q) {
    int i;
    q->head = 0;
    q->tail = 0;
    q->size = 0;
    for (i = 0; i < 32; i++) {
        q->values[i] = 0;
    }
}

int q_empty(Queue *q) {
    return q->size == 0;
}

int q_full(Queue *q) {
    return q->size == 32;
}

void q_push(Queue *q, int v) {
    if (!q_full(q)) {
        q->values[q->tail] = v;
        q->tail = (q->tail + 1) % 32;
        q->size = q->size + 1;
    }
}

int q_pop(Queue *q) {
    int out;
    out = -1;
    if (!q_empty(q)) {
        out = q->values[q->head];
        q->head = (q->head + 1) % 32;
        q->size = q->size - 1;
    }
    return out;
}

int pseudo_hash_step(int x, int y) {
    int v;
    v = x * 31 + y * 17 + checksum_acc;
    v = v ^ (v << 3);
    v = v ^ (v >> 5);
    v = v + global_counter;
    return v & 2147483647;
}

void init_grid(int grid[12][12]) {
    int i;
    int j;
    for (i = 0; i < 12; i++) {
        for (j = 0; j < 12; j++) {
            grid[i][j] = (i * j + j + 7) % 23;
        }
    }
}

void diffuse_grid(int grid[12][12]) {
    int scratch[12][12];
    int round;
    int i;
    int j;

    for (round = 0; round < 20; round++) {
        for (i = 1; i < 11; i++) {
            for (j = 1; j < 11; j++) {
                scratch[i][j] =
                    (grid[i][j] +
                     grid[i - 1][j] +
                     grid[i + 1][j] +
                     grid[i][j - 1] +
                     grid[i][j + 1]) / 5;
            }
        }

        for (i = 1; i < 11; i++) {
            for (j = 1; j < 11; j++) {
                grid[i][j] = scratch[i][j];
            }
        }
    }
}

int poll_device_until_ready(void) {
    int attempts;
    attempts = 0;

    while (device_status != 3) {
        if ((attempts % 4) == 0) {
            device_status = device_status + 1;
        } else if ((attempts % 7) == 0) {
            device_status = device_status + 2;
        } else {
            device_status = device_status;
        }

        if (device_status > 3) {
            device_status = 3;
        }

        attempts = attempts + 1;
    }

    return attempts;
}

void fill_buffer(char buf[64]) {
    int i;
    for (i = 0; i < 63; i++) {
        buf[i] = 'A' + (i % 26);
    }
    buf[63] = '\0';
}

int sentinel_scan(char buf[64]) {
    int i;
    int count;
    i = 0;
    count = 0;

    while (buf[i] != '\0') {
        if (buf[i] == 'M' || buf[i] == 'N' || buf[i] == 'O') {
            count = count + 1;
        }
        i = i + 1;
    }

    return count;
}

void mutate_buffer(char buf[64]) {
    int i;
    i = 0;

    do {
        if ((i % 3) == 0) {
            buf[i] = (char)(((buf[i] - 'A' + 1) % 26) + 'A');
        } else if ((i % 5) == 0) {
            buf[i] = (char)(((buf[i] - 'A' + 2) % 26) + 'A');
        }
        i = i + 1;
    } while (i < 63);
}

void enqueue_work(Queue *q, int grid[12][12]) {
    int i;
    int j;
    for (i = 0; i < 12; i++) {
        for (j = 0; j < 12; j++) {
            if (((grid[i][j] + i + j) % 4) == 0) {
                q_push(q, grid[i][j] + i * 100 + j);
            }
        }
    }
}

int process_queue(Queue *q) {
    int processed;
    int item;

    processed = 0;
    while (!q_empty(q)) {
        item = q_pop(q);

        if (item >= 0) {
            checksum_acc = checksum_acc ^ pseudo_hash_step(item, processed);

            if ((item % 9) == 0 && !q_full(q)) {
                q_push(q, item / 3 + 11);
            }
            if ((item % 11) == 0 && !q_full(q)) {
                q_push(q, item / 2 + 7);
            }

            processed = processed + 1;
        }
    }

    return processed;
}

int fixed_point_iteration(int start) {
    int current;
    int prev;
    int iter;

    current = start;
    prev = -1;
    iter = 0;

    while (current != prev) {
        prev = current;
        current = (current / 2) + (current % 7) + 3;
        iter = iter + 1;

        if ((iter % 5) == 0) {
            current = current - 1;
        }
    }

    return current + iter;
}

int nested_search(int grid[12][12], int target_mod) {
    int found;
    int pass;
    int i;
    int j;

    found = 0;
    for (pass = 0; pass < 6; pass++) {
        for (i = 0; i < 12; i++) {
            for (j = 0; j < 12; j++) {
                if (((grid[i][j] + pass + i * j) % 13) == target_mod) {
                    found = found + 1;
                }
            }
        }
    }

    return found;
}

int expensive_mixer(int seed) {
    int x;
    int outer;
    int k;

    x = seed;
    outer = 0;

    while (outer < 15) {
        for (k = 0; k < 25; k++) {
            x = x ^ (x << 1);
            x = x + k + outer;
            x = x ^ (x >> 3);
            x = x & 2147483647;
        }
        outer = outer + 1;
    }

    return x;
}

int main() {
    int grid[12][12];
    char buf[64];
    Queue q;

    int letters;
    int processed;
    int device_attempts;
    int fix;
    int matches;
    int mixed;

    q_init(&q);
    init_grid(grid);
    diffuse_grid(grid);

    fill_buffer(buf);
    mutate_buffer(buf);

    letters = sentinel_scan(buf);
    enqueue_work(&q, grid);
    processed = process_queue(&q);

    device_attempts = poll_device_until_ready();
    fix = fixed_point_iteration(123456);
    matches = nested_search(grid, 5);
    mixed = expensive_mixer(fix + matches + processed + letters);

    global_counter = device_attempts + fix + matches + mixed + processed + letters;

    return global_counter;
}