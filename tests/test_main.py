from pathlib import Path
import sys
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from main import _should_emit_preprocessed_source


class MainFlowTests(unittest.TestCase):
    def test_coreutils_no_cli_constraints_still_emits_preprocessed_source(self) -> None:
        should_preprocess = _should_emit_preprocessed_source(
            REPO_ROOT / "examples/coreutils/src/echo.c",
            no_cli_constraints=True,
        )

        self.assertTrue(should_preprocess)

    def test_coreutils_with_cli_constraints_emits_wrapper_source(self) -> None:
        should_preprocess = _should_emit_preprocessed_source(
            REPO_ROOT / "examples/coreutils/src/echo.c",
            no_cli_constraints=False,
        )

        self.assertTrue(should_preprocess)


if __name__ == "__main__":
    unittest.main()
