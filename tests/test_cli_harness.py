from __future__ import annotations

import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

from pycparser import c_parser

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from cli_config import OptionElement, OptionValueElement, PositionalElement, load_cli_config
from main import _processed_output_path
import preprocessor
from preprocessor import preprocess_file


class CLIConfigTests(unittest.TestCase):
    def test_loads_canonical_echo_yaml(self) -> None:
        spec = load_cli_config(REPO_ROOT / "examples/tests/cli/echo.yml")

        self.assertEqual(spec.program, "echo")
        self.assertEqual(spec.entry_point, "main")
        self.assertIsNone(spec.klee_posix_command)
        self.assertEqual(spec.argv0, "echo")
        self.assertEqual(len(spec.elements), 3)
        self.assertIsInstance(spec.elements[0], OptionElement)
        self.assertIsInstance(spec.elements[1], PositionalElement)
        self.assertIsInstance(spec.elements[2], PositionalElement)

    def test_treats_null_elements_as_empty_list(self) -> None:
        spec = load_cli_config(REPO_ROOT / "examples/tests/loops/while.yml")

        self.assertEqual(spec.program, "while")
        self.assertEqual(spec.elements, ())

    def test_preserves_multiple_spellings(self) -> None:
        spec = load_cli_config(REPO_ROOT / "examples/tests/cli/head_like.yml")
        option = spec.elements[0]

        self.assertIsInstance(option, OptionElement)
        self.assertEqual(option.spellings, ("-n", "--lines"))

    def test_loads_guided_sensor_probe_yaml(self) -> None:
        spec = load_cli_config(REPO_ROOT / "examples/tests/guided/sensor_probe.yml")

        self.assertEqual(spec.program, "sensor_probe")
        self.assertEqual(spec.entry_point, "main")
        self.assertEqual(spec.klee_posix_command, "--sym-args 0 4 2")
        self.assertEqual(spec.argv0, "sensor-probe")
        self.assertEqual(len(spec.elements), 4)
        self.assertIsInstance(spec.elements[0], OptionElement)
        self.assertIsInstance(spec.elements[2], OptionValueElement)
        self.assertIsInstance(spec.elements[3], PositionalElement)

    def test_loads_integer_positional_yaml(self) -> None:
        spec = load_cli_config(REPO_ROOT / "examples/vulnerable/repeat.yml")
        count = spec.elements[1]

        self.assertIsInstance(count, PositionalElement)
        self.assertEqual(count.value_kind, "int")
        self.assertEqual(count.min, 1)
        self.assertEqual(count.max, 8)

    def test_rejects_legacy_schema(self) -> None:
        legacy_yaml = """
        program: tool
        options:
          flag:
            type: bool
            flag: --flag
        """

        with self.assertRaisesRegex(ValueError, "Legacy CLI schema"):
            self._load_yaml_string(legacy_yaml)

    def test_rejects_invalid_configs(self) -> None:
        cases = (
            (
                "invalid_entry_point",
                """
                program: tool
                entry_point: helper
                args:
                  argv0: "tool"
                  elements: []
                """,
                "entry_point must be 'main'",
            ),
            (
                "duplicate_id",
                """
                program: tool
                entry_point: main
                args:
                  argv0: "tool"
                  elements:
                    - id: dup
                      type: option
                      spellings: ["-a"]
                    - id: dup
                      type: positional
                      max_length: 4
                """,
                "reuses element id",
            ),
            (
                "missing_parent",
                """
                program: tool
                entry_point: main
                args:
                  argv0: "tool"
                  elements:
                    - id: value
                      type: option_value
                      parent: flag
                      value_kind: int
                      min: 0
                      max: 4
                """,
                "previously declared option parent",
            ),
            (
                "bad_range",
                """
                program: tool
                entry_point: main
                args:
                  argv0: "tool"
                  elements:
                    - id: msg
                      type: positional
                      min_length: 4
                      max_length: 2
                """,
                "min_length <= max_length",
            ),
            (
                "int_positional_wrong_keys",
                """
                program: tool
                entry_point: main
                args:
                  argv0: "tool"
                  elements:
                    - id: count
                      type: positional
                      value_kind: int
                      min_length: 1
                      max_length: 3
                """,
                "must use min/max",
            ),
        )

        for name, yaml_text, expected_message in cases:
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, expected_message):
                    self._load_yaml_string(yaml_text)

    def _load_yaml_string(self, yaml_text: str):
        with tempfile.TemporaryDirectory() as temp_dir:
            yaml_path = Path(temp_dir) / "config.yml"
            yaml_path.write_text(textwrap.dedent(yaml_text).strip() + "\n")
            return load_cli_config(yaml_path)


class HarnessGenerationTests(unittest.TestCase):
    def test_processed_output_path_uses_source_basename(self) -> None:
        output_path = _processed_output_path(
            REPO_ROOT / "examples/tests/cli/head_like.c"
        )

        self.assertEqual(
            output_path,
            REPO_ROOT / "examples/tests/cli/head_like-processed.c",
        )

    def test_rewrites_main_and_uses_canonical_argv0(self) -> None:
        generated = preprocess_file(
            str(REPO_ROOT / "examples/tests/cli/echo.c"),
            str(REPO_ROOT / "examples/tests/cli/echo.yml"),
        )

        self.assertIn("int __eclipse_original_main(int argc, char **argv)", generated)
        self.assertIn('__eclipse_argv[0] = "echo";', generated)
        self.assertIn(
            "return __eclipse_original_main(__eclipse_argc, __eclipse_argv);",
            generated,
        )

    def test_optional_elements_are_presence_gated(self) -> None:
        generated = preprocess_file(
            str(REPO_ROOT / "examples/tests/cli/echo.c"),
            str(REPO_ROOT / "examples/tests/cli/echo.yml"),
        )

        self.assertIn("if (__eclipse_use_no_newline)", generated)
        self.assertIn("if (__eclipse_use_msg1)", generated)
        self.assertIn("if (__eclipse_use_msg2)", generated)

    def test_option_values_follow_parent_selection(self) -> None:
        generated = preprocess_file(
            str(REPO_ROOT / "examples/tests/cli/head_like.c"),
            str(REPO_ROOT / "examples/tests/cli/head_like.yml"),
        )

        option_index = generated.index('= "-n";')
        value_index = generated.index("__eclipse_int_to_string(sym_count_value")
        file_index = generated.index("= sym_file;")

        self.assertIn("if (__eclipse_use_count_flag)", generated)
        self.assertIn("__eclipse_int_to_string(sym_count_value", generated)
        self.assertLess(option_index, value_index)
        self.assertLess(value_index, file_index)

    def test_multiple_spellings_use_selector_not_symbolic_bytes(self) -> None:
        generated = preprocess_file(
            str(REPO_ROOT / "examples/tests/cli/head_like.c"),
            str(REPO_ROOT / "examples/tests/cli/head_like.yml"),
        )

        self.assertIn("int __eclipse_count_flag_spelling;", generated)
        self.assertIn("if (__eclipse_count_flag_spelling == 0)", generated)
        self.assertIn("if (__eclipse_count_flag_spelling == 1)", generated)
        self.assertNotIn("char sym_count_flag", generated)

    def test_generated_output_parses_as_c(self) -> None:
        generated = preprocess_file(
            str(REPO_ROOT / "examples/tests/cli/head_like.c"),
            str(REPO_ROOT / "examples/tests/cli/head_like.yml"),
        )

        parsed = c_parser.CParser().parse(generated)
        self.assertIsNotNone(parsed)

    def test_guided_example_generates_parseable_harness(self) -> None:
        generated = preprocess_file(
            str(REPO_ROOT / "examples/tests/guided/sensor_probe.c"),
            str(REPO_ROOT / "examples/tests/guided/sensor_probe.yml"),
        )

        self.assertIn("int __eclipse_sample_flag_spelling;", generated)
        self.assertIn("char sym_payload[3];", generated)
        self.assertIn('__eclipse_argv[0] = "sensor-probe";', generated)

        parsed = c_parser.CParser().parse(generated)
        self.assertIsNotNone(parsed)

    def test_integer_positional_uses_symbolic_int_and_stringified_argv(self) -> None:
        generated = preprocess_file(
            str(REPO_ROOT / "examples/vulnerable/repeat.c"),
            str(REPO_ROOT / "examples/vulnerable/repeat.yml"),
            no_guided_se=True,
        )

        self.assertIn("int sym_count;", generated)
        self.assertIn('klee_make_symbolic(&sym_count, sizeof(sym_count), "count");', generated)
        self.assertIn("klee_assume((sym_count >= 1) && (sym_count <= 8));", generated)
        self.assertIn("char __eclipse_count_value[2];", generated)
        self.assertIn("__eclipse_int_to_string(sym_count, __eclipse_count_value, sizeof(__eclipse_count_value))", generated)
        self.assertNotIn("char sym_count[", generated)

    def test_gpio_preprocessing_preserves_function_prototype_semicolons(self) -> None:
        generated = preprocess_file(
            str(REPO_ROOT / "examples/tests/preprocessing/gpio/scalar_read_assignment.c"),
            str(REPO_ROOT / "examples/tests/preprocessing/gpio/scalar_read_assignment.yml"),
        )

        self.assertIn(
            "void klee_make_symbolic(void *addr, int nbytes, char *name);",
            generated,
        )
        self.assertIn("void klee_assume(int expr);", generated)
        self.assertIn("int gpiod_line_get_value(struct gpiod_line *line);", generated)
        self.assertIn("int consume(int value);", generated)

        parsed = c_parser.CParser().parse(generated)
        self.assertIsNotNone(parsed)

    def test_gpio_preprocessing_skips_duplicate_klee_preamble_declarations(self) -> None:
        generated = preprocess_file(
            str(REPO_ROOT / "examples/tests/preprocessing/gpio/scalar_read_assignment.c"),
            str(REPO_ROOT / "examples/tests/preprocessing/gpio/scalar_read_assignment.yml"),
        )

        self.assertNotIn(
            "extern void klee_make_symbolic(void *addr, unsigned long nbytes, const char *name);",
            generated,
        )
        self.assertNotIn("extern void klee_assume(int condition);", generated)

    def test_option_value_element_is_loaded(self) -> None:
        spec = load_cli_config(REPO_ROOT / "examples/tests/cli/head_like.yml")

        self.assertIsInstance(spec.elements[1], OptionValueElement)

    def test_coreutils_config_loads_optional_klee_posix_command(self) -> None:
        spec = load_cli_config(REPO_ROOT / "examples/coreutils/src/echo.yml")

        self.assertEqual(spec.klee_posix_command, "--sym-args 0 4 2")

    def test_rejects_sys_args_typo_in_klee_posix_command(self) -> None:
        invalid_yaml = """
        program: echo
        entry_point: main
        klee_posix_command: "--sys-args 0 2 4"
        args:
          argv0: "echo"
          elements: []
        """

        with self.assertRaisesRegex(ValueError, "--sym-args"):
            self._load_yaml_string(invalid_yaml)

    def test_no_arg_main_is_wrapped_without_argv_harness(self) -> None:
        generated = preprocess_file(
            str(REPO_ROOT / "examples/tests/loops/while.c"),
            str(REPO_ROOT / "examples/tests/loops/while.yml"),
        )

        self.assertIn("int __eclipse_original_main()", generated)
        self.assertIn("return __eclipse_original_main();", generated)
        self.assertNotIn("__eclipse_argv", generated)

    def test_cli_constraints_run_after_loop_and_gpio_before_render(self) -> None:
        ast = object()
        events: list[str] = []

        def _record(name: str):
            events.append(name)
            return ast

        with (
            patch.object(preprocessor, "parse_file", return_value=ast),
            patch.object(preprocessor, "_build_cpp_args", return_value=[]),
            patch.object(preprocessor, "add_loop_bounds", side_effect=lambda value: _record("loops")),
            patch.object(preprocessor, "constrain_gpio_reads", side_effect=lambda value: _record("gpio")),
            patch.object(
                preprocessor,
                "add_argument_constraints",
                side_effect=lambda file_path, value: (
                    events.append("cli"),
                    ast,
                )[1],
            ),
            patch.object(
                preprocessor,
                "render_processed_source",
                side_effect=lambda value, config_path: (
                    events.append("render"),
                    "/* processed */\nint __eclipse_original_main(void) { return 0; }\n"
                    "int main(void)\n{\n  return __eclipse_original_main();\n}\n",
                )[1],
            ),
        ):
            generated = preprocess_file(
                str(REPO_ROOT / "examples/tests/loops/while.c"),
                str(REPO_ROOT / "examples/tests/loops/while.yml"),
                no_guided_se=True,
            )

        self.assertLess(events.index("loops"), events.index("gpio"))
        self.assertLess(events.index("gpio"), events.index("cli"))
        self.assertLess(events.index("cli"), events.index("render"))
        self.assertIn("/* processed */", generated)
        self.assertIn("__eclipse_original_main", generated)
        self.assertIn("int main(void)", generated)

    def _load_yaml_string(self, yaml_text: str):
        with tempfile.TemporaryDirectory() as temp_dir:
            yaml_path = Path(temp_dir) / "config.yml"
            yaml_path.write_text(textwrap.dedent(yaml_text).strip() + "\n")
            return load_cli_config(yaml_path)


if __name__ == "__main__":
    unittest.main()
