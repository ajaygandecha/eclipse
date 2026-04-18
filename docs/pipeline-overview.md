# ECLIPSE Pipeline Overview

This document explains the current ECLIPSE execution pipeline end to end.

It focuses on:

- what each step does
- which module owns that step
- why the implementation is structured the way it is
- what assumptions and tradeoffs each step makes

The current flow is:

1. Parse CLI arguments and locate inputs
2. Load and validate the CLI YAML configuration
3. Preprocess the source file into a `pycparser` AST
4. Optionally compute guided-search metadata
5. Apply AST transformation passes in a fixed order
6. Render the transformed AST back into source while preserving the original file text where possible
7. Compile the processed source into LLVM bitcode
8. Run KLEE on the resulting bitcode

## High-Level Flow

The main entrypoint is [`src/main.py`](/Users/ajaygandecha/Developer/eclipse/src/main.py).

At a high level, `main.py` does this:

```text
input C file
  -> preprocess_file(...)
  -> write *-processed.c
  -> compile_input(...)
  -> run_klee(...)
```

There are two important ideas that shape the current design:

- All source rewriting happens at the AST level during preprocessing.
- Final source emission uses a source-preserving renderer instead of regenerating the whole translation unit from scratch.

That second point matters a lot. The project intentionally avoids full-file round-tripping through `pycparser.c_generator` because that would lose comments, preprocessor structure, and other original source layout details.

## Step 1: Entrypoint And Argument Parsing

Owned by: [`src/main.py`](/Users/ajaygandecha/Developer/eclipse/src/main.py)

`main.py` is responsible for orchestration, not transformation logic.

It performs four main jobs:

- parses command-line flags
- resolves input/output paths
- calls the preprocessing pipeline
- calls the compile and KLEE execution pipeline

### Inputs

The current command shape is:

```bash
python3 src/main.py <input.c> --cli-config <config.yml>
```

The important flags are:

- `--cli-config`
  - required for structured CLI harness generation
- `--no-loop-bounds`
  - disables loop bounding
- `--no-gpio-constraints`
  - disables GPIO read rewriting
- `--no-cli-constraints`
  - disables harness generation
- `--no-guided-se`
  - disables guided symbolic execution metadata generation

### Output Paths

`main.py` derives two important artifact paths from the input file:

- `*-processed.c`
  - the emitted transformed C source
- `*-guidance.json`
  - guided-search metadata for KLEE, when enabled

These are created using:

- `_processed_output_path(...)`
- `_guidance_output_path(...)`

The main file does not care how preprocessing is implemented internally; it just treats it as “source in, transformed source out”.

## Step 2: CLI Configuration Loading

Owned by: [`src/cli_config.py`](/Users/ajaygandecha/Developer/eclipse/src/cli_config.py)

The CLI YAML file is the declarative description of how ECLIPSE should model command-line input.

The loader entrypoint is:

- `load_cli_config(...)`

### What The Loader Produces

It converts YAML into a typed `CLIProgramSpec`, which contains:

- `program`
- `entry_point`
- `klee_posix_command`
- `argv0`
- `elements`

The `elements` field is a sequence of typed argument descriptions:

- `OptionElement`
- `PositionalElement`
- `OptionValueElement`

### Why This Exists

The source transformer in `argument_constraints.py` needs a structured description of:

- which flags may appear
- which values are symbolic
- which elements are optional
- what ranges or length limits apply

Rather than infer that from raw source code, ECLIPSE takes an explicit schema.

### Validation Strategy

The loader rejects:

- legacy schema formats
- unknown keys
- duplicate ids
- invalid type combinations
- invalid parent relationships for `option_value`
- invalid numeric ranges

This means later passes can assume the config is already well-formed.

## Step 3: Source Preprocessing Into An AST

Owned by: [`src/preprocessor.py`](/Users/ajaygandecha/Developer/eclipse/src/preprocessor.py)

The top-level preprocessing entrypoint is:

- `preprocess_file(...)`

This function is the main AST pipeline coordinator.

### What `preprocess_file(...)` Does

It:

1. runs `clang -E` through `pycparser.parse_file(...)`
2. optionally computes guided-search metadata
3. applies the enabled AST passes in order
4. renders the final AST back into C source

### Why Clang Is Used First

`pycparser` does not parse raw real-world C very well on its own, especially when code uses:

- `#include`
- macros
- GNU extensions
- compiler-specific builtins

So ECLIPSE preprocesses the file first with Clang and a carefully chosen set of compatibility flags.

### `_build_cpp_args(...)`

This helper constructs the Clang preprocessing arguments.

It combines:

- a fixed set of compatibility flags
- the input file's own directory
- vendored Coreutils include directories
- fake libc headers

The goal is not “compile the program exactly the way production would”.
The goal is:

- expand headers and macros
- simplify compiler-specific syntax
- give `pycparser` something stable and parseable

### Why The Include Setup Looks Broader Than A Single-File Tool

Even though not every input is a Coreutils program, ECLIPSE currently keeps the include environment broad enough to support the vendored examples and project test fixtures consistently.

That means preprocessing stays predictable across different input types.

## Step 4: Guided Symbolic Execution Analysis

Owned by: [`src/guided_se.py`](/Users/ajaygandecha/Developer/eclipse/src/guided_se.py)

This step is optional and is skipped when `--no-guided-se` is set.

The main functions are:

- `find_risky_functions(...)`
- `write_guidance_file(...)`

### What This Analysis Does

It walks each function body and records whether the function appears “interesting” for symbolic exploration.

Examples of currently tracked patterns include:

- dangerous API calls such as `strcpy`, `sprintf`, `memcpy`
- writes through pointer arithmetic
- non-constant array index writes

The result is stored in `GuidanceMetadata`.

### Why This Exists

Symbolic execution can spend a lot of time in uninteresting paths.
The guidance analysis gives KLEE a lightweight signal about where risky behavior is more likely to exist.

### Output

The guidance metadata is written as JSON to `*-guidance.json`.

That file is later passed to KLEE via an environment variable:

- `ECLIPSE_GUIDANCE_FILE`

## Step 5: AST Transformation Passes

Owned by:

- [`src/loop_bounds.py`](/Users/ajaygandecha/Developer/eclipse/src/loop_bounds.py)
- [`src/gpio_constraints.py`](/Users/ajaygandecha/Developer/eclipse/src/gpio_constraints.py)
- [`src/argument_constraints.py`](/Users/ajaygandecha/Developer/eclipse/src/argument_constraints.py)

The pass order in `preprocess_file(...)` is:

1. loop bounds
2. GPIO constraints
3. CLI constraints

That order is intentional.

### Why This Order

Loop bounds and GPIO rewriting both operate on the original program body.
CLI constraints are different: they rename the original `main` and append a generated harness `main`.

Running CLI last means:

- the original program body is transformed first
- then the renamed original entrypoint is preserved in the output
- then the new symbolic harness is added on top

This keeps the final emitted `*-processed.c` easy to reason about.

### Step 5A: Loop Bounding

Owned by: [`src/loop_bounds.py`](/Users/ajaygandecha/Developer/eclipse/src/loop_bounds.py)

Entry point:

- `add_loop_bounds(...)`

#### What It Does

For every `while` and `for` loop, the pass:

- creates a fresh counter variable such as `__eclipse_loop_bound_0`
- initializes it before the loop
- extends the loop condition with `counter < MAX_ITERATIONS`
- increments the counter at the end of the loop body

#### Example Shape

Conceptually:

```c
while (cond) {
  body;
}
```

becomes:

```c
int __eclipse_loop_bound_0 = 0;
while (cond && __eclipse_loop_bound_0 < 10) {
  body;
  __eclipse_loop_bound_0++;
}
```

#### Why It Is Implemented As An AST Rewrite

This is a structural transformation:

- loop conditions change
- new declarations are inserted
- loop bodies may need to become compound blocks

Doing that textually would be brittle.
The AST approach makes it precise and language-aware.

### Step 5B: GPIO Constraint Injection

Owned by: [`src/gpio_constraints.py`](/Users/ajaygandecha/Developer/eclipse/src/gpio_constraints.py)

Entry point:

- `add_gpio_constraints(...)`

#### What It Does

This pass replaces supported GPIO read calls with symbolic variables.

Currently recognized functions are:

- `gpiod_line_get_value`
- `gpiod_line_request_get_value`

#### How It Works

When the pass encounters one of those reads inside an expression, it:

- introduces a symbolic variable
- emits the supporting prefix statements needed to make that variable symbolic
- replaces the original GPIO read expression with the symbolic identifier

Because these reads can appear inside complex expressions, this pass sometimes has to lower expressions into explicit statement sequences.

#### Why The Pass Is More Complex Than Loop Bounds

Loop bounds mostly modify already-separate statement structures.

GPIO reads can appear:

- in `if` conditions
- in `for` loop init/cond/next clauses
- inside function arguments
- inside nested expressions

So the pass must carefully pull side effects out into statement prefixes while preserving the original evaluation structure as much as possible.

### Step 5C: CLI Harness Generation

Owned by: [`src/argument_constraints.py`](/Users/ajaygandecha/Developer/eclipse/src/argument_constraints.py)

Entry point:

- `add_argument_constraints(...)`

This is the pass that turns a normal `main(...)` into a KLEE-friendly symbolic CLI harness.

#### High-Level Strategy

The pass does three things:

1. validates that the existing entrypoint is compatible
2. renames the original entrypoint to `__eclipse_original_main`
3. appends a brand-new generated `main` that builds symbolic `argv`

#### Validation

The pass verifies:

- the entrypoint exists
- it returns `int`
- its signature is either:
  - `int main()`
  - `int main(int argc, char **argv)` or equivalent

This prevents the harness generator from producing a broken wrapper around unsupported entrypoint shapes.

#### Renaming

The original entrypoint is renamed from `main` to:

- `__eclipse_original_main`

That preserves the original logic while freeing up the name `main` for the generated harness.

#### Harness Generation

`HarnessSourceBuilder` constructs readable C source for the new symbolic `main`.

Depending on the CLI spec, it emits:

- symbolic presence booleans for optional elements
- symbolic selector integers for options with multiple spellings
- symbolic string buffers plus length constraints
- symbolic integer values plus range constraints
- `argv` construction logic in the declared element order

The final generated `main` calls:

- `__eclipse_original_main(...)`

with the synthesized `argc` and `argv`.

#### Why This Pass Appends A New Top-Level Function

Unlike the other passes, CLI transformation is not just modifying existing code.
It adds a completely new entrypoint.

That is one of the main reasons the renderer has to handle both:

- rewriting existing source-backed functions
- appending generated top-level nodes

## Step 6: Rendering The Processed Source

Owned by: [`src/render.py`](/Users/ajaygandecha/Developer/eclipse/src/render.py)

Entry point:

- `render_processed_source(...)`

This module is the key “how do we get back to C source?” layer.

### The Core Design Choice

ECLIPSE does **not** emit the whole translation unit using `pycparser.c_generator`.

Instead, it:

- reads the original source file text
- identifies source-backed function definitions and function declarations
- replaces only those spans with regenerated code from the transformed AST
- appends generated top-level functions such as the CLI harness

### Why Not Regenerate The Whole File?

Because `pycparser` does not preserve:

- comments
- `#include` lines in their original form
- macro structure
- formatting and layout
- various source-level preprocessor details

For this project, preserving the original file shape is valuable.

### What The Renderer Preserves

It preserves everything outside rewritten function-like spans, including:

- includes
- macros
- comments
- unrelated globals
- general source layout

### What The Renderer Rewrites

It rewrites:

- function definitions from the source file
- function declarations from the source file
- generated top-level nodes appended by later passes

### How It Finds Replacement Spans

The renderer uses source coordinates from AST nodes and then performs careful text scanning to determine:

- where a function-like construct begins
- where a function body block begins
- where the matching closing brace lies
- where a declaration terminator lies

This is why `render.py` contains multiple scanning helpers such as:

- `_find_function_like_start(...)`
- `_find_block_start(...)`
- `_find_matching_brace(...)`
- `_find_declaration_terminator(...)`

These helpers avoid naïve string replacement and let the renderer preserve the surrounding source text reliably.

### KLEE Runtime Preamble

The renderer also prepends `KLEE_PREAMBLE`, which declares runtime functions and provides:

- `klee_make_symbolic`
- `klee_assume`
- `klee_assert`
- `__eclipse_int_to_string(...)`

The generated CLI harness relies on these declarations.

## Step 7: Compiling To LLVM Bitcode

Owned by: [`src/clang.py`](/Users/ajaygandecha/Developer/eclipse/src/clang.py)

Entry point:

- `compile_input(...)`

This step turns `*-processed.c` into a `.bc` file suitable for KLEE.

There are currently two compile models.

### Model 1: Ordinary Single-File Compilation

For normal inputs, ECLIPSE invokes Clang directly with:

- `-emit-llvm`
- `-c`
- `-g`
- `-O0`
- `-Xclang -disable-O0-optnone`

This produces LLVM bitcode for a single translation unit.

#### Why `-disable-O0-optnone` Is Used

At `-O0`, Clang normally adds `optnone`, which can interfere with later analysis and optimization expectations.
This flag keeps the IR more useful for symbolic execution.

#### Fake Libc Fallback Headers

`_build_clang_fallback_include_flags(...)` may add:

- `-idirafter <fake_libc_include>`

This lets Clang fall back to project-supplied fake libc headers when the host toolchain is missing or exposing incompatible headers.

### Model 2: Coreutils Whole-Program Bitcode

For inputs under `examples/coreutils`, ECLIPSE uses the Coreutils build system instead of direct Clang compilation.

This path exists because Coreutils programs depend on:

- generated headers
- shared support libraries
- the full configured build tree

Compiling only `foo.c` directly would not produce the right whole-program artifact.

#### How The Coreutils Path Works

1. Validate that the devcontainer-prepared Coreutils build tree exists
2. Resolve the original source path corresponding to `foo-processed.c`
3. Temporarily replace the original source with the processed source
4. Build the utility with `make` using `wllvm`
5. Run `extract-bc` on the final executable
6. Copy the resulting `.bc` into the expected output location

#### Why `wllvm` And `extract-bc` Are Used

`wllvm` records LLVM bitcode for the objects participating in the build.
`extract-bc` then recovers bitcode from the linked final program.

That gives KLEE a whole-program bitcode artifact instead of just one object file.

#### Why `BUILT_SOURCES` Is Materialized First

Coreutils generates some headers lazily, and going straight to `make src/foo` can fail if those generated headers have not been produced yet.

So `_coreutils_built_sources(...)` asks Make for the expanded `BUILT_SOURCES` list and builds those first.

### Why There Are Two Compile Models

The compile split is not about preprocessing anymore.
It is about the build environment required by the program being analyzed.

- simple standalone files can be compiled directly
- Coreutils needs a real project build

## Step 8: Running KLEE

Owned by: [`src/klee.py`](/Users/ajaygandecha/Developer/eclipse/src/klee.py)

Entry point:

- `run_klee(...)`

This step is responsible for:

- locating the `klee` binary
- creating an output directory
- building the KLEE command
- preparing the runtime environment
- running KLEE

### Output Directory Layout

Each run gets a timestamped output directory next to the original input file:

- `klee-output-<timestamp>`

That keeps symbolic execution artifacts close to the program under test.

### Command Construction

`_build_klee_command(...)` constructs the command in a fixed layout:

1. KLEE binary
2. default KLEE execution options
3. optional guided-search options
4. bitcode file path
5. optional POSIX runtime command arguments

That last point is important: POSIX runtime args must be appended after the bitcode path.

### Guided Search

When guided search is enabled:

- KLEE gets `--search=guided`
- KLEE also gets `--search=nurs:covnew`
- `ECLIPSE_GUIDANCE_FILE` is set in the environment

This lets KLEE use the earlier risky-function analysis during path exploration.

### POSIX Runtime Arguments

If CLI constraints are disabled, `main.py` falls back to `klee_posix_command` from the YAML config.

That means there are two distinct CLI modeling modes:

- generated symbolic harness in the transformed source
- raw KLEE POSIX runtime argument generation

The current normal mode is the generated harness approach.

## Putting The Pieces Together

Here is the full logical pipeline:

```text
main.py
  -> load CLI config path
  -> preprocess_file(...)
       -> clang -E + pycparser AST
       -> optional guided risk analysis
       -> loop bounds pass
       -> GPIO constraint pass
       -> CLI harness pass
       -> source-preserving render
  -> write *-processed.c
  -> compile_input(...)
       -> direct clang bitcode build
          or
       -> Coreutils whole-program wllvm/extract-bc build
  -> run_klee(...)
       -> build command/environment
       -> execute symbolic run
```

## Why The Current Architecture Looks The Way It Does

The design is trying to balance three competing goals:

### 1. Make transformations structurally correct

AST rewrites are used for:

- loop surgery
- expression rewriting
- `main` renaming
- harness generation

This avoids brittle textual edits.

### 2. Preserve the original source text as much as possible

The renderer only rewrites function-like spans and generated nodes instead of regenerating the whole file.

This keeps emitted `*-processed.c` files readable and close to the original source.

### 3. Support both simple files and real project builds

Compilation is split so:

- normal files stay simple
- Coreutils still gets a faithful whole-program bitcode build

## Current Tradeoffs And Limitations

These are useful to keep in mind while evolving the pipeline.

### Source-Preserving Rendering Is Narrower Than Full AST Emission

The renderer is ideal for:

- function body rewrites
- function signature renames
- appended top-level helper/harness functions

It is less naturally suited for arbitrary top-level restructuring across the entire file.

### Preprocessing Depends On Compatibility Defines

The Clang preprocessing flags in `preprocessor.py` intentionally simplify or erase some compiler-specific behavior to make parsing possible.

That is acceptable for source transformation, but it is not a perfect semantic model of every original program.

### Coreutils Still Needs A Separate Compile Path

Preprocessing is unified now, but compilation is not.

That split is currently justified by the build requirements of Coreutils, not by source transformation concerns.

## Recommended Mental Model

The simplest way to think about the current system is:

- `main.py` orchestrates
- `cli_config.py` explains what CLI to synthesize
- `preprocessor.py` builds the AST and runs passes
- `guided_se.py` scores risky functions for search guidance
- `loop_bounds.py` makes loops finite
- `gpio_constraints.py` turns GPIO reads into symbolic inputs
- `argument_constraints.py` turns CLI specs into a symbolic harness
- `render.py` emits a readable processed C file while preserving original source text
- `clang.py` turns processed C into LLVM bitcode
- `klee.py` runs symbolic execution

That is the current “one sentence per module” map of the system.
