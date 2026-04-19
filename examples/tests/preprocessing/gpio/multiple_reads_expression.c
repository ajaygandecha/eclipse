struct gpiod_line;

void klee_make_symbolic(void *addr, int nbytes, char *name);
void klee_assume(int expr);
int gpiod_line_get_value(struct gpiod_line *line);

int main() {
    struct gpiod_line *left;
    struct gpiod_line *right;

    if (gpiod_line_get_value(left) && gpiod_line_get_value(right)) {
        return 1;
    }

    return 0;
}
