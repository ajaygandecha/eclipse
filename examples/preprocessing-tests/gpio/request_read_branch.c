struct gpiod_line_request;

void klee_make_symbolic(void *addr, int nbytes, char *name);
void klee_assume(int expr);
int gpiod_line_request_get_value(struct gpiod_line_request *request, unsigned int offset);

int main() {
    struct gpiod_line_request *request;
    unsigned int pin = 17;

    if (gpiod_line_request_get_value(request, pin)) {
        return 1;
    }

    return 0;
}
