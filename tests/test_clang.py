from pathlib import Path
import sys
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from clang import _coreutils_build_source_path, _coreutils_program_target


class CoreutilsBuildInputTests(unittest.TestCase):
    def test_coreutils_program_target_uses_original_source_name(self) -> None:
        target = _coreutils_program_target(
            REPO_ROOT / "examples/coreutils/src/echo.c"
        )

        self.assertEqual(target, "src/echo")

    def test_processed_coreutils_input_maps_back_to_original_source(self) -> None:
        build_source = _coreutils_build_source_path(
            REPO_ROOT / "examples/coreutils/src/echo-processed.c"
        )

        self.assertEqual(
            build_source,
            REPO_ROOT / "examples/coreutils/src/echo.c",
        )


if __name__ == "__main__":
    unittest.main()
