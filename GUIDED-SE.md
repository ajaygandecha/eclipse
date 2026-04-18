# Guided Symbolic Execution in ECLIPSE

This document explains the guided symbolic execution approach implemented in this repository.

## Overview

ECLIPSE uses a lightweight, function-level guided search strategy on top of KLEE.

The flow is:

1. Parse the input C source with `pycparser`.
2. Identify functions that contain simple high-signal risky patterns.
3. Emit a sibling JSON guidance file next to the original source.
4. Compile the program to LLVM bitcode.
5. Run a custom KLEE `guided` searcher that prioritizes states executing inside risky functions.

This is intentionally a pragmatic heuristic, not a full static-analysis or distance-to-bug system.

## Design Goal

The goal is to bias KLEE toward code that is more likely to contain memory-safety or input-handling bugs, without adding a heavy analysis pipeline.

Instead of computing precise control-flow distances or taint reachability, ECLIPSE asks a simpler question:

> Which functions look risky enough that states inside them should be explored earlier?

That keeps the implementation small, explainable, and easy to evaluate.

## Python-Side Analysis

The guidance analysis lives in [src/guided_se.py](/Users/ajaygandecha/Developer/eclipse/src/guided_se.py:1).

It walks each `FuncDef` in the AST and marks a function as risky if it contains at least one of the following:

- Calls to dangerous or error-prone APIs such as `strcpy`, `strcat`, `gets`, `sprintf`, `memcpy`, `memmove`, `strncpy`, or `snprintf`
- Writes to an array using a non-constant index
- Writes through a pointer derived from pointer arithmetic

The analysis is deliberately conservative. False positives are acceptable; the point is to prioritize likely-interesting functions, not to prove a bug statically.

## Guidance File

For an input like `examples/coreutils/src/echo.c`, ECLIPSE emits:

`examples/coreutils/src/echo-guidance.json`

The file is written automatically during preprocessing. Users do not need to pass a guidance path manually.

Current format:

```json
{
  "analysis_version": 1,
  "risky_functions": ["example_fn"],
  "notes": {
    "example_fn": ["calls dangerous API 'strcpy'"]
  }
}
```

`risky_functions` is the field consumed by KLEE. `notes` is mainly there to make the analysis easier to inspect and debug.

## KLEE-Side Guided Search

The custom KLEE integration is stored as a repo-owned patch in:

[.devcontainer/klee-guided-search.patch](/Users/ajaygandecha/Developer/eclipse/.devcontainer/klee-guided-search.patch:1)

It adds:

- A new `guided` search mode
- A `GuidedSearcher` implementation in KLEE core
- JSON loading for the generated guidance metadata

The searcher is function-level and binary-scored:

- If a state is currently executing in a risky function, it gets priority
- Otherwise, it is treated as non-risky

This means guided search changes scheduling only. It does not change symbolic execution semantics, constraints, or path feasibility.

## How KLEE Finds the Guidance File

The Python launcher exports the generated guidance path to KLEE through the environment variable:

`ECLIPSE_GUIDANCE_FILE`

This avoids needing a user-facing `--guidance-file` flag.

If that environment variable is not present, the patched KLEE build falls back to deriving a sibling filename from the loaded module path, including stripping a trailing `-processed` stem when needed.

In normal ECLIPSE usage, the environment path is the authoritative source and avoids naming mismatches for linked Coreutils builds.

## Command Construction

When guided SE is enabled, ECLIPSE runs KLEE with:

```bash
klee --search=guided --search=nurs:covnew ...
```

This combines:

- `guided` for vulnerability-directed prioritization
- `nurs:covnew` for KLEE’s usual coverage-seeking behavior

That pairing keeps the search strategy closer to standard KLEE behavior while still injecting ECLIPSE’s vulnerability bias.

## Integration Points in This Repo

- [src/guided_se.py](/Users/ajaygandecha/Developer/eclipse/src/guided_se.py:1)
  AST analysis and JSON emission helpers
- [src/preprocessor.py](/Users/ajaygandecha/Developer/eclipse/src/preprocessor.py:1)
  Runs the guidance analysis during preprocessing
- [src/main.py](/Users/ajaygandecha/Developer/eclipse/src/main.py:1)
  Emits the guidance file and launches the pipeline
- [src/klee.py](/Users/ajaygandecha/Developer/eclipse/src/klee.py:1)
  Builds the KLEE command and exports `ECLIPSE_GUIDANCE_FILE`
- [.devcontainer/klee-guided-search.patch](/Users/ajaygandecha/Developer/eclipse/.devcontainer/klee-guided-search.patch:1)
  KLEE modifications
- [.devcontainer/apply-guided-klee.sh](/Users/ajaygandecha/Developer/eclipse/.devcontainer/apply-guided-klee.sh:1)
  Applies the patch and rebuilds KLEE inside the devcontainer

## Devcontainer Persistence

The patched KLEE is meant to persist across fresh containers by rebuilding from repo-tracked artifacts.

The key command is:

```bash
bash .devcontainer/apply-guided-klee.sh
```

That script:

1. Applies the tracked KLEE patch if needed
2. Detects already-patched trees safely
3. Rebuilds the KLEE binary

The devcontainer post-create hook also runs it automatically:

```bash
bash .devcontainer/post-create.sh
```

If a VS Code container is stale and still shows the older behavior, rerun one of the commands above or rebuild the devcontainer.

## Example

Suppose the source contains:

```c
void log_status(const char *msg) {
    printf("%s\n", msg);
}

void parse_packet(char *input) {
    char buf[16];
    strcpy(buf, input);
}
```

The guidance pass emits `parse_packet` as risky.

If KLEE has active states in both `log_status` and `parse_packet`, the `GuidedSearcher` prefers the state in `parse_packet`.

## Limitations

This implementation is intentionally simple.

It does not:

- Compute per-basic-block risk
- Compute distances to sinks
- Perform full taint analysis
- Prove a risky write is reachable
- Replace good harnesses or input modeling

It is best understood as a practical heuristic that nudges KLEE toward code regions that are more likely to matter.

## Practical Notes

- The guidance file is generated automatically whenever guided SE is enabled.
- `--no-guided-se` disables both guidance emission and guided search.
- Coreutils whole-program builds must be run in the prepared devcontainer environment.
- Host-side macOS runs can fail much earlier during Coreutils preprocessing because the Coreutils/KLEE flow is Linux/devcontainer-oriented.

## Summary

ECLIPSE’s guided symbolic execution is a small, function-level enhancement to KLEE:

- lightweight AST risk detection
- automatic JSON guidance emission
- automatic handoff to patched KLEE
- a custom searcher that prioritizes states in risky functions

That keeps the implementation manageable while still giving the project a real vulnerability-directed search component.
