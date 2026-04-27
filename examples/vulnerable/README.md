These scripts are intentionally vulnerable programs to test that ECLIPSE can find vulnerabilities.

## Test Scripts

**repeat**
```
eclipse examples/vulnerable/repeat.c --cli-config examples/vulnerable/repeat.yml --exit
eclipse examples/vulnerable/repeat.c --cli-config examples/vulnerable/repeat.yml --exit --no-guided
eclipse examples/vulnerable/repeat.c --cli-config examples/vulnerable/repeat.yml --exit --no-guided --no-cli
eclipse examples/vulnerable/repeat.c --cli-config examples/vulnerable/repeat.yml --exit --no-guided --no-cli --no-gpio
eclipse examples/vulnerable/repeat.c --cli-config examples/vulnerable/repeat.yml --exit --no-guided --no-cli --no-gpio --no-loop
```


```
eclipse examples/vulnerable/repeat.c --cli-config examples/vulnerable/repeat.yml
eclipse examples/vulnerable/alarm-keypad.c --cli-config examples/vulnerable/alarm-keypad.yml
eclipse examples/vulnerable/alarm-keypad-baseline.c --cli-config examples/vulnerable/alarm-keypad.yml --exit --no-guided --no-cli --no-gpio
eclipse examples/vulnerable/buggy.c --cli-config examples/vulnerable/buggy.yml
eclipse examples/vulnerable/irrigation-controller.c --cli-config examples/vulnerable/irrigation-controller.yml
eclipse examples/vulnerable/irrigation-controller-baseline.c --cli-config examples/vulnerable/irrigation-controller.yml

```

```
eclipse examples/coreutils/src/echo.c --cli-config examples/coreutils/src/echo.yml --exit

```
eclipse examples/coreutils/src/tr.c --cli-config examples/coreutils/src/tr.yml --exit
eclipse examples/coreutils/src/pwd.c --cli-config examples/coreutils/src/pwd.yml --exit


eclipse examples/coreutils/src/seq.c --cli-config examples/coreutils/src/seq.yml --exit
