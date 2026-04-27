These scripts specifically are meant to help us sanity-check the outputs of the pre-processor for different stages.

## Test Scripts

**Loops:**
```
eclipse examples/tests/preprocessing/loops/while.c --cli-config examples/tests/preprocessing/loops/while.yml
eclipse examples/tests/preprocessing/loops/for.c --cli-config examples/tests/preprocessing/loops/for.yml
eclipse examples/tests/preprocessing/loops/crazy.c --cli-config examples/tests/preprocessing/loops/crazy.yml
```

**GPIO pins:**
```
eclipse examples/tests/preprocessing/gpio/scalar_read_assignment.c --cli-config examples/tests/preprocessing/gpio/scalar_read_assignment.yml
eclipse examples/tests/preprocessing/gpio/request_read_branch.c --cli-config examples/tests/preprocessing/gpio/request_read_branch.yml
eclipse examples/tests/preprocessing/gpio/polling_loop.c --cli-config examples/tests/preprocessing/gpio/polling_loop.yml
eclipse examples/tests/preprocessing/gpio/multiple_reads_expression.c --cli-config examples/tests/preprocessing/gpio/multiple_reads_expression.yml
```

**CLI arguments:**
```
eclipse examples/tests/preprocessing/cli/flag_and_message.c --cli-config examples/tests/preprocessing/cli/flag_and_message.yml
eclipse examples/tests/preprocessing/cli/count_and_label.c --cli-config examples/tests/preprocessing/cli/count_and_label.yml
```
