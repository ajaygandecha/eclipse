import subprocess
import shutil
from pathlib import Path
import os
from contextlib import contextmanager

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

# Direct single-file builds use a much simpler clang invocation than the
# Coreutils whole-program flow. These flags intentionally prioritize bitcode
# that is easy for KLEE to reason about over native-code performance.
_DIRECT_CLANG_FLAGS = (
    # Parse the file as modern GNU C so repo examples and system headers can use
    # newer language features and GNU extensions consistently.
    "-std=gnu2x",
    # Some generated comparisons in vendored code trigger a noisy diagnostic
    # that is not relevant to our symbolic-execution workflow.
    "-Wno-tautological-constant-out-of-range-compare",
    # Emit LLVM bitcode instead of a native object file.
    "-emit-llvm",
    # Compile only; do not link. For standalone inputs we hand KLEE a single
    # translation unit bitcode file directly.
    "-c",
    # Keep debug info so source line references survive into KLEE diagnostics.
    "-g",
    # Stay at O0 so the input structure remains close to the original source.
    "-O0",
    # Clang normally adds the `optnone` attribute at O0, which can make later
    # analysis/transforms less useful. Disable that frontend behavior explicitly.
    "-Xclang",
    "-disable-O0-optnone",
)


def compile_input(input_path: Path) -> str:
    """
    Compile the input file into LLVM bitcode for KLEE.

    Note that there are two different methods of compilation based on the type
    of input file.

    For standard single-file C programs, we use a direct Clang compilation that
    emits LLVM bitcode for the program.

    This approach does not work on Coreutils programs because they depend on a
    large set of external header files and support libraries that are not present
    in the standard Clang installation. Therefore, we use a whole program build
    that uses `wllvm` to compile the program using the Coreutils build tree.
    """

    # Create a path for the compiled output file.
    compiled_output_path = input_path.parent / "compiled-input.bc"

    # If the program is a Coreutils program, we use the whole program build.
    if _is_coreutils_input(input_path):
        print(
            f"Compiling {input_path} using the prepared Coreutils WLLVM build...",
            flush=True,
        )
        return _compile_coreutils_program(input_path, compiled_output_path)
    # If the program is not a Coreutils program, we use direct Clang compilation.
    else:
        print(f"Compiling {input_path} using clang...", flush=True)
        # `-idirafter <dir>` appends `<dir>` to Clang's header search path, but
        # only after the normal system include directories. The idea here is that
        # the host computer running ECLIPSE may not have all the headers required
        # by the program. So, we use `-idirafter` to append the fake libc headers
        # to the end of the header search path if the host toolchain is missing
        # any headers.
        source_include_flags = ["-I", str(input_path.parent.resolve())]
        fallback_include_flags = (
            ["-idirafter", str(_FAKE_LIBC_INCLUDE.resolve())]
            if _FAKE_LIBC_INCLUDE.exists()
            else []
        )
        subprocess.run(
            ["clang"]
            # Prefer local benchmark/example headers first.
            + source_include_flags
            # Add the fallback include .h flags to the Clang command.
            + fallback_include_flags
            # Add the direct Clang flags to the Clang command.
            + list(_DIRECT_CLANG_FLAGS)
            # Determine the output file path for the compiled program.
            + [str(input_path), "-o", str(compiled_output_path)],
            check=True,
        )

    # Return the path to the compiled output file.
    return str(compiled_output_path)


def _is_coreutils_input(input_path: Path) -> bool:
    """Deteremine if the input program is a Coreutils program by checking if it
    lives inside the vendored Coreutils tree."""

    resolved_input = input_path.resolve()
    resolved_coreutils_root = _COREUTILS_ROOT.resolve()
    return resolved_coreutils_root in (resolved_input, *resolved_input.parents)


def _compile_coreutils_program(input_path: Path, compiled_output_path: Path) -> str:
    """Compile a Coreutils program using the prepared Coreutils build tree.

    In a normal Coreutils build, a file (such as `src/foo.c`) is not compiled
    directly. Instead, the project is first bootstrapped and configured, which
    generates a build tree, derived headers, and Makefile rules. After that,
    a `make` command rebuilds the utility by compiling the source together with the
    gnulib/Coreutils support code and then linking the final executable.

    That normal build structure is important here because the utility depends
    on more than just its own translation unit:

    - generated headers such as entries from `BUILT_SOURCES`
    - Coreutils support libraries and gnulib compatibility code
    - the final link step that produces the real utility executable

    Therefore, we need to compile the program using the prepared Coreutils build tree.
    This is done by temporarily swapping the generated, processed code (that was
    generated by the preprocessor) into the real Coreutils source tree and then
    rebuilding the utility using the `make` command. This creates a LLVM bitcode (.bc)
    file that includes the generated headers and support libraries that a standalone
    compile would not include.

    This pass works as follows:
    1. make sure the prepared Coreutils tree exists
    2. map `foo-processed.c` back to the original `foo.c` build target
    3. temporarily swap the processed source into that build tree
    4. materialize generated headers listed in `BUILT_SOURCES`
    5. rebuild the utility with `wllvm` as the compiler
    6. run `extract-bc` on the final executable to recover the whole program LLVM bitcode
    7. copy the recovered whole-program `.bc` file into our expected output path
    """

    # Prepare the Coreutils build tree and get the environment variables needed
    # to compile the program.
    build_root, env = _prepare_coreutils_source_tree()

    # The preprocessor emits `foo-processed.c`, but the Coreutils build system
    # only knows the utility by its original source file and make target. This
    # maps the processed artifact back onto the checked-in source file that will
    # be temporarily overridden during the build.
    build_source_path = _coreutils_build_source_path(input_path)

    # Convert the restored source file path into the make target for the final
    # utility executable, for example `src/echo`.
    program_target = _coreutils_program_target(build_source_path)
    extract_bc_binary = _resolve_tool_binary("extract-bc")
    if not extract_bc_binary:
        raise RuntimeError(
            "extract-bc is required for Coreutils whole-program KLEE builds. "
            "Rebuild the devcontainer so the declared dependencies are installed."
        )

    print("Building linked Coreutils bitcode with wllvm...", flush=True)

    # Temporarily overwrite the original Coreutils source file with the
    # processed version so `make src/foo` rebuilds the instrumented program
    # instead of the checked-in one. The context manager always restores the
    # original contents afterward.
    with _coreutils_source_override(build_source_path, input_path):
        # Coreutils does not always generate its derived headers eagerly when we
        # ask for just one utility target. Build the full BUILT_SOURCES set up
        # front so the later `make src/foo` has all generated prerequisites.
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
        # Build a single utility at a time. Using `-j1` keeps the temporary
        # source-file override deterministic and avoids parallel build races
        # while the checked-in source tree is momentarily modified.
        make_command = ["make", "-j1"]
        if input_path != build_source_path:
            # Processed sources can introduce helper references that are resolved
            # only in the final linked program. This linker flag keeps the build
            # moving long enough for `extract-bc` to recover the whole-program
            # bitcode artifact we actually care about.
            make_command.append("LDFLAGS=-Wl,--unresolved-symbols=ignore-all")
        make_command.append(program_target)
        subprocess.run(
            make_command,
            cwd=build_root,
            env=env,
            check=True,
        )

        built_program_path = build_root / program_target
        # `wllvm` embeds enough metadata in the build outputs for `extract-bc`
        # to recover whole-program LLVM bitcode from the final linked
        # executable. This is the main reason we go through the real build
        # system instead of invoking clang on one processed `.c` file directly.
        subprocess.run(
            [extract_bc_binary, str(built_program_path)],
            cwd=build_root,
            env=env,
            check=True,
        )

        # Normalize the output location so the rest of the pipeline can consume
        # Coreutils and non-Coreutils bitcode through the same `compiled-input.bc`
        # path without caring which compile strategy produced it.
        built_bitcode_path = built_program_path.with_suffix(".bc")
        shutil.copy2(built_bitcode_path, compiled_output_path)
    return str(compiled_output_path)


def _prepare_coreutils_source_tree() -> tuple[Path, dict[str, str]]:
    """
    Return the prepared Coreutils build root and its required toolchain env.

    Coreutils compilation depends on a configured build tree created by the
    devcontainer setup. This helper validates that preparation step and returns
    the directory/environment pair used by the whole-program build flow.
    """

    build_root = _COREUTILS_ROOT
    env = _coreutils_klee_env()

    if not _COREUTILS_CONFIG_STAMP.exists() or not (build_root / "Makefile").exists():
        raise RuntimeError(
            "The devcontainer has not prepared Coreutils for whole-program KLEE "
            "builds yet. Rebuild/reopen the devcontainer or run "
            "bash .devcontainer/post-create.sh inside it."
        )

    return build_root, env


def _coreutils_klee_env() -> dict[str, str]:
    """Return the toolchain environment required for whole-program Coreutils BC.

    `wllvm` records the LLVM bitcode for each compiled object, and `extract-bc`
    later recovers linked whole-program bitcode from the final executable.

    The environment overrides are the important part:

    - `LLVM_COMPILER=clang` tells `wllvm` which frontend to wrap.
    - `CC=<path-to-wllvm>` forces the Coreutils build to compile through that
      wrapper instead of the default compiler.
    - `CFLAGS=<...>` injects the KLEE-friendly flags documented above into the
      normal Coreutils build.
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
            # `-s` and `--no-print-directory` keep the output machine-friendly so
            # we can reliably parse the printed BUILT_SOURCES list.
            "-s",
            "--no-print-directory",
            # We inject a tiny one-off make target that simply prints the fully
            # expanded value of `$(BUILT_SOURCES)`.
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
    """Resolve a required external tool from PATH.

    This keeps the rest of the module focused on workflow logic instead of
    repeating `shutil.which(...)` and the associated `None` handling.
    """

    tool_binary = shutil.which(tool_name)
    return tool_binary if tool_binary else None


def _coreutils_input_relative_path(input_path: Path) -> Path:
    """Return a Coreutils source path relative to the vendored project root."""

    return input_path.resolve().relative_to(_COREUTILS_ROOT.resolve())


def _coreutils_build_source_path(input_path: Path) -> Path:
    """Map generated processed sources back to the real Coreutils build input.

    The preprocessor writes files like `echo-processed.c`, but the Coreutils
    build system still knows the target as `src/echo`. This helper reverses
    that filename transformation so the later `make` command rebuilds the
    correct utility.
    """

    if input_path.suffix != ".c" or not input_path.stem.endswith("-processed"):
        return input_path

    original_path = input_path.with_name(
        f"{input_path.stem.removesuffix('-processed')}{input_path.suffix}"
    )
    if original_path.exists():
        return original_path

    return input_path


def _coreutils_program_target(input_path: Path) -> str:
    """Map `examples/coreutils/src/foo.c` to the make target `src/foo`.

    The whole-program build path currently assumes top-level Coreutils source
    files under `src/`; nested or non-utility files are intentionally rejected
    here because the surrounding build logic is not generalized beyond that.
    """
    relative_input_path = _coreutils_input_relative_path(input_path)
    if relative_input_path.parent != Path("src"):
        raise RuntimeError(
            "Whole-program Coreutils KLEE builds currently support top-level "
            "src/*.c inputs."
        )

    return f"src/{relative_input_path.stem}"


@contextmanager
def _coreutils_source_override(
    original_source_path: Path, replacement_source_path: Path
):
    """Temporarily replace a Coreutils source file while invoking the build.

    This lets us compile the processed `*-processed.c` content through the real
    Coreutils build system without permanently modifying the checked-in source
    tree. The context manager overwrites the source file just for the duration
    of the build and then restores the original bytes in a `finally` block.
    """

    if original_source_path.resolve() == replacement_source_path.resolve():
        yield
        return

    original_bytes = original_source_path.read_bytes()
    replacement_text = replacement_source_path.read_text()
    original_source_path.write_text(replacement_text)
    try:
        yield
    finally:
        original_source_path.write_bytes(original_bytes)
