import sys
import subprocess
from pathlib import Path
from datetime import datetime

def compile_input(input_path: Path) -> str:
    """Compiles the input file using clang into a LLVM bitcode file"""

    print(f"Compiling {input_path} using clang...")

    # Create a path for the compiled output file.
    compiled_output_path = input_path.parent / "compiled-input.bc"

    # Run the clang process using the input path as the source file and
    # the correct settings to compile an input C file into LLVM bitcode
    # that can be used by KLEE.
    subprocess.run([
        "clang",
        "-I",
        "/usr/include",
        "-emit-llvm",
        "-c",
        "-g",
        "-O0",
        "-Xclang",
        "-disable-O0-optnone",
        str(input_path),
        "-o",
        str(compiled_output_path),
    ], check=True)

    # Return the path to the compiled output file.
    return str(compiled_output_path)

def run_klee(bitcode_file: str, original_input_file: str) -> None:
    """Symbolically executes the LLVM bitcode file using KLEE"""

    print(f"Running {bitcode_file} using klee...")

    # Create a base output directory for the KLEE output.
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    output_directory = Path(original_input_file).resolve().parent / f"klee-output-{timestamp}"

    # Run the KLEE process using the bitcode file and the output directory.
    subprocess.run([
        "klee",
        f"-output-dir={str(output_directory)}",
        bitcode_file,
    ], check=True)

    return str(output_directory)
    
if __name__ == "__main__":
    input_file = sys.argv[1]

    input_path = Path(input_file).resolve()

    # Compile the input file into a LLVM bitcode file.
    compiled_input_file = compile_input(input_path)

    # Run the LLVM bitcode file using KLEE.
    output_directory = run_klee(compiled_input_file, input_file)