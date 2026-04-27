# ECLIPSE

**ECLIPSE** *(Embedded CLI Program Symbolic Executor)* is a symbolic execution tool that finds memory safety vulnerabilities in C-based CLI programs. 

At a high level, ECLIPSE operates as a pipeline-style program which is the target CLI utility to analyze, and (2) a YAML-based CLI specification file. The CLI specification file describes the structure of valid input to the target C program and its constraints, such as supported flags and options, data types, and valid values (e.g., enumerations or bounds on integer ranges or string lengths). The program is first transformed by a custom preprocessor to constrain inputs, model hardware interactions, and bound potential sources of path explosion. ECLIPSE then compiles the transformed program into LLVM bitcode using Clang and performs symbolic execution us- ing KLEE with a guided search strategy. Finally, ECLIPSE produces a report describing discovered vulnerabilities along with concrete inputs that reproduce them. An overview of ECLIPSE’s workflow is shown in Figure 1. ECLIPSE and most of its functionality is written in Python.

To learn more about ECLIPSE, read our paper [here]().

## Structure

The structure of the repository is as follows:

```
FILE TREE HERE
```

- **`src`**: The source folder contains all of ECLIPSE's source code, including the entrypoint for ECLIPSE and for the preprocessor.
    - `main.py`: The entrypoint for ECLIPSE.
    - `preprocessor.py`: The core preprocessor functionality, which includes parsing the input C program into an AST and applying ECLIPSE's optimizations. These optimizations are separated into different files for better readability.
    - `clang.py`: Responsible for the compilation logic converting the processed C file into LLVM bitcode for KLEE to symbolically execute.
    - `klee.py`: Logic for symbolically executing the input LLVM bitcode.
- **`examples`**: Folder containing examples to run ECLIPSE on.
    - `preprocessing-tests`: These files contain tests just to ensure that preprocessing works correctly. Tests include checks for loop bounds, GPIO modeling, and CLI modeling.
    - `vulnerable`: These are intentionally vulnerable C programs used to check that ECLIPSE can successfully find vulnerabilites in an input program if they exist. These files (specifically `repeat.c`, `buggy.c`, `alarm-keypad.c`, and `irrigation-controller.c`) were the programs tested in our paper. For more information about each file and the methodology of how each were tested, see the Appendix of the paper.
    - `coreutils`: The CoreUtils folder is a submodule of this GitHub repository containing the implementation code for the CoreUtils library of standard Unix CLI programs. You can access all of the programs in the `coreutils/src` directory. In our paper, we tested `echo.c`, `expr.c`, and `seq.c`. More information about each file and the methology of how each were tested is located in the Appendix of the paper. *Note: we based this heavily on the [official KLEE docs](https://klee-se.org/tutorials/testing-coreutils/) describing how to test symbolic execution on CoreUtils.*

## Setup

To use ECLIPSE, first clone the repository and open the project in VS Code. The project has a pre-configured Docker DevContainer. Ensure that you have both [Docker Desktop]() and the [DevContainer extension]() installed, then open the project and select the "Reopen in DevContainer" option.

From there, ECLIPSE will begin setting up. This may take a while. The DevContainer should run the `post-create.sh` script, which should set up the CoreUtils project as well for testing purposes. This script also runs the `apply-guided-klee.sh` script, which applies a [patch file]() to KLEE's internal installation so that it can support guided symbolic execution. From there, try running your first test on `buggy.c` below!

## Example Workflow

To show how ECLIPSE can be used to find memory safety violation in a C utility program, we walk through a detailed example of the workflow running ECLIPSE on an example program - in this case, [`buggy.c`](). 

Recall that ECLIPSE requires two input programs - (1) C file to test and (2) the CLI specification for the program. Here, we created [`buggy.yml`]() to provide the CLI specification.

To run ECLIPSE on this program, we use the command:

```
eclipse examples/vulnerable/buggy.c --cli-config examples/vulnerable/buggy.yml
```

Upon running this command, ECLIPSE is going to create and output two files: (1) a [`buggy-processed.c`]() file that contains the output of ECLIPSE's preprocessing transformations on the orignal C file, and a [`buggy-guidance.json`]() which specifies potential "high-risk" functions to guide symbolic execution.

Once these files are created, ECLIPSE will compile the program and create a [`compiled-input.bc`]() LLVM bitcode file. This file is then symbolically executed. You will see a lot of output, some of which may look incomprehensible - this is just output while KLEE is symbolically executing. You should however, see the following lines:

```
KLEE: ERROR: examples/vulnerable/buggy-processed.c:57: memory error: object read only
KLEE: ERROR: examples/vulnerable/buggy-processed.c:74: memory error: invalid pointer: free
KLEE: ERROR: examples/vulnerable/buggy-processed.c:39: memory error: out of bound pointer
...
KLEE: done: total instructions = 16041
KLEE: done: completed paths = 1
KLEE: done: partially completed paths = 10
KLEE: done: generated tests = 4
KLEE run time: 3s
```

You can see ECLIPSE reporting three memory safety violations - which are all of the three present violations in the program! You will also see some data about how many instructions the symbolic execution engine (KLEE) executed and its total run time. ECLIPSE will also create a folder called `klee-output-<timestamp>` in the same directory as the input file with details about its execution and generated test cases.

Note that there are multiple flags that you can use with ECLIPSE:

| Flag | Description |
| ---- | ----------- |
| `--exit-on-first-error` | Stop KLEE as soon as it finds its first memory safety violation in the program. |
| `--no-loop-bounds` | Disables loop bounds constraining by the preprocessor. |
| `--no-gpio-constraints` | Disables GPIO constraining by the preprocessor. |
| `--no-cli-constraints` | Disables CLI input constraining by the preprocessor. |
| `--no-guided-se` | Disables guided symbolic execution. | 