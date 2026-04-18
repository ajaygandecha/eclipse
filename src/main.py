"""Compile C inputs to LLVM bitcode and run them under KLEE.

Most inputs can be compiled as a single translation unit with clang. Coreutils
is the main exception: utilities such as `cut` depend on a large set of
generated headers and support libraries, so KLEE must be given linked,
whole-program bitcode instead of a single `cut.c` object file.
"""

import argparse
import os
import subprocess
import shutil
import sys
import time
from pathlib import Path
from datetime import datetime
from cli_config import load_cli_config
from klee import run_klee
from preprocessor import preprocess_file
from clang import compile_input


def _print_status_ok(message: str) -> None:
    """Print a green checkmark line when stdout is a TTY; plain text otherwise."""

    mark = "\N{CHECK MARK}"
    if sys.stdout.isatty() and not os.environ.get("NO_COLOR"):
        line = f"\033[32m[{mark}]\033[0m {message}"
    else:
        line = f"[{mark}] {message}"
    print(line, flush=True)


def processed_output_path(input_path: Path) -> Path:
    """Return the emitted post-preprocessing C path for an input source file."""

    return input_path.with_name(f"{input_path.stem}-processed.c")


def _format_elapsed_duration(seconds: float) -> str:
    """Render elapsed seconds as a small human-readable duration."""

    total_seconds = max(0, int(round(seconds)))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)

    parts: list[str] = []
    if hours:
        parts.append(f"{hours}hr")
    if hours or minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)


def _is_coreutils_input(input_path: Path) -> bool:
    """Return whether the input lives under the vendored Coreutils tree."""

    coreutils_root = Path(__file__).resolve().parent.parent / "examples" / "coreutils"
    resolved_input = input_path.resolve()
    return coreutils_root.resolve() in (resolved_input, *resolved_input.parents)


def _should_emit_preprocessed_source(
    input_path: Path, no_cli_constraints: bool
) -> bool:
    """Decide whether this invocation should compile a generated C file."""

    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preprocess a C file for ECLIPSE symbolic execution."
    )
    parser.add_argument("input_file", help="Path to the input C program.")
    parser.add_argument(
        "--cli-config",
        help="Path to the canonical YAML config describing structured CLI inputs.",
    )
    parser.add_argument(
        "--no-loop-bounds",
        action="store_true",
        help="Disable loop bounds constraining by the preprocessor.",
    )
    parser.add_argument(
        "--no-gpio-constraints",
        action="store_true",
        help="Disable GPIO constraining by the preprocessor.",
    )
    parser.add_argument(
        "--no-cli-constraints",
        action="store_true",
        help="Disable CLI input constraining by the preprocessor.",
    )
    parser.add_argument(
        "--no-guided-se",
        action="store_true",
        help="Disable guided symbolic execution.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    input_path = Path(args.input_file).resolve()
    compile_input_path = input_path

    if not args.cli_config:
        raise RuntimeError(
            "A CLI config is required for structured CLI input processing."
        )

    # if args.cli_config:
    # if _is_coreutils_input(input_path):
    #     raise RuntimeError(
    #         "Structured CLI harness generation currently supports standalone "
    #         "C inputs only; coreutils still use the whole-program KLEE flow."
    #     )

    cli_config_path = Path(args.cli_config).resolve()

    preprocessed_code = preprocess_file(
        str(input_path),
        str(cli_config_path),
        no_loop_bounds=args.no_loop_bounds if args.no_loop_bounds else False,
        no_gpio_constraints=(
            args.no_gpio_constraints if args.no_gpio_constraints else False
        ),
        no_cli_constraints=(
            args.no_cli_constraints if args.no_cli_constraints else False
        ),
        no_guided_se=args.no_guided_se if args.no_guided_se else False,
    )

    compile_input_path = processed_output_path(input_path)
    compile_input_path.write_text(preprocessed_code)
    _print_status_ok(f"Pre-processing complete (wrote to {compile_input_path})")

    # Compile the input file into a LLVM bitcode file.
    compiled_input_file = compile_input(compile_input_path)
    # print("Compiled.", flush=True)

    _print_status_ok("Compiled using clang")

    # Run the LLVM bitcode file using KLEE.
    print(f"Running {compiled_input_file} using klee...", flush=True)

    klee_posix_command = None
    if args.no_cli_constraints:
        klee_posix_command = load_cli_config(cli_config_path).klee_posix_command

    klee_started_at = time.monotonic()
    output_directory = run_klee(
        compiled_input_file,
        input_path,
        klee_posix_command=klee_posix_command,
    )
    klee_elapsed = time.monotonic() - klee_started_at
    print(f"KLEE run time: {_format_elapsed_duration(klee_elapsed)}", flush=True)
