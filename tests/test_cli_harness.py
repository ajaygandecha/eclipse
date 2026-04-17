from __future__ import annotations

import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from pycparser import c_parser

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from cli_config import OptionElement, OptionValueElement, PositionalElement, load_cli_config
from main import processed_output_path
from preprocessor import preprocess_file


class CLIConfigTests(unittest.TestCase):
    def test_loads_canonical_echo_yaml(self) -> None:
        spec = load_cli_config(REPO_ROOT / "examples/tests/cli/echo.yml")

        self.assertEqual(spec.program, "echo")
        self.assertEqual(spec.entry_point, "main")
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
        output_path = processed_output_path(
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

    def test_option_value_element_is_loaded(self) -> None:
        spec = load_cli_config(REPO_ROOT / "examples/tests/cli/head_like.yml")

        self.assertIsInstance(spec.elements[1], OptionValueElement)

    def test_no_arg_main_is_wrapped_without_argv_harness(self) -> None:
        generated = preprocess_file(
            str(REPO_ROOT / "examples/tests/loops/while.c"),
            str(REPO_ROOT / "examples/tests/loops/while.yml"),
        )

        self.assertIn("int __eclipse_original_main()", generated)
        self.assertIn("return __eclipse_original_main();", generated)
        self.assertNotIn("__eclipse_argv", generated)


if __name__ == "__main__":
    unittest.main()
