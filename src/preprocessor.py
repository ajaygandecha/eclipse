from dataclasses import dataclass
from pathlib import Path

from pycparser import parse_file, c_generator
from pycparser.c_ast import FileAST, FuncDef
from argument_constraints import ORIGINAL_MAIN_NAME, build_cli_harness_source
from cli_config import load_cli_config
from gpio_constraints import add_gpio_constraints
from guided_se import find_risky_functions, write_guidance_file
from loop_bounds import add_loop_bounds

KLEE_PREAMBLE = """extern int snprintf(char *str, unsigned long size, const char *format, ...);
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
_COREUTILS_ROOT = _REPO_ROOT / "examples" / "coreutils"
_COREUTILS_LIB = _REPO_ROOT / "examples" / "coreutils" / "lib"
_COREUTILS_SRC = _REPO_ROOT / "examples" / "coreutils" / "src"
_COREUTILS_GNULIB_LIB = _REPO_ROOT / "examples" / "coreutils" / "gnulib" / "lib"
_COREUTILS_GL_LIB = _REPO_ROOT / "examples" / "coreutils" / "gl" / "lib"
_COREUTILS_ORIGINAL_SOURCE_PLACEHOLDER = "__ECLIPSE_COREUTILS_ORIGINAL_SOURCE__"
_FAKE_LIBC_INCLUDE = _REPO_ROOT / "src" / "utils" / "fake_libc_include"
_CPP_INCLUDES = (
    _COREUTILS_LIB,
    _COREUTILS_SRC,
    _COREUTILS_GNULIB_LIB,
    _COREUTILS_GL_LIB,
    _FAKE_LIBC_INCLUDE,
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


def preprocess_file(
    file_path: str,
    cli_config_path: str | None = None,
    no_loop_bounds: bool = False,
    no_gpio_constraints: bool = False,
    no_cli_constraints: bool = False,
    no_guided_se: bool = False,
    guidance_output_path: str | Path | None = None,
) -> str:
    """Preprocesses the input file using the pycparser library"""
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

    if cli_config_path and not no_cli_constraints and _is_coreutils_input(file_path):
        return _build_coreutils_cli_wrapper(file_path, cli_config_path)

    if cli_config_path and not no_cli_constraints:
        from argument_constraints import add_argument_constraints

        ast = add_argument_constraints(ast, cli_config_path)
    if not no_gpio_constraints:
        ast = constrain_gpio_reads(ast)
    if not no_loop_bounds:
        ast = add_loop_bounds(ast)

    if _is_coreutils_input(file_path):
        return _render_coreutils_processed_source(file_path, ast)

    # Convert the final AST back into C code.
    generator = c_generator.CGenerator()
    c_code = generator.visit(ast)
    return KLEE_PREAMBLE + c_code


def constrain_structured_arguments(ast: FileAST, cli_config_path: str) -> FileAST:
    from argument_constraints import add_argument_constraints

    return add_argument_constraints(ast, cli_config_path)


def constrain_gpio_reads(ast: FileAST) -> FileAST:
    return add_gpio_constraints(ast)


def _is_coreutils_input(file_path: str | Path) -> bool:
    resolved_input = Path(file_path).resolve()
    return _COREUTILS_ROOT.resolve() in (resolved_input, *resolved_input.parents)


def _build_coreutils_cli_wrapper(file_path: str | Path, cli_config_path: str) -> str:
    """Generate a wrapper that preserves the real Coreutils translation unit."""

    spec = load_cli_config(cli_config_path)
    harness_source = build_cli_harness_source(spec, uses_argv=True)
    return (
        f"#define main {ORIGINAL_MAIN_NAME}\n"
        f'#include "{_COREUTILS_ORIGINAL_SOURCE_PLACEHOLDER}"\n'
        "#undef main\n\n"
        f"{KLEE_PREAMBLE}"
        f"{harness_source}"
    )


@dataclass(frozen=True)
class _SourceSpan:
    start: int
    end: int


def _render_coreutils_processed_source(file_path: str | Path, ast: FileAST) -> str:
    """Rewrite only source-file function bodies, preserving Coreutils headers/macros."""

    source_path = Path(file_path).resolve()
    original_source = source_path.read_text()
    generator = c_generator.CGenerator()
    rewritten_source = original_source

    replacements: list[tuple[_SourceSpan, str]] = []
    for node in ast.ext:
        if not _is_original_source_function(node, source_path):
            continue
        span = _function_definition_span(original_source, node)
        replacements.append((span, generator.visit(node.body)))

    for span, replacement in sorted(
        replacements,
        key=lambda item: item[0].start,
        reverse=True,
    ):
        rewritten_source = (
            f"{rewritten_source[:span.start]}"
            f"{replacement}"
            f"{rewritten_source[span.end:]}"
        )

    return f"{KLEE_PREAMBLE}{rewritten_source}"


def _is_original_source_function(node: object, source_path: Path) -> bool:
    if not isinstance(node, FuncDef):
        return False
    coord = getattr(node.decl, "coord", None)
    return str(getattr(coord, "file", "")) == str(source_path)


def _function_definition_span(source_text: str, node: FuncDef) -> _SourceSpan:
    body_coord = node.body.coord
    start = _line_col_to_offset(source_text, body_coord.line, body_coord.column)
    end = _find_matching_brace(source_text, start) + 1
    return _SourceSpan(start=start, end=end)


def _line_col_to_offset(source_text: str, line: int, column: int) -> int:
    current_line = 1
    offset = 0
    while current_line < line:
        next_newline = source_text.find("\n", offset)
        if next_newline == -1:
            raise ValueError(f"Unable to find line {line} in source text.")
        offset = next_newline + 1
        current_line += 1
    return offset + column - 1


def _find_matching_brace(source_text: str, brace_offset: int) -> int:
    if source_text[brace_offset] != "{":
        raise ValueError("Expected function body to begin with an opening brace.")

    depth = 0
    index = brace_offset
    in_string = False
    in_char = False
    in_line_comment = False
    in_block_comment = False
    escaping = False

    while index < len(source_text):
        char = source_text[index]
        next_char = source_text[index + 1] if index + 1 < len(source_text) else ""

        if in_line_comment:
            if char == "\n":
                in_line_comment = False
            index += 1
            continue

        if in_block_comment:
            if char == "*" and next_char == "/":
                in_block_comment = False
                index += 2
                continue
            index += 1
            continue

        if in_string:
            if escaping:
                escaping = False
            elif char == "\\":
                escaping = True
            elif char == '"':
                in_string = False
            index += 1
            continue

        if in_char:
            if escaping:
                escaping = False
            elif char == "\\":
                escaping = True
            elif char == "'":
                in_char = False
            index += 1
            continue

        if char == "/" and next_char == "/":
            in_line_comment = True
            index += 2
            continue

        if char == "/" and next_char == "*":
            in_block_comment = True
            index += 2
            continue

        if char == '"':
            in_string = True
            index += 1
            continue

        if char == "'":
            in_char = True
            index += 1
            continue

        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index

        index += 1

    raise ValueError("Unable to locate the end of the function definition.")
