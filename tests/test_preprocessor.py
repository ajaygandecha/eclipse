from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from preprocessor import (
    _COREUTILS_GL_LIB,
    _COREUTILS_GNULIB_LIB,
    _COREUTILS_LIB,
    _COREUTILS_SRC,
    _FAKE_LIBC_INCLUDE,
    _build_cpp_args,
    preprocess_file,
)


class PreprocessorIncludeTests(unittest.TestCase):
    def test_standalone_input_uses_fake_libc_without_coreutils_roots(self) -> None:
        cpp_args = _build_cpp_args(REPO_ROOT / "examples/vulnerable/repeat-and-copy.c")

        self.assertIn(f"-I{(REPO_ROOT / 'examples/vulnerable').resolve()}", cpp_args)
        self.assertIn(f"-I{_FAKE_LIBC_INCLUDE.resolve()}", cpp_args)
        self.assertNotIn(f"-I{_COREUTILS_LIB.resolve()}", cpp_args)
        self.assertNotIn(f"-I{_COREUTILS_SRC.resolve()}", cpp_args)
        self.assertNotIn(f"-I{_COREUTILS_GNULIB_LIB.resolve()}", cpp_args)
        self.assertNotIn(f"-I{_COREUTILS_GL_LIB.resolve()}", cpp_args)

    def test_coreutils_input_keeps_vendored_include_roots(self) -> None:
        cpp_args = _build_cpp_args(REPO_ROOT / "examples/coreutils/src/echo.c")

        self.assertIn(f"-I{_COREUTILS_LIB.resolve()}", cpp_args)
        self.assertIn(f"-I{_COREUTILS_SRC.resolve()}", cpp_args)
        self.assertIn(f"-I{_COREUTILS_GNULIB_LIB.resolve()}", cpp_args)
        self.assertIn(f"-I{_COREUTILS_GL_LIB.resolve()}", cpp_args)
        self.assertIn(f"-I{_FAKE_LIBC_INCLUDE.resolve()}", cpp_args)


class PreprocessorRegressionTests(unittest.TestCase):
    def test_repeat_and_copy_preprocesses_with_standard_headers(self) -> None:
        generated = preprocess_file(
            str(REPO_ROOT / "examples/vulnerable/repeat-and-copy.c"),
            str(REPO_ROOT / "examples/vulnerable/repeat-and-copy.yml"),
            no_guided_se=True,
        )

        self.assertIn("int __eclipse_original_main(int argc, char *argv[])", generated)
        self.assertIn('__eclipse_argv[0] = "repeat-and-copy";', generated)
        self.assertIn("char sym_word[17];", generated)


if __name__ == "__main__":
    unittest.main()
