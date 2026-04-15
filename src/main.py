import argparse
import os
import subprocess
import shutil
import sys
from pathlib import Path
from datetime import datetime

_REPO_ROOT = Path(__file__).resolve().parent.parent
_COREUTILS_ROOT = _REPO_ROOT / "examples" / "coreutils"
_FAKE_LIBC_INCLUDE = _REPO_ROOT / "src" / "utils" / "fake_libc_include"
_COREUTILS_CONFIG_STAMP = _COREUTILS_ROOT / ".eclipse-devcontainer-configured"
_COREUTILS_KLEE_CFLAGS = (
    "-g -O1 -Xclang -disable-llvm-passes "
    "-D__NO_STRING_INLINES -D_FORTIFY_SOURCE=0 -U__OPTIMIZE__"
)


def _build_clang_fallback_include_flags() -> list[str]:
    if _FAKE_LIBC_INCLUDE.exists():
        # Keep real system headers first, but use our fake libc headers as a
        # fallback for newer headers that may be missing on the host toolchain.
        return ["-idirafter", str(_FAKE_LIBC_INCLUDE.resolve())]
    return []


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


def _resolve_tool_binary(tool_name: str) -> str | None:
    tool_binary = shutil.which(tool_name)
    if tool_binary:
        return tool_binary
    return None


def _is_coreutils_input(input_path: Path) -> bool:
    resolved_input = input_path.resolve()
    resolved_coreutils_root = _COREUTILS_ROOT.resolve()
    return resolved_coreutils_root in (resolved_input, *resolved_input.parents)


def _coreutils_input_relative_path(input_path: Path) -> Path:
    return input_path.resolve().relative_to(_COREUTILS_ROOT.resolve())


def _coreutils_program_target(input_path: Path) -> str:
    relative_input_path = _coreutils_input_relative_path(input_path)
    if relative_input_path.parent != Path("src"):
        raise RuntimeError(
            "Whole-program Coreutils KLEE builds currently support top-level "
            "src/*.c inputs."
        )

    return f"src/{relative_input_path.stem}"


def _coreutils_built_sources(build_root: Path, env: dict[str, str]) -> list[str]:
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


def _coreutils_klee_env() -> dict[str, str]:
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


def _prepare_coreutils_source_tree(input_path: Path) -> tuple[Path, dict[str, str]]:
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
    build_root, env = _prepare_coreutils_source_tree(input_path)
    program_target = _coreutils_program_target(input_path)
    extract_bc_binary = _resolve_tool_binary("extract-bc")
    if not extract_bc_binary:
        raise RuntimeError(
            "extract-bc is required for Coreutils whole-program KLEE builds. "
            "Rebuild the devcontainer so the declared dependencies are installed."
        )

    print("Building linked Coreutils bitcode with wllvm...", flush=True)
    built_sources = _coreutils_built_sources(build_root, env)
    if built_sources:
        subprocess.run(
            ["make", "-j1", *built_sources],
            cwd=build_root,
            env=env,
            check=True,
        )
    make_command = ["make", "-j1"]
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


def compile_input(input_path: Path) -> str:
    """Compiles the input file using clang into a LLVM bitcode file"""

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


def run_klee(bitcode_file: str, original_input_file: str) -> str | None:
    """Symbolically executes the LLVM bitcode file using KLEE"""

    print(f"Running {bitcode_file} using klee...", flush=True)

    klee_binary = _resolve_klee_binary()
    if not klee_binary:
        print("KLEE binary not found; skipping symbolic execution.", flush=True)
        return None

    # Create a base output directory for the KLEE output.
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    output_directory = (
        Path(original_input_file).resolve().parent / f"klee-output-{timestamp}"
    )

    # Run the KLEE process using the bitcode file and the output directory.
    klee_command = [
        klee_binary,
        "--only-output-states-covering-new",
        f"-output-dir={str(output_directory)}",
    ]

    if _is_coreutils_input(Path(original_input_file)):
        klee_command.extend(["--libc=uclibc", "--posix-runtime"])

    klee_command.append(bitcode_file)

    result = subprocess.run(klee_command, check=False)

    if result.returncode != 0:
        print(
            f"KLEE exited with code {result.returncode}; see {output_directory} "
            "for diagnostics.",
            flush=True,
        )
        return None

    return str(output_directory)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preprocess a C file for ECLIPSE symbolic execution."
    )
    parser.add_argument("input_file", help="Path to the input C program.")
    # parser.add_argument(
    #     "--cli-config",
    #     required=True,
    #     help="Path to the YAML config describing CLI flags and symbolic constraints.",
    # )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    input_path = Path(args.input_file).resolve()

    # Preprocess the input file.
    # from preprocessor import preprocess_file
    # preprocessed_code = preprocess_file(input_path)
    # preprocessed_code = preprocess_file(input_path, args.cli_config)
    # print(preprocessed_code)

    # Compile the input file into a LLVM bitcode file.
    compiled_input_file = compile_input(input_path)
    print("Compiled.", flush=True)

    # Run the LLVM bitcode file using KLEE.
    output_directory = run_klee(compiled_input_file, input_path)
