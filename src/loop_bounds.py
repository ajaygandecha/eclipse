from typing import Optional

from pycparser.c_ast import (
    BinaryOp,
    Case,
    Compound,
    Constant,
    Decl,
    Default,
    FileAST,
    For,
    FuncDef,
    ID,
    IdentifierType,
    If,
    Label,
    Node,
    Switch,
    TypeDecl,
    UnaryOp,
    While,
)

MAX_ITERATIONS = 10


class LoopBoundsVisitor:
    """Rewrite loops so every `while`/`for` has an explicit iteration cap.

    The visitor walks statement structure recursively. Whenever it finds a loop,
    it injects:

    - a fresh counter declaration before the loop
    - an additional `counter < max_iterations` guard in the loop condition
    - a counter increment at the end of the loop body

    This keeps the transformed program structurally close to the original one
    while ensuring symbolic execution does not wander into unbounded iteration.
    """

    def __init__(self, max_iterations: int = MAX_ITERATIONS):
        self.max_iterations = max_iterations
        self.loop_counter_index = 0

    def visit(self, ast: FileAST) -> FileAST:
        """Rewrite each top-level statement/function in the translation unit."""

        ast.ext = [self._visit_statement(node) for node in ast.ext]
        return ast

    def _next_counter_name(self) -> str:
        counter_name = f"__eclipse_loop_bound_{self.loop_counter_index}"
        self.loop_counter_index += 1
        return counter_name

    def _make_loop_counter_decl(self, counter_name: str) -> Decl:
        return Decl(
            name=counter_name,
            quals=[],
            align=[],
            storage=[],
            funcspec=[],
            type=TypeDecl(
                declname=counter_name,
                quals=[],
                align=None,
                type=IdentifierType(names=["int"]),
            ),
            init=Constant(type="int", value="0"),
            bitsize=None,
        )

    def _make_bound_expr(self, counter_name: str) -> BinaryOp:
        return BinaryOp(
            op="<",
            left=ID(name=counter_name),
            right=Constant(type="int", value=str(self.max_iterations)),
        )

    def _make_counter_increment(self, counter_name: str) -> UnaryOp:
        return UnaryOp(op="p++", expr=ID(name=counter_name))

    def _ensure_compound(self, stmt: Optional[Node]) -> Compound:
        if isinstance(stmt, Compound):
            stmt.block_items = stmt.block_items or []
            return stmt
        return Compound(block_items=[stmt] if stmt is not None else [])

    def _rewrite_loop_condition(self, loop_node: While | For, counter_name: str) -> None:
        bound_expr = self._make_bound_expr(counter_name)
        if isinstance(loop_node, While):
            loop_node.cond = BinaryOp(op="&&", left=loop_node.cond, right=bound_expr)
            return

        if loop_node.cond is None:
            loop_node.cond = bound_expr
        else:
            loop_node.cond = BinaryOp(op="&&", left=loop_node.cond, right=bound_expr)

    def _visit_loop(self, loop_node: While | For) -> tuple[Decl, While | For]:
        """Rewrite one loop and return the counter declaration plus new loop node."""

        counter_name = self._next_counter_name()
        loop_node.stmt = self._visit_statement(loop_node.stmt)

        loop_body = self._ensure_compound(loop_node.stmt)
        loop_node.stmt = loop_body
        self._rewrite_loop_condition(loop_node, counter_name)
        loop_body.block_items.append(self._make_counter_increment(counter_name))

        return self._make_loop_counter_decl(counter_name), loop_node

    def _visit_block_items(
        self, block_items: Optional[list[Node]]
    ) -> Optional[list[Node]]:
        if not block_items:
            return block_items

        rewritten_items = []
        for item in block_items:
            rewritten_items.append(self._visit_statement(item))
        return rewritten_items

    def _visit_statement(self, stmt: Optional[Node]) -> Optional[Node]:
        """Recursively rewrite one statement subtree.

        Most statement kinds are traversed in place. Loops are the special case:
        they expand into a small compound block containing the fresh counter
        declaration followed by the rewritten loop itself.
        """

        if stmt is None:
            return stmt

        if isinstance(stmt, Compound):
            stmt.block_items = self._visit_block_items(stmt.block_items)
            return stmt

        if isinstance(stmt, If):
            stmt.iftrue = self._visit_statement(stmt.iftrue)
            stmt.iffalse = self._visit_statement(stmt.iffalse)
            return stmt

        if isinstance(stmt, FuncDef):
            stmt.body = self._visit_statement(stmt.body)
            return stmt

        if isinstance(stmt, (While, For)):
            counter_decl, loop_node = self._visit_loop(stmt)
            return Compound(block_items=[counter_decl, loop_node])

        if isinstance(stmt, Switch):
            stmt.stmt = self._visit_statement(stmt.stmt)
            return stmt

        if isinstance(stmt, Label):
            stmt.stmt = self._visit_statement(stmt.stmt)
            return stmt

        if isinstance(stmt, (Case, Default)):
            stmt.stmts = self._visit_block_items(stmt.stmts)
            return stmt

        return stmt


def add_loop_bounds(ast: FileAST) -> FileAST:
    """Apply the loop-bounding visitor to an entire translation unit."""
    return LoopBoundsVisitor(max_iterations=MAX_ITERATIONS).visit(ast)
