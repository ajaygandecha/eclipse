import json
from dataclasses import dataclass
from pathlib import Path

from pycparser.c_ast import (
    ArrayRef,
    Assignment,
    BinaryOp,
    Cast,
    Constant,
    Decl,
    FileAST,
    FuncCall,
    FuncDef,
    ID,
    Node,
    NodeVisitor,
    PtrDecl,
    UnaryOp,
)

_DANGEROUS_API_NAMES = {
    "gets",
    "memcpy",
    "memmove",
    "snprintf",
    "sprintf",
    "strcat",
    "strcpy",
    "strncpy",
}


@dataclass(frozen=True)
class GuidanceMetadata:
    """Structured guidance emitted for KLEE's guided-search mode.

    `risky_functions` is the ordered list of function names that the analysis
    considered interesting. `notes` explains why each function was flagged, so
    the JSON output is both machine-consumable and readable when debugging the
    analysis.
    """

    risky_functions: tuple[str, ...]
    notes: dict[str, tuple[str, ...]]
    analysis_version: int = 1


class _FunctionRiskVisitor(NodeVisitor):
    """Collect lightweight "risk" notes while walking a single function body.

    The goal is to identify functions that look more interesting than average for
    symbolic exploration, for example because they perform pointer arithmetic, write
    through derived pointers, or call string/memory APIs that are commonly involved
    in bugs.
    """

    def __init__(self) -> None:
        self.notes: list[str] = []
        self._pointer_arithmetic_targets: set[str] = set()

    def visit_Assignment(self, node: Assignment) -> None:
        if isinstance(node.lvalue, ID) and _is_pointer_arithmetic_expr(node.rvalue):
            self._pointer_arithmetic_targets.add(node.lvalue.name)

        if _is_non_constant_array_write(node):
            self._record("contains non-constant array index write")

        pointer_write_note = self._pointer_write_note(node)
        if pointer_write_note:
            self._record(pointer_write_note)

        self.generic_visit(node)

    def visit_Decl(self, node: Decl) -> None:
        if (
            node.name
            and isinstance(node.type, PtrDecl)
            and node.init is not None
            and _is_pointer_arithmetic_expr(node.init)
        ):
            self._pointer_arithmetic_targets.add(node.name)
        self.generic_visit(node)

    def visit_FuncCall(self, node: FuncCall) -> None:
        callee_name = _func_call_name(node)
        if callee_name in _DANGEROUS_API_NAMES:
            self._record(f"calls dangerous API '{callee_name}'")
        self.generic_visit(node)

    def _pointer_write_note(self, node: Assignment) -> str | None:
        target = _strip_casts(node.lvalue)
        if not isinstance(target, UnaryOp) or target.op != "*":
            return None

        dereferenced_expr = _strip_casts(target.expr)
        if _is_pointer_arithmetic_expr(dereferenced_expr):
            return "writes through pointer arithmetic"

        if isinstance(dereferenced_expr, ID):
            if dereferenced_expr.name in self._pointer_arithmetic_targets:
                return "writes through pointer derived from pointer arithmetic"

        return None

    def _record(self, note: str) -> None:
        if note not in self.notes:
            self.notes.append(note)


def find_risky_functions(ast: FileAST) -> GuidanceMetadata:
    """Analyze each function definition in an AST and summarize risky ones.

    The process is:

    1. iterate over top-level function definitions
    2. run `_FunctionRiskVisitor` on each function body
    3. keep only the functions for which the visitor recorded one or more notes
    4. package the final result as `GuidanceMetadata`

    This keeps the output small and focused on the parts of the program that
    are most likely to benefit from guided symbolic execution.
    """

    risky_functions: list[str] = []
    notes: dict[str, tuple[str, ...]] = {}

    for node in ast.ext:
        if not isinstance(node, FuncDef):
            continue
        function_name = node.decl.name
        if not function_name:
            continue

        visitor = _FunctionRiskVisitor()
        visitor.visit(node.body)
        if not visitor.notes:
            continue

        risky_functions.append(function_name)
        notes[function_name] = tuple(visitor.notes)

    return GuidanceMetadata(
        risky_functions=tuple(risky_functions),
        notes=notes,
    )


def write_guidance_file(
    output_path: str | Path,
    guidance: GuidanceMetadata,
) -> Path:
    """Serialize guidance metadata to the JSON format consumed by KLEE."""

    destination = Path(output_path).resolve()
    payload = {
        "analysis_version": guidance.analysis_version,
        "risky_functions": list(guidance.risky_functions),
        "notes": {name: list(reasons) for name, reasons in guidance.notes.items()},
    }
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return destination


def _func_call_name(node: FuncCall) -> str | None:
    """Extract a direct callee name from a call expression when possible."""

    callee = _strip_casts(node.name)
    if isinstance(callee, ID):
        return callee.name
    return None


def _is_non_constant_array_write(node: Assignment) -> bool:
    """Return whether an assignment writes through an array with symbolic indexing."""

    target = _strip_casts(node.lvalue)
    if not isinstance(target, ArrayRef):
        return False

    subscript = _strip_casts(target.subscript)
    return not isinstance(subscript, Constant)


def _is_pointer_arithmetic_expr(node: Node | None) -> bool:
    """Return whether an expression is a simple pointer-arithmetic operation."""

    expr = _strip_casts(node)
    return isinstance(expr, BinaryOp) and expr.op in {"+", "-"}


def _strip_casts(node: Node | None) -> Node | None:
    """Peel away nested cast nodes so the underlying expression can be inspected."""

    expr = node
    while isinstance(expr, Cast):
        expr = expr.expr
    return expr
