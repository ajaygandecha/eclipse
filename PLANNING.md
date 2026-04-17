# Planning Page

My personal notes as we work on this...

The ultimate goals is to be able to run:

```
eclipse program.c --cli-spec=program.yml
```

```
eclipse program.c --cli-spec program.yml --no-loop-bounds --no-gpio-constraints --no-cli-constraints --no-guided-se
```

Note: when user uses `--no-cli-constraints`, then this should use the standard KLEE command put in the CLI .yml file as a spec.

Result is something like:

```
[✓] Pre-processing complete (wrote to /file/path)
[✓] Compiled using clang
[✓] Running KLEE

Results:
0 memory violations
```