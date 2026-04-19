from dataclasses import dataclass
from pathlib import Path

from pycparser import c_generator
from pycparser.c_ast import Decl, FileAST, FuncDecl, FuncDef, Node

_KLEE_DECLARATIONS = (
    (
        "snprintf",
        "extern int snprintf(char *str, unsigned long size, const char *format, ...);",
    ),
    (
        "klee_make_symbolic",
        "extern void klee_make_symbolic(void *addr, unsigned long nbytes, const char *name);",
    ),
    ("klee_assume", "extern void klee_assume(int condition);"),
    ("klee_assert", "extern void klee_assert(int condition);"),
)
_KLEE_HELPERS = """static char *__eclipse_int_to_string(int value, char *buffer, int buffer_size)
{
  snprintf(buffer, buffer_size, "%d", value);
  return buffer;
}
"""


@dataclass(frozen=True)
class _SourceSpan:
    """A half-open character span inside the original source text.

    The renderer works by replacing exact text slices from the original file
    rather than regenerating the entire translation unit. Each `_SourceSpan`
    tells us which region of the source should be replaced by regenerated code
    from the transformed AST.
    """

    start: int
    end: int


def render_processed_source(file_path: str | Path, ast: FileAST) -> str:
    """Render AST changes while preserving the original source text around them.

    This module deliberately does *not* emit the whole file from `pycparser`'s
    code generator. Doing that would lose too much original source structure:

    - comments
    - include directives
    - macro layout
    - formatting and other preprocessor-adjacent details

    Instead, the renderer uses a source-preserving strategy:

    1. read the original file text
    2. find the source spans corresponding to function definitions and function
       declarations that came from that file
    3. regenerate only those AST nodes as C text
    4. splice those regenerated snippets back into the original source
    5. append generated top-level nodes, such as the synthetic CLI harness

    This works well because the current preprocessing passes only change
    function-level code and append a small amount of generated top-level code.
    The surrounding translation unit can therefore remain exactly as-authored.
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
            replacements.append((span, _render_function_like_node(generator, node)))
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

    rendered_parts = [_build_klee_preamble(ast, source_path), rewritten_source.rstrip()]
    if appended_nodes:
        rendered_parts.append("\n\n".join(appended_nodes))
    return "\n\n".join(part for part in rendered_parts if part) + "\n"


def _build_klee_preamble(ast: FileAST, source_path: Path) -> str:
    """Build the helper preamble while avoiding duplicate source declarations."""

    declared_names = {
        _function_like_name(node)
        for node in ast.ext
        if _is_source_file_function_like(node, source_path)
    }
    declarations = [
        declaration
        for name, declaration in _KLEE_DECLARATIONS
        if name not in declared_names
    ]
    return "\n".join([*declarations, "", _KLEE_HELPERS]).strip() + "\n"


def _is_source_file_function_like(node: object, source_path: Path) -> bool:
    """Return whether a node is a source-backed function def/decl from this file."""

    coord = getattr(node, "coord", None)
    if str(getattr(coord, "file", "")) != str(source_path):
        return False
    return isinstance(node, FuncDef) or (
        isinstance(node, Decl) and isinstance(node.type, FuncDecl)
    )


def _is_generated_top_level_node(node: object) -> bool:
    """Return whether a top-level AST node was synthesized rather than parsed.

    Generated nodes such as the CLI harness have no meaningful source file
    coordinates, so the renderer cannot splice them back into an existing text
    span. Instead, these nodes are appended after the preserved source.
    """

    coord = getattr(node, "coord", None)
    return isinstance(node, Node) and getattr(coord, "file", None) in (None, "")


def _function_like_name(node: FuncDef | Decl) -> str:
    """Return the declared function name for a function definition/prototype."""

    if isinstance(node, FuncDef):
        return node.decl.name
    return node.name


def _render_function_like_node(
    generator: c_generator.CGenerator, node: FuncDef | Decl
) -> str:
    """Render a function definition/prototype with the source-compatible suffix."""

    rendered = generator.visit(node)
    if isinstance(node, Decl) and isinstance(node.type, FuncDecl):
        return rendered + ";"
    return rendered


def _function_like_span(source_text: str, node: FuncDef | Decl) -> _SourceSpan:
    """Compute the exact source span occupied by a function def/decl node."""

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
    """Convert a 1-based line/column pair into a character offset."""

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
    """Walk upward to find the true start of a function signature.

    `pycparser` coordinates often point at the function name itself rather than
    the first line of the full signature. For example, a function written as:

    ```c
    static int
    main(...)
    ```

    may report a coordinate on the `main` line. This helper walks upward across
    signature-continuation lines until it reaches the actual beginning of the
    declaration.
    """

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
    """Return a single source line by 1-based index, without the trailing newline."""

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
    """Find the closing brace that matches the block starting at `brace_offset`.

    The scan is string/comment aware, so braces inside comments or literals do
    not interfere with finding the end of the function body.
    """

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
    """Find the first opening brace for a function definition starting at `start_offset`."""

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
    """Find the terminating semicolon for a function declaration span.

    The scan ignores semicolons that appear inside comments, strings, character
    literals, or nested parameter syntax.
    """

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
