# ECLIPSE

*This is a work-in-progress!*

To test running ECLIPSE on the KLEE Getting Started example program, run the following:

```
python3 src/main.py examples/tests/cli/echo.c --cli-config examples/tests/cli/echo.yml
python3 src/main.py examples/tests/cli/head_like.c --cli-config examples/tests/cli/head_like.yml
```

python3 src/main.py examples/coreutils/src/cut.c

Structured CLI modeling now uses the canonical YAML schema in
`templates/cli.yml`. V1 supports:

- `program`
- `entry_point: main`
- `args.argv0`
- ordered `args.elements` entries for `option`, `positional`, and `option_value`

At the moment, `--cli-config` is intended for standalone C examples. The
Coreutils path still uses the whole-program KLEE build flow without the
generated CLI harness.

python3 src/main.py examples/tests/cli/echo.c --cli-config examples/tests/cli/echo.yml