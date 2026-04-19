struct gpiod_line;

void klee_make_symbolic(void *addr, int nbytes, char *name);
void klee_assume(int expr);
int gpiod_line_get_value(struct gpiod_line *line);

int main() {
    struct gpiod_line *line;
    int val = gpiod_line_get_value(line);
    return 0;
}
