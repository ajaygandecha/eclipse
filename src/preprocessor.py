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
_CPP_INCLUDES = (
    _COREUTILS_LIB,
    _COREUTILS_SRC,
    _COREUTILS_GNULIB_LIB,
    _COREUTILS_GL_LIB,
    _FAKE_LIBC_INCLUDE,
)
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
    "-D__inline=inline",
)


def _build_cpp_args(file_path: str | Path) -> list[str]:
    """Return the Clang preprocessing flags needed for a parseable translation unit.

    The returned argument list combines our compatibility defines with the
    source file's directory and the repository's vendored include roots. This
    keeps preprocessing deterministic and steers `pycparser` away from host
    system headers that often contain unsupported compiler extensions.
    """

    # Start with the compatibility flags above, then prepend the source file's
    # own directory and our vendored include trees so preprocessing sees the
    # same project headers regardless of which file we parse.
    source_path = Path(file_path).resolve()
    cpp_args = list(_CPP_ARGS)
    seen_paths: set[Path] = set()

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
    """Apply all enabled AST preprocessing passes and render the result.

    The file is first preprocessed with Clang into a `pycparser`-friendly AST.
    Guided-search metadata, loop bounds, GPIO constraints, and CLI harnessing
    are then applied in order before the final source-preserving renderer emits
    the processed C translation unit.
    """

    ast = parse_file(
        str(Path(file_path).resolve()),
        use_cpp=True,
        cpp_path="clang",
        cpp_args=_build_cpp_args(file_path),
    )
    guidance = None
    if not no_guided_se:
        guidance = find_risky_functions(ast)
        if guidance_output_path:
            write_guidance_file(guidance_output_path, guidance)

    if not no_loop_bounds:
        ast = add_loop_bounds(ast)
    if not no_gpio_constraints:
        ast = add_gpio_constraints(ast)

    if cli_config_path and not no_cli_constraints:
        ast = add_argument_constraints(ast, cli_config_path)

    return render_processed_source(file_path, ast)
