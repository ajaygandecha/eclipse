from pathlib import Path

from pycparser import parse_file, c_generator
from pycparser.c_ast import FileAST
from gpio_constraints import add_gpio_constraints
from loop_bounds import add_loop_bounds

KLEE_PREAMBLE = """extern int snprintf(char *str, int size, const char *format, ...);
extern void klee_make_symbolic(void *addr, unsigned long nbytes, const char *name);
extern void klee_assume(int condition);
extern void klee_assert(int condition);

static char *__eclipse_int_to_string(int value, char *buffer, int buffer_size)
{
  snprintf(buffer, buffer_size, "%d", value);
  return buffer;
}

"""

_REPO_ROOT = Path(__file__).resolve().parent.parent
_COREUTILS_LIB = _REPO_ROOT / "examples" / "coreutils" / "lib"
_COREUTILS_SRC = _REPO_ROOT / "examples" / "coreutils" / "src"
_COREUTILS_GNULIB_LIB = _REPO_ROOT / "examples" / "coreutils" / "gnulib" / "lib"
_COREUTILS_GL_LIB = _REPO_ROOT / "examples" / "coreutils" / "gl" / "lib"
_FAKE_LIBC_INCLUDE = _REPO_ROOT / "src" / "utils" / "fake_libc_include"
_CPP_INCLUDES = (
    _FAKE_LIBC_INCLUDE,
    _COREUTILS_LIB,
    _COREUTILS_SRC,
    _COREUTILS_GNULIB_LIB,
    _COREUTILS_GL_LIB,
)
_CPP_ARGS = (
    "-E",
    "-nostdinc",
    "-Wno-builtin-macro-redefined",
    "-D_GL_NO_INLINE_ERROR",
    "-D__attribute__(x)=",
    "-D__extension__=",
    "-D__asm__(x)=",
    "-D__restrict=",
    "-D__restrict__=",
    "-D__has_attribute(x)=0",
    "-D__has_c_attribute(x)=0",
    "-D__builtin_constant_p(x)=0",
    "-D__builtin_expect(x,y)=(x)",
    "-D__builtin_types_compatible_p(x,y)=0",
    "-D__builtin_choose_expr(c,x,y)=(y)",
    "-D__inline=inline",
)


def _build_cpp_args(file_path: str | Path) -> list[str]:
    source_path = Path(file_path).resolve()
    cpp_args = list(_CPP_ARGS)
    seen_paths: set[Path] = set()

    for include_path in (source_path.parent, *_CPP_INCLUDES):
        resolved_path = include_path.resolve()
        if not resolved_path.exists() or resolved_path in seen_paths:
            continue
        seen_paths.add(resolved_path)
        cpp_args.append(f"-I{resolved_path}")

    return cpp_args


def preprocess_file(file_path: str, cli_config_path: str | None = None) -> str:
    """Preprocesses the input file using the pycparser library"""
    ast = parse_file(
        str(Path(file_path).resolve()),
        use_cpp=True,
        cpp_path="clang",
        cpp_args=_build_cpp_args(file_path),
    )
    if cli_config_path:
        from argument_constraints import add_argument_constraints

        ast = add_argument_constraints(ast, cli_config_path)
    ast = constrain_gpio_reads(ast)
    ast = add_loop_bounds(ast)

    find_risky_functions(ast)

    # Convert the final AST back into C code.
    generator = c_generator.CGenerator()
    c_code = generator.visit(ast)
    return KLEE_PREAMBLE + c_code


def constrain_structured_arguments(ast: FileAST, cli_config_path: str) -> FileAST:
    from argument_constraints import add_argument_constraints

    return add_argument_constraints(ast, cli_config_path)


def constrain_gpio_reads(ast: FileAST) -> FileAST:
    return add_gpio_constraints(ast)


def find_risky_functions(ast: FileAST):
    ...
    # Create risky JSON
