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
    """Run KLEE on a bitcode artifact and return the output directory on success.

    The output directory is created next to the original source file so each run
    keeps its diagnostics, test cases, and replay artifacts close to the input
    that produced them. If KLEE is unavailable or exits with an error code, the
    function prints a short diagnostic and returns ``None``.
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
    """Assemble the KLEE argv list for a single symbolic-execution run.

    POSIX-runtime arguments must appear after the bitcode path, so this helper
    builds the fixed KLEE options first, appends the bitcode input, and then
    expands any caller-provided POSIX argument string.
    """

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
    """Return the environment KLEE should run under for this invocation.

    Guided search uses an environment variable to tell the runtime where to
    find the generated guidance metadata. When guided search is disabled, the
    variable is removed to avoid leaking stale state across runs.
    """

    environment = os.environ.copy()
    if guidance_file:
        environment["ECLIPSE_GUIDANCE_FILE"] = guidance_file
    else:
        environment.pop("ECLIPSE_GUIDANCE_FILE", None)
    return environment


def _resolve_klee_binary() -> str | None:
    """Locate the `klee` executable in PATH or in common local install prefixes."""

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
