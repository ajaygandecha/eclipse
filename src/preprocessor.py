from pathlib import Path

from pycparser import parse_file
from argument_constraints import add_argument_constraints
from gpio_constraints import add_gpio_constraints
from guided_se import find_risky_functions, write_guidance_file
from loop_bounds import add_loop_bounds
from render import render_processed_source

_REPO_ROOT = Path(__file__).resolve().parent.parent
_COREUTILS_LIB = _REPO_ROOT / "examples" / "coreutils" / "lib"
_COREUTILS_SRC = _REPO_ROOT / "examples" / "coreutils" / "src"
_COREUTILS_GNULIB_LIB = _REPO_ROOT / "examples" / "coreutils" / "gnulib" / "lib"
_COREUTILS_GL_LIB = _REPO_ROOT / "examples" / "coreutils" / "gl" / "lib"
_FAKE_LIBC_INCLUDE = _REPO_ROOT / "src" / "utils" / "fake_libc_include"

# Define the include paths that Clang will use to find the header files
_CPP_INCLUDES = (
    _COREUTILS_LIB,
    _COREUTILS_SRC,
    _COREUTILS_GNULIB_LIB,
    _COREUTILS_GL_LIB,
    _FAKE_LIBC_INCLUDE,
)

# Define the necessary Clang preprocessing flags for the AST to be parsed correctly.
# NOTE: Some of the flags added here are a response to running ECLIPSE on different
# CoreUtils programs.
_CPP_ARGS = (
    # Ask Clang to stop after preprocessing. `pycparser` expects plain C with
    # `#include`/`#define` already expanded instead of raw preprocessor syntax.
    "-E",
    # Avoid the host machine's real system headers. They often contain compiler-
    # specific extensions that `pycparser` cannot understand, so we prefer our
    # controlled include roots and fake libc headers below.
    "-nostdinc",
    # Some of the compatibility defines below intentionally shadow builtin
    # macros/functions, so suppress the resulting warning noise from Clang.
    "-Wno-builtin-macro-redefined",
    # Gnulib/Coreutils use this guard around inline-heavy headers. Defining it
    # keeps those headers on a simpler path during preprocessing.
    "-D_GL_NO_INLINE_ERROR",
    # Drop GCC-style attributes such as `__attribute__((noreturn))`. They are
    # useful to a real compiler but irrelevant to the AST rewrites we perform.
    "-D__attribute__(x)=",
    # Remove GCC's `__extension__` marker, which only tells the compiler to
    # accept a non-standard construct without warning.
    "-D__extension__=",
    # Strip inline assembly annotations/aliases. `pycparser` cannot model them,
    # and our source-to-source passes do not need them.
    "-D__asm__(x)=",
    # Normalize compiler-specific spellings of `restrict` away. Those qualifiers
    # matter for optimization, but not for loop/GPIO/CLI source rewriting.
    "-D__restrict=",
    "-D__restrict__=",
    # Force feature-detection macros down the "attribute unsupported" path so
    # headers do not emit syntax that depends on Clang/GCC extensions.
    "-D__has_attribute(x)=0",
    "-D__has_c_attribute(x)=0",
    # Treat builtin-constant checks as false so headers choose simpler fallback
    # code instead of compiler-only constant-folding branches.
    "-D__builtin_constant_p(x)=0",
    # Remove branch prediction hints while keeping the original condition.
    # `__builtin_expect(expr, hint)` becomes just `(expr)`.
    "-D__builtin_expect(x,y)=(x)",
    # Disable type-introspection builtins that appear in system-style headers.
    # We only need parseable C, not exact compiler metaprogramming behavior.
    "-D__builtin_types_compatible_p(x,y)=0",
    # Replace Clang/GCC's compile-time choose-expression builtin with its
    # fallback arm. This is a simplification, but it keeps headers parseable.
    "-D__builtin_choose_expr(c,x,y)=(y)",
    # Normalize GNU `__inline` to ordinary `inline` so the parser sees a more
    # standard spelling of the same keyword.
    # NOTE: Necessary for CoreUtils' `echo` program.
    "-D__inline=inline",
)


def _build_cpp_args(file_path: str | Path) -> list[str]:
    """
    Generates the arguments needed for the parser preprocessing step.

    The returned argument list includes:
    - Flags to make different C files parseable by pycparser.
    - Next, we need to tell Clang where to find the header files that
      are included in the source C file. This is done by adding -I flags
      for each of the include paths.
    """

    source_path = Path(file_path).resolve()

    # Start with the compatibility flags above, then prepend the source file's
    # own directory and our vendored include trees so preprocessing sees the
    # same project headers regardless of which file we parse.
    cpp_args = list(_CPP_ARGS)

    # We need to keep track of the paths we have already added to the argument list
    # to avoid duplicates.
    seen_paths: set[Path] = set()

    # Add the source file's own directory and our vendored include trees so
    # preprocessing sees the same project headers regardless of which file we parse.
    for include_path in (source_path.parent, *_CPP_INCLUDES):
        resolved_path = include_path.resolve()
        # Skip missing/duplicate include roots so we hand Clang a clean,
        # deterministic `-I...` list.
        if not resolved_path.exists() or resolved_path in seen_paths:
            continue
        seen_paths.add(resolved_path)
        cpp_args.append(f"-I{resolved_path}")

    return cpp_args


def preprocess_file(
    file_path: str,
    cli_config_path: str | None = None,
    no_loop_bounds: bool = False,
    no_gpio_constraints: bool = False,
    no_cli_constraints: bool = False,
    no_guided_se: bool = False,
    guidance_output_path: str | Path | None = None,
) -> str:
    """
    Apply all enabled AST preprocessing passes and render the result.

    First, the C file is parsed with pycparser into an AST. By default, pycparser
    does not parse all C files correctly because it expects plain C with macros
    (such as `#include` and `#define`) already expanded into standard C code. To
    process the file correctly, `pycparser` uses Clang to preprocess the file into
    a more parseable form with the option `use_cpp=True` and arguments for cpp.

    From there, the AST is modified to add loop bounds, GPIO constraints, and CLI
    constraints if they are enabled.

    Finally, the AST is rendered back into a C file using a custom file that
    preserves the original source text around the edited code. This is because
    `pycparser`'s standard C generator does not preserve comments, includes,
    macros, or other original code structural components that is necessary for
    Clang to correctly compile the file.
    """

    # Parse the input file into an AST.
    ast = parse_file(
        str(Path(file_path).resolve()),
        use_cpp=True,
        cpp_path="clang",
        cpp_args=_build_cpp_args(file_path),
    )

    # If guided symbolic execution is enabled, find the risky functions
    # and write the guidance metadata file for the guided searcher.
    if not no_guided_se and guidance_output_path:
        guidance = find_risky_functions(ast)
        write_guidance_file(guidance_output_path, guidance)

    # If loop bounding is enabled, add loop bounds to the AST.
    if not no_loop_bounds:
        ast = add_loop_bounds(ast)

    # If GPIO constraints are enabled, add GPIO constraints to the AST.
    if not no_gpio_constraints:
        ast = add_gpio_constraints(ast)

    # If CLI constraints are enabled, add CLI constraints to the AST.
    if cli_config_path and not no_cli_constraints:
        ast = add_argument_constraints(ast, cli_config_path)

    # Render the AST back into a C file.
    return render_processed_source(file_path, ast)
