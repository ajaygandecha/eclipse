static int starts_with_dash(const char *text)
{
    return text != 0 && text[0] == '-';
}

int main(int argc, char **argv)
{
    int cursor = 1;
    int loud_mode = 0;

    if (cursor < argc && starts_with_dash(argv[cursor])) {
        loud_mode = 1;
        cursor++;
    }

    if (cursor < argc && argv[cursor][0] != '\0') {
        return loud_mode ? 2 : 1;
    }

    return loud_mode ? 3 : 0;
}
