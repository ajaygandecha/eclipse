"""Main entrypoint that runs the entire ECLIPSE workflow."""

import argparse
import time
from pathlib import Path
from cli_config import load_cli_config
from klee import run_klee
from preprocessor import preprocess_file
from clang import compile_input
from helpers import format_time_duration
from helpers import print_checkmarked_message


def _processed_output_path(input_path: Path) -> Path:
    """Create the path for the processed C input file from the input path."""

    return input_path.with_name(f"{input_path.stem}-processed.c")


def _guidance_output_path(input_path: Path) -> Path:
    """Create the path for the guidance metadata file from the input path."""

    return input_path.with_name(f"{input_path.stem}-guidance.json")


def parse_args() -> argparse.Namespace:
    """Parse the command line arguments for the ECLIPSE main program."""
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
    parser.add_argument(
        "--exit-on-first-error",
        action="store_true",
        help="Stop KLEE as soon as it hits the first configured memory error.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    input_path = Path(args.input_file).resolve()
    compile_input_path = input_path
    emitted_guidance_path = None

    if not args.cli_config:
        raise RuntimeError(
            "A CLI config file is required for structured CLI input processing."
        )

    cli_config_path = Path(args.cli_config).resolve()

    # Preprocess the input file.
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
        guidance_output_path=(
            str(_guidance_output_path(input_path)) if not args.no_guided_se else None
        ),
    )

    # Write the preprocessed code to the output file.
    compile_input_path = _processed_output_path(input_path)
    compile_input_path.write_text(preprocessed_code)

    print_checkmarked_message(
        f"Pre-processing complete (wrote to {compile_input_path})"
    )

    # If guided symbolic execution is enabled, emit the guidance metadata file.
    if not args.no_guided_se:
        emitted_guidance_path = _guidance_output_path(input_path)
        print_checkmarked_message(
            f"Guidance metadata emitted to {emitted_guidance_path}"
        )

    # Compile the input file into a LLVM bitcode file.
    compiled_input_file = compile_input(compile_input_path)

    print_checkmarked_message("Compiled using clang")

    # Run the LLVM bitcode file using KLEE.
    print(f"Running {compiled_input_file} using klee...", flush=True)

    # Determine the time that symbolic execution started.
    klee_started_at = time.monotonic()

    # Run KLEE with the compiled input file.
    output_directory = run_klee(
        compiled_input_file,
        input_path,
        klee_posix_command=(
            load_cli_config(cli_config_path).klee_posix_command
            if args.no_cli_constraints
            else None
        ),
        guided_search=emitted_guidance_path is not None,
        guidance_file=str(emitted_guidance_path) if emitted_guidance_path else None,
        exit_on_first_error=args.exit_on_first_error,
    )

    # Determine the time that symbolic execution finished.
    klee_elapsed = time.monotonic() - klee_started_at

    # Print the time that symbolic execution took.
    print(f"KLEE run time: {format_time_duration(klee_elapsed)}", flush=True)
