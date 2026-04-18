from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from klee import _build_klee_command, _build_klee_environment


class KLEECommandTests(unittest.TestCase):
    def test_appends_posix_runtime_arguments_after_bitcode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "klee-output"
            command = _build_klee_command(
                "/usr/bin/klee",
                "/tmp/echo.bc",
                output_dir,
                klee_posix_command="--sym-arg 3",
            )

        self.assertEqual(
            command,
            [
                "/usr/bin/klee",
                "--only-output-states-covering-new",
                f"-output-dir={output_dir}",
                "--libc=uclibc",
                "--posix-runtime",
                "-exit-on-error-type=Ptr",
                "-exit-on-error-type=Free",
                "-exit-on-error-type=ReadOnly",
                "/tmp/echo.bc",
                "--sym-arg",
                "3",
            ],
        )

    def test_sets_guidance_path_in_environment(self) -> None:
        environment = _build_klee_environment("/tmp/echo-guidance.json")

        self.assertEqual(
            environment["ECLIPSE_GUIDANCE_FILE"],
            "/tmp/echo-guidance.json",
        )

    def test_includes_guided_search_arguments_before_bitcode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "klee-output"
            command = _build_klee_command(
                "/usr/bin/klee",
                "/tmp/echo.bc",
                output_dir,
                guided_search=True,
            )

        self.assertEqual(
            command,
            [
                "/usr/bin/klee",
                "--only-output-states-covering-new",
                f"-output-dir={output_dir}",
                "--libc=uclibc",
                "--posix-runtime",
                "-exit-on-error-type=Ptr",
                "-exit-on-error-type=Free",
                "-exit-on-error-type=ReadOnly",
                "--search=guided",
                "--search=nurs:covnew",
                "/tmp/echo.bc",
            ],
        )


if __name__ == "__main__":
    unittest.main()
