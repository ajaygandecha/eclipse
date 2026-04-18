import subprocess
import shutil
import tempfile
from pathlib import Path
import sys
import os
from contextlib import contextmanager

from preprocessor import _COREUTILS_ORIGINAL_SOURCE_PLACEHOLDER

_REPO_ROOT = Path(__file__).resolve().parent.parent
_COREUTILS_ROOT = _REPO_ROOT / "examples" / "coreutils"
_COREUTILS_CONFIG_STAMP = _COREUTILS_ROOT / ".eclipse-devcontainer-configured"
_FAKE_LIBC_INCLUDE = _REPO_ROOT / "src" / "utils" / "fake_libc_include"

# These flags mirror the KLEE Coreutils tutorial: keep debug info, avoid
# optimization passes that erase useful structure, and disable a few host
# optimizations that get in the way of symbolic execution.
_COREUTILS_KLEE_CFLAGS = (
    "-g -O1 -Xclang -disable-llvm-passes "
    "-D__NO_STRING_INLINES -D_FORTIFY_SOURCE=0 -U__OPTIMIZE__"
)


def compile_input(input_path: Path) -> str:
    """Compile the input file into LLVM bitcode for KLEE.

    Ordinary inputs use a direct clang invocation. Coreutils inputs use a
    separate whole-program flow because KLEE needs the linked utility plus its
    generated gnulib/Coreutils support code.
    """

    # Create a path for the compiled output file.
    compiled_output_path = input_path.parent / "compiled-input.bc"

    if _is_coreutils_input(input_path):
        print(
            f"Compiling {input_path} using the prepared Coreutils WLLVM build...",
            flush=True,
        )
        print("Compiling coreutils input...", flush=True)
        return _build_coreutils_bitcode(input_path, compiled_output_path)
    elif sys.platform.startswith("linux"):
        print(f"Compiling {input_path} using clang...", flush=True)
        subprocess.run(
            [
                "clang",
                "-Wno-tautological-constant-out-of-range-compare",
                *_build_clang_fallback_include_flags(),
                "-emit-llvm",
                "-c",
                "-g",
                "-O0",
                "-Xclang",
                "-disable-O0-optnone",
                str(input_path),
                "-o",
                str(compiled_output_path),
            ],
            check=True,
        )
    else:
        print(f"Compiling {input_path} using clang...", flush=True)
        subprocess.run(
            [
                "clang",
                "-std=gnu2x",
                "-Wno-tautological-constant-out-of-range-compare",
                *_build_clang_fallback_include_flags(),
                "-emit-llvm",
                "-c",
                "-g",
                "-O0",
                "-Xclang",
                "-disable-O0-optnone",
                str(input_path),
                "-o",
                str(compiled_output_path),
            ],
            check=True,
        )

    # Return the path to the compiled output file.
    return str(compiled_output_path)


def _prepare_coreutils_source_tree(input_path: Path) -> tuple[Path, dict[str, str]]:
    """Validate that the devcontainer-prepared Coreutils tree is ready to use."""
    build_root = _COREUTILS_ROOT
    env = _coreutils_klee_env()

    if not _COREUTILS_CONFIG_STAMP.exists() or not (build_root / "Makefile").exists():
        raise RuntimeError(
            "The devcontainer has not prepared Coreutils for whole-program KLEE "
            "builds yet. Rebuild/reopen the devcontainer or run "
            "bash .devcontainer/post-create.sh inside it."
        )

    return build_root, env


def _build_coreutils_bitcode(input_path: Path, compiled_output_path: Path) -> str:
    """Build linked whole-program bitcode for a Coreutils utility.

    This follows the KLEE Coreutils workflow more closely than the normal clang
    path: generate Coreutils' built headers, build the linked utility with
    `wllvm`, then extract a `.bc` file from the final executable.
    """
    build_root, env = _prepare_coreutils_source_tree(input_path)
    build_source_path = _coreutils_build_source_path(input_path)
    program_target = _coreutils_program_target(build_source_path)
    extract_bc_binary = _resolve_tool_binary("extract-bc")
    if not extract_bc_binary:
        raise RuntimeError(
            "extract-bc is required for Coreutils whole-program KLEE builds. "
            "Rebuild the devcontainer so the declared dependencies are installed."
        )

    print("Building linked Coreutils bitcode with wllvm...", flush=True)
    with _coreutils_source_override(build_source_path, input_path):
        built_sources = _coreutils_built_sources(build_root, env)
        if built_sources:
            # Coreutils' generated compatibility headers are prerequisites for
            # source files like `src/cut.c`, but make does not always materialize
            # them early enough when we request only `src/cut`.
            subprocess.run(
                ["make", "-j1", *built_sources],
                cwd=build_root,
                env=env,
                check=True,
            )
        make_command = ["make", "-j1"]
        if input_path != build_source_path:
            make_command.append("LDFLAGS=-Wl,--unresolved-symbols=ignore-all")
        make_command.append(program_target)
        subprocess.run(
            make_command,
            cwd=build_root,
            env=env,
            check=True,
        )

        built_program_path = build_root / program_target
        subprocess.run(
            [extract_bc_binary, str(built_program_path)],
            cwd=build_root,
            env=env,
            check=True,
        )

        built_bitcode_path = built_program_path.with_suffix(".bc")
        shutil.copy2(built_bitcode_path, compiled_output_path)
    return str(compiled_output_path)


def _is_coreutils_input(input_path: Path) -> bool:
    resolved_input = input_path.resolve()
    resolved_coreutils_root = _COREUTILS_ROOT.resolve()
    return resolved_coreutils_root in (resolved_input, *resolved_input.parents)


def _build_clang_fallback_include_flags() -> list[str]:
    if _FAKE_LIBC_INCLUDE.exists():
        # Keep real system headers first, but use our fake libc headers as a
        # fallback for newer headers that may be missing on the host toolchain.
        return ["-idirafter", str(_FAKE_LIBC_INCLUDE.resolve())]
    return []


def _coreutils_klee_env() -> dict[str, str]:
    """Return the toolchain environment required for whole-program Coreutils BC.

    `wllvm` records the LLVM bitcode for each compiled object, and `extract-bc`
    later recovers linked whole-program bitcode from the final executable.
    """
    wllvm_binary = _resolve_tool_binary("wllvm")
    if not wllvm_binary:
        raise RuntimeError(
            "wllvm is required for Coreutils whole-program KLEE builds. "
            "Rebuild the devcontainer so the declared dependencies are installed."
        )

    extract_bc_binary = _resolve_tool_binary("extract-bc")
    if not extract_bc_binary:
        raise RuntimeError(
            "extract-bc is required for Coreutils whole-program KLEE builds. "
            "Rebuild the devcontainer so the declared dependencies are installed."
        )

    env = os.environ.copy()
    env["LLVM_COMPILER"] = "clang"
    env["CC"] = wllvm_binary
    env["CFLAGS"] = _COREUTILS_KLEE_CFLAGS
    return env


def _coreutils_built_sources(build_root: Path, env: dict[str, str]) -> list[str]:
    """Ask make for the fully expanded Coreutils BUILT_SOURCES list.

    Coreutils generates many wrapper headers such as `configmake.h`,
    `lib/stdio.h`, and `lib/wctype.h`. Building them up front avoids the
    missing-generated-header errors we saw when jumping straight to `make src/cut`.
    """
    built_sources_result = subprocess.run(
        [
            "make",
            "-s",
            "--no-print-directory",
            "--eval",
            "print-built-sources: ; @printf '%s\\n' \"$(BUILT_SOURCES)\"",
            "print-built-sources",
        ],
        cwd=build_root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    if built_sources_result.returncode != 0 and not built_sources_result.stdout.strip():
        raise RuntimeError(
            "Unable to read Coreutils BUILT_SOURCES from make: "
            f"{built_sources_result.stderr.strip()}"
        )

    built_sources = built_sources_result.stdout.split()

    if not built_sources:
        raise RuntimeError("Unable to find Coreutils BUILT_SOURCES in make output.")

    return built_sources




def _resolve_tool_binary(tool_name: str) -> str | None:
    tool_binary = shutil.which(tool_name)
    if tool_binary:
        return tool_binary
    return None


def _coreutils_input_relative_path(input_path: Path) -> Path:
    return input_path.resolve().relative_to(_COREUTILS_ROOT.resolve())


def _coreutils_build_source_path(input_path: Path) -> Path:
    """Map generated Coreutils harness sources back to their original utility."""

    if input_path.suffix != ".c" or not input_path.stem.endswith("-processed"):
        return input_path

    original_path = input_path.with_name(
        f"{input_path.stem.removesuffix('-processed')}{input_path.suffix}"
    )
    if original_path.exists():
        return original_path

    return input_path


def _coreutils_program_target(input_path: Path) -> str:
    """Map `examples/coreutils/src/foo.c` to the make target `src/foo`."""
    relative_input_path = _coreutils_input_relative_path(input_path)
    if relative_input_path.parent != Path("src"):
        raise RuntimeError(
            "Whole-program Coreutils KLEE builds currently support top-level "
            "src/*.c inputs."
        )

    return f"src/{relative_input_path.stem}"


@contextmanager
def _coreutils_source_override(original_source_path: Path, replacement_source_path: Path):
    """Temporarily build a Coreutils utility from an instrumented replacement source."""

    if original_source_path.resolve() == replacement_source_path.resolve():
        yield
        return

    original_bytes = original_source_path.read_bytes()
    with tempfile.NamedTemporaryFile(
        prefix=f"{original_source_path.stem}-eclipse-original-",
        suffix=original_source_path.suffix,
        delete=False,
    ) as temp_source:
        temp_source.write(original_bytes)
        temp_source_path = Path(temp_source.name)

    replacement_text = replacement_source_path.read_text()
    if _COREUTILS_ORIGINAL_SOURCE_PLACEHOLDER in replacement_text:
        replacement_text = replacement_text.replace(
            _COREUTILS_ORIGINAL_SOURCE_PLACEHOLDER,
            str(temp_source_path),
        )
    original_source_path.write_text(replacement_text)
    try:
        yield
    finally:
        original_source_path.write_bytes(original_bytes)
