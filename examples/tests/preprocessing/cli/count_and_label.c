static int parse_int(const char *text)
{
    int value = 0;
    int index = 0;

    while (text[index] != '\0') {
        char digit = text[index];
        if (digit < '0' || digit > '9') {
            return -1;
        }
        value = (value * 10) + (digit - '0');
        index++;
    }

    return value;
}

int main(int argc, char **argv)
{
    int cursor = 1;
    int count = 1;

    if (cursor + 1 < argc && argv[cursor][0] == '-') {
        count = parse_int(argv[cursor + 1]);
        cursor += 2;
    }

    if (cursor < argc && argv[cursor][0] != '\0') {
        return count + argv[cursor][0];
    }

    return count;
}
