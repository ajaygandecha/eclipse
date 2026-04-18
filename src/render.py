from dataclasses import dataclass
from pathlib import Path

from pycparser import c_generator
from pycparser.c_ast import Decl, FileAST, FuncDecl, FuncDef, Node

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


@dataclass(frozen=True)
class _SourceSpan:
    start: int
    end: int


def render_processed_source(file_path: str | Path, ast: FileAST) -> str:
    """Render AST changes while preserving the original source text around them.

    `pycparser` can round-trip function bodies well, but it does not preserve
    comments, includes, macros, or other preprocessor structure when we emit an
    entire translation unit. Our preprocessing passes only touch function-level
    code plus the generated CLI harness, so we splice those pieces back into the
    original source and leave the rest of the file exactly as-authored.
    """

    source_path = Path(file_path).resolve()
    original_source = source_path.read_text()
    generator = c_generator.CGenerator()
    rewritten_source = original_source

    replacements: list[tuple[_SourceSpan, str]] = []
    appended_nodes: list[str] = []
    for node in ast.ext:
        # Only function definitions/prototypes are rewritten. That keeps the
        # surrounding includes, macros, comments, and global declarations in
        # their original form while still letting the AST drive our edits.
        if _is_source_file_function_like(node, source_path):
            span = _function_like_span(original_source, node)
            replacements.append((span, generator.visit(node)))
            continue
        # Generated harness functions have no source coordinates, so we append
        # them after the preserved source instead of trying to splice them in.
        if _is_generated_top_level_node(node):
            appended_nodes.append(generator.visit(node))

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

    rendered_parts = [KLEE_PREAMBLE, rewritten_source.rstrip()]
    if appended_nodes:
        rendered_parts.append("\n\n".join(appended_nodes))
    return "\n\n".join(part for part in rendered_parts if part) + "\n"


def _is_source_file_function_like(node: object, source_path: Path) -> bool:
    coord = getattr(node, "coord", None)
    if str(getattr(coord, "file", "")) != str(source_path):
        return False
    return isinstance(node, FuncDef) or (
        isinstance(node, Decl) and isinstance(node.type, FuncDecl)
    )


def _is_generated_top_level_node(node: object) -> bool:
    coord = getattr(node, "coord", None)
    return isinstance(node, Node) and getattr(coord, "file", None) in (None, "")


def _function_like_span(source_text: str, node: FuncDef | Decl) -> _SourceSpan:
    coord = getattr(node, "coord", None)
    if coord is None:
        raise ValueError("Expected source-backed function node to have coordinates.")

    start = _find_function_like_start(source_text, coord.line)
    if isinstance(node, FuncDef):
        end = _find_matching_brace(
            source_text,
            _find_block_start(source_text, start),
        ) + 1
        return _SourceSpan(start=start, end=end)

    end = _find_declaration_terminator(source_text, start) + 1
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


def _find_function_like_start(source_text: str, line: int) -> int:
    start_line = line

    # Function coordinates often point at the function name. Walk upward over
    # signature-continuation lines (for example `static int` above `main(...)`)
    # but stop before comments, blank lines, or previous top-level constructs.
    while start_line > 1:
        previous_line = _source_line(source_text, start_line - 1).strip()
        if not previous_line:
            break
        if previous_line.startswith(("//", "/*", "*", "#")):
            break
        if previous_line.endswith((";", "}", "{")):
            break
        start_line -= 1

    return _line_col_to_offset(source_text, start_line, 1)


def _source_line(source_text: str, line: int) -> str:
    current_line = 1
    offset = 0
    while current_line < line:
        next_newline = source_text.find("\n", offset)
        if next_newline == -1:
            return ""
        offset = next_newline + 1
        current_line += 1

    next_newline = source_text.find("\n", offset)
    if next_newline == -1:
        return source_text[offset:]
    return source_text[offset:next_newline]


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


def _find_block_start(source_text: str, start_offset: int) -> int:
    index = start_offset
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
            return index

        index += 1

    raise ValueError("Unable to locate the start of the function body.")


def _find_declaration_terminator(source_text: str, start_offset: int) -> int:
    index = start_offset
    in_string = False
    in_char = False
    in_line_comment = False
    in_block_comment = False
    escaping = False
    paren_depth = 0

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

        if char == "(":
            paren_depth += 1
        elif char == ")":
            paren_depth = max(0, paren_depth - 1)
        elif char == ";" and paren_depth == 0:
            return index

        index += 1

    raise ValueError("Unable to locate the end of the declaration.")
