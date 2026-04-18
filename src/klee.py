import subprocess
import shutil
import shlex
import os
from pathlib import Path
from datetime import datetime


def run_klee(
    bitcode_file: str,
    original_input_file: str,
    klee_posix_command: str | None = None,
    guided_search: bool = False,
    guidance_file: str | None = None,
) -> str | None:
    """
    Symbolically executes the LLVM bitcode file using KLEE.

    Args:
        bitcode_file: The LLVM bitcode file to execute.
        original_input_file: The original input file that was compiled to the bitcode file.

    Returns:
        The output directory of the KLEE run.
    """

    klee_binary = _resolve_klee_binary()
    if not klee_binary:
        print("KLEE binary not found; skipping symbolic execution.", flush=True)
        return None

    # Create a base output directory for the KLEE output.
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    output_directory = (
        Path(original_input_file).resolve().parent / f"klee-output-{timestamp}"
    )

    klee_command = _build_klee_command(
        klee_binary,
        bitcode_file,
        output_directory,
        klee_posix_command=klee_posix_command,
        guided_search=guided_search,
    )

    klee_environment = _build_klee_environment(guidance_file)
    result = subprocess.run(klee_command, check=False, env=klee_environment)

    if result.returncode != 0:
        print(
            f"KLEE exited with code {result.returncode}; see {output_directory} "
            "for diagnostics.",
            flush=True,
        )
        return None

    return str(output_directory)


def _build_klee_command(
    klee_binary: str,
    bitcode_file: str,
    output_directory: Path,
    klee_posix_command: str | None = None,
    guided_search: bool = False,
) -> list[str]:
    """Build the KLEE command, appending POSIX-runtime args after the bitcode."""

    klee_command = [
        klee_binary,
        "--only-output-states-covering-new",
        f"-output-dir={str(output_directory)}",
        "--libc=uclibc",
        "--posix-runtime",
        "-exit-on-error-type=Ptr",
        "-exit-on-error-type=Free",
        "-exit-on-error-type=ReadOnly",
    ]

    if guided_search:
        klee_command.extend(
            [
                "--search=guided",
                "--search=nurs:covnew",
            ]
        )

    klee_command.append(bitcode_file)

    if klee_posix_command:
        klee_command.extend(shlex.split(klee_posix_command))

    return klee_command


def _build_klee_environment(guidance_file: str | None = None) -> dict[str, str]:
    environment = os.environ.copy()
    if guidance_file:
        environment["ECLIPSE_GUIDANCE_FILE"] = guidance_file
    else:
        environment.pop("ECLIPSE_GUIDANCE_FILE", None)
    return environment


def _resolve_klee_binary() -> str | None:
    klee_binary = shutil.which("klee")
    if klee_binary:
        return klee_binary

    common_locations = (
        Path("/opt/homebrew/bin/klee"),
        Path("/usr/local/bin/klee"),
        Path("/opt/local/bin/klee"),
    )
    for candidate in common_locations:
        if candidate.exists() and candidate.is_file():
            return str(candidate)

    return None
