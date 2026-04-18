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
    exit_on_first_error: bool = False,
) -> str | None:
    """Run KLEE on a compiled bitcode artifact and return the output directory.

    This function is the last step of the ECLIPSE pipeline. By the time we get
    here, the input C program has already been:

    - preprocessed and rewritten into `*-processed.c`
    - compiled into LLVM bitcode

    At this point, our job is simply to:

    1. find the `klee` executable
    2. choose an output directory for this run
    3. build the KLEE command line
    4. set any required environment variables
    5. execute KLEE and report whether the run succeeded

    The output directory is created next to the original source file so that
    the generated test cases, diagnostics, and replay artifacts stay close to
    the program that produced them. If KLEE is not installed or exits with a
    non-zero status code, this function prints a short diagnostic and returns
    ``None`` instead of raising.
    """

    # Resolve the KLEE binary from PATH first, then fall back to a few common
    # local installation prefixes used on developer machines.
    klee_binary = _resolve_klee_binary()
    if not klee_binary:
        print("KLEE binary not found; skipping symbolic execution.", flush=True)
        return None

    # Each run gets its own timestamped output directory. KLEE writes many
    # files during execution, so keeping runs separated avoids collisions and
    # makes it easy to inspect the artifacts from one invocation later.
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    output_directory = (
        Path(original_input_file).resolve().parent / f"klee-output-{timestamp}"
    )

    # Build the full argv list, including optional guided-search settings and
    # any caller-provided KLEE POSIX-runtime arguments.
    klee_command = _build_klee_command(
        klee_binary,
        bitcode_file,
        output_directory,
        klee_posix_command=klee_posix_command,
        guided_search=guided_search,
        exit_on_first_error=exit_on_first_error,
    )

    # Build the environment for this particular run. Guided search uses an
    # environment variable to point KLEE at the generated JSON guidance file.
    klee_environment = _build_klee_environment(guidance_file)
    result = subprocess.run(klee_command, check=False, env=klee_environment)

    # A non-zero exit means KLEE itself failed, not just that it found an
    # interesting program path. In that case we point the user to the output
    # directory, since that is where KLEE leaves its logs and diagnostics.
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
    exit_on_first_error: bool = False,
) -> list[str]:
    """Assemble the exact argv list used to invoke KLEE.

    KLEE's command line is a mix of:

    - fixed execution options that we want on every run
    - optional search-strategy flags
    - the input bitcode file itself
    - optional POSIX-runtime arguments such as `--sym-args ...`

    The ordering matters. In particular, POSIX-runtime arguments belong after
    the bitcode path, because they describe the simulated command-line
    environment for the program *inside* KLEE rather than options for KLEE
    itself.
    """

    klee_command = [
        klee_binary,
        # Only keep test cases for states that increase line coverage. This
        # avoids filling the output directory with many redundant paths.
        "--only-output-states-covering-new",
        # Tell KLEE where to write all of its output artifacts for this run.
        f"-output-dir={str(output_directory)}",
        # Use KLEE's uclibc model so common libc behavior is available inside
        # symbolic execution.
        "--libc=uclibc",
        # Enable KLEE's POSIX runtime model. This is what allows symbolic argv,
        # files, and related command-line style execution environments.
        "--posix-runtime",
    ]

    if exit_on_first_error:
        # In "exit on first error" mode, stop as soon as KLEE reaches one of
        # these memory-safety error classes instead of continuing through the
        # rest of the path space.
        klee_command.extend(
            [
                "-exit-on-error-type=Ptr",
                "-exit-on-error-type=Free",
                "-exit-on-error-type=ReadOnly",
            ]
        )

    if guided_search:
        # If guided search is enabled, we should override the default search strategy
        # and use the guided search strategy.
        klee_command.extend(
            [
                "--search=guided",
                "--search=nurs:covnew",
            ]
        )

    klee_command.append(bitcode_file)

    if klee_posix_command:
        # The config stores these as a shell-style string (for example
        # `"--sym-args 0 4 8"`). `shlex.split` turns that into the argv form
        # that `subprocess.run(...)` expects.
        klee_command.extend(shlex.split(klee_posix_command))

    return klee_command


def _build_klee_environment(guidance_file: str | None = None) -> dict[str, str]:
    """Build the environment dictionary for a single KLEE invocation.

    Guided search uses an environment variable to tell the runtime where to
    find the generated guidance metadata. When guided search is disabled, the
    variable is removed so one run cannot accidentally inherit stale guidance
    from an earlier invocation.
    """

    environment = os.environ.copy()
    if guidance_file:
        environment["ECLIPSE_GUIDANCE_FILE"] = guidance_file
    else:
        environment.pop("ECLIPSE_GUIDANCE_FILE", None)
    return environment


def _resolve_klee_binary() -> str | None:
    """Locate the `klee` executable in PATH or in common install locations.

    We first trust the user's PATH, since that is the most explicit signal of
    which KLEE they want to use. If that fails, we check a few typical local
    install prefixes used on macOS and similar developer environments.
    """

    klee_binary = shutil.which("klee")
    if klee_binary:
        return klee_binary

    # These are fallback guesses for local installs outside PATH. They are not
    # exhaustive, but they cover the common places developers often end up with
    # a manually installed KLEE binary.
    common_locations = (
        Path("/opt/homebrew/bin/klee"),
        Path("/usr/local/bin/klee"),
        Path("/opt/local/bin/klee"),
    )
    for candidate in common_locations:
        if candidate.exists() and candidate.is_file():
            return str(candidate)

    return None
