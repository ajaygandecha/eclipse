from copy import deepcopy
from typing import Optional

from pycparser.c_ast import (
    ArrayRef,
    Assignment,
    BinaryOp,
    Break,
    Case,
    Cast,
    Compound,
    Constant,
    Continue,
    Decl,
    DeclList,
    Default,
    ExprList,
    FileAST,
    For,
    FuncCall,
    FuncDef,
    ID,
    IdentifierType,
    If,
    Label,
    Node,
    Return,
    StructRef,
    Switch,
    TernaryOp,
    TypeDecl,
    UnaryOp,
    While,
)

GPIO_READ_FUNCTIONS = {"gpiod_line_get_value", "gpiod_line_request_get_value"}

EXPRESSION_STATEMENT_TYPES = (
    ArrayRef,
    Assignment,
    BinaryOp,
    Cast,
    Constant,
    ExprList,
    FuncCall,
    ID,
    StructRef,
    TernaryOp,
    UnaryOp,
)


class GPIOConstraintVisitor:
    """Visits AST nodes and replaces supported GPIO reads with symbolic values."""

    def __init__(self) -> None:
        self.gpio_counter_index = 0

    def visit(self, ast: FileAST) -> FileAST:
        rewritten_ext = []
        for node in ast.ext:
            rewritten_ext.extend(self._rewrite_statement(node))
        ast.ext = rewritten_ext
        return ast

    def _rewrite_statement(self, stmt: Optional[Node]) -> list[Node]:
        if stmt is None:
            return []

        if isinstance(stmt, Compound):
            stmt.block_items = self._rewrite_block_items(stmt.block_items)
            return [stmt]

        if isinstance(stmt, FuncDef):
            stmt.body = self._wrap_statements(self._rewrite_statement(stmt.body))
            return [stmt]

        if isinstance(stmt, If):
            return self._rewrite_if(stmt)

        if isinstance(stmt, While):
            return self._rewrite_while(stmt)

        if isinstance(stmt, For):
            return self._rewrite_for(stmt)

        if isinstance(stmt, Switch):
            prefix_nodes, stmt.cond = self._rewrite_expression(stmt.cond)
            stmt.stmt = self._wrap_statements(self._rewrite_statement(stmt.stmt))
            return prefix_nodes + [stmt]

        if isinstance(stmt, Label):
            stmt.stmt = self._wrap_statements(self._rewrite_statement(stmt.stmt))
            return [stmt]

        if isinstance(stmt, (Case, Default)):
            stmt.stmts = self._rewrite_block_items(stmt.stmts)
            return [stmt]

        if isinstance(stmt, Decl):
            prefix_nodes, stmt.init = self._rewrite_expression(stmt.init)
            return prefix_nodes + [stmt]

        if isinstance(stmt, Return):
            prefix_nodes, stmt.expr = self._rewrite_expression(stmt.expr)
            return prefix_nodes + [stmt]

        if isinstance(stmt, EXPRESSION_STATEMENT_TYPES):
            prefix_nodes, rewritten_expr = self._rewrite_expression(stmt)
            return prefix_nodes + self._optional_node(rewritten_expr)

        return [stmt]

    def _rewrite_if(self, stmt: If) -> list[Node]:
        prefix_nodes, stmt.cond = self._rewrite_expression(stmt.cond)
        stmt.iftrue = self._wrap_statements(self._rewrite_statement(stmt.iftrue))
        if stmt.iffalse is not None:
            stmt.iffalse = self._wrap_statements(self._rewrite_statement(stmt.iffalse))
        return prefix_nodes + [stmt]

    def _rewrite_while(self, stmt: While) -> list[Node]:
        cond_prefix, stmt.cond = self._rewrite_expression(stmt.cond)
        stmt.stmt = self._wrap_statements(self._rewrite_statement(stmt.stmt))

        if not cond_prefix:
            return [stmt]

        loop_body = list(cond_prefix)
        loop_body.append(self._make_break_if_false(stmt.cond))
        loop_body.extend(self._as_block_items(stmt.stmt))

        return [While(cond=self._true_constant(), stmt=Compound(block_items=loop_body))]

    def _rewrite_for(self, stmt: For) -> list[Node]:
        init_prefix, stmt.init = self._rewrite_for_init(stmt.init)
        cond_prefix, stmt.cond = self._rewrite_expression(stmt.cond)
        next_prefix, stmt.next = self._rewrite_expression(stmt.next)
        stmt.stmt = self._wrap_statements(self._rewrite_statement(stmt.stmt))

        if not cond_prefix and not next_prefix:
            return init_prefix + [stmt]

        loop_tail = list(next_prefix)
        if stmt.next is not None:
            loop_tail.append(stmt.next)

        stmt.stmt = self._inject_before_continue(stmt.stmt, loop_tail)

        loop_body = list(cond_prefix)
        if stmt.cond is not None:
            loop_body.append(self._make_break_if_false(stmt.cond))
        loop_body.extend(self._as_block_items(stmt.stmt))
        loop_body.extend(self._clone_nodes(loop_tail))

        lowered_loop = [*init_prefix, *self._for_init_to_statements(stmt.init)]
        lowered_loop.append(
            While(cond=self._true_constant(), stmt=Compound(block_items=loop_body))
        )
        return [Compound(block_items=lowered_loop)]

    def _rewrite_block_items(
        self, block_items: Optional[list[Node]]
    ) -> Optional[list[Node]]:
        if not block_items:
            return block_items

        rewritten_items = []
        for item in block_items:
            rewritten_items.extend(self._rewrite_statement(item))
        return rewritten_items

    def _rewrite_for_init(self, init: Optional[Node]) -> tuple[list[Node], Optional[Node]]:
        if init is None:
            return [], init

        if isinstance(init, DeclList):
            prefix_nodes = []
            for decl in init.decls:
                decl_prefix, decl.init = self._rewrite_expression(decl.init)
                prefix_nodes.extend(decl_prefix)
            return prefix_nodes, init

        return self._rewrite_expression(init)

    def _rewrite_expression(self, expr: Optional[Node]) -> tuple[list[Node], Optional[Node]]:
        if expr is None:
            return [], expr

        if self._is_gpio_read(expr):
            return self._replace_gpio_read()

        if isinstance(expr, BinaryOp):
            return self._rewrite_binary_op(expr)

        if isinstance(expr, UnaryOp):
            prefix_nodes, expr.expr = self._rewrite_expression(expr.expr)
            return prefix_nodes, expr

        if isinstance(expr, Cast):
            prefix_nodes, expr.expr = self._rewrite_expression(expr.expr)
            return prefix_nodes, expr

        if isinstance(expr, TernaryOp):
            return self._rewrite_ternary_op(expr)

        if isinstance(expr, ArrayRef):
            name_prefix, expr.name = self._rewrite_expression(expr.name)
            subscript_prefix, expr.subscript = self._rewrite_expression(expr.subscript)
            return name_prefix + subscript_prefix, expr

        if isinstance(expr, StructRef):
            name_prefix, expr.name = self._rewrite_expression(expr.name)
            field_prefix, expr.field = self._rewrite_expression(expr.field)
            return name_prefix + field_prefix, expr

        if isinstance(expr, Assignment):
            lvalue_prefix, expr.lvalue = self._rewrite_expression(expr.lvalue)
            rvalue_prefix, expr.rvalue = self._rewrite_expression(expr.rvalue)
            return lvalue_prefix + rvalue_prefix, expr

        if isinstance(expr, FuncCall):
            name_prefix, expr.name = self._rewrite_expression(expr.name)
            arg_prefix, expr.args = self._rewrite_expr_list(expr.args)
            return name_prefix + arg_prefix, expr

        if isinstance(expr, ExprList):
            return self._rewrite_expr_list(expr)

        return [], expr

    def _rewrite_binary_op(self, expr: BinaryOp) -> tuple[list[Node], BinaryOp]:
        left_prefix, expr.left = self._rewrite_expression(expr.left)
        right_prefix, expr.right = self._rewrite_expression(expr.right)
        return left_prefix + right_prefix, expr

    def _rewrite_ternary_op(self, expr: TernaryOp) -> tuple[list[Node], TernaryOp]:
        cond_prefix, expr.cond = self._rewrite_expression(expr.cond)
        iftrue_prefix, expr.iftrue = self._rewrite_expression(expr.iftrue)
        iffalse_prefix, expr.iffalse = self._rewrite_expression(expr.iffalse)
        return cond_prefix + iftrue_prefix + iffalse_prefix, expr

    def _rewrite_expr_list(
        self, expr_list: Optional[ExprList]
    ) -> tuple[list[Node], Optional[ExprList]]:
        if expr_list is None:
            return [], expr_list

        prefix_nodes = []
        rewritten_exprs = []
        for expr in expr_list.exprs:
            expr_prefix, rewritten_expr = self._rewrite_expression(expr)
            prefix_nodes.extend(expr_prefix)
            rewritten_exprs.append(rewritten_expr)
        expr_list.exprs = rewritten_exprs
        return prefix_nodes, expr_list

    def _replace_gpio_read(self) -> tuple[list[Node], ID]:
        symbol_name = self._next_symbol_name()
        return self._make_symbolic_prefix(symbol_name), ID(name=symbol_name)

    def _next_symbol_name(self) -> str:
        symbol_name = f"__eclipse_gpio_value_{self.gpio_counter_index}"
        self.gpio_counter_index += 1
        return symbol_name

    def _is_gpio_read(self, expr: Node) -> bool:
        return (
            isinstance(expr, FuncCall)
            and isinstance(expr.name, ID)
            and expr.name.name in GPIO_READ_FUNCTIONS
        )

    def _make_symbolic_prefix(self, symbol_name: str) -> list[Node]:
        return [
            self._make_symbol_decl(symbol_name),
            self._make_symbolic_call(symbol_name),
            self._make_assume_call(symbol_name),
        ]

    def _make_symbol_decl(self, symbol_name: str) -> Decl:
        return Decl(
            name=symbol_name,
            quals=[],
            align=[],
            storage=[],
            funcspec=[],
            type=TypeDecl(
                declname=symbol_name,
                quals=[],
                align=None,
                type=IdentifierType(names=["int"]),
            ),
            init=None,
            bitsize=None,
        )

    def _make_symbolic_call(self, symbol_name: str) -> FuncCall:
        return FuncCall(
            name=ID(name="klee_make_symbolic"),
            args=ExprList(
                exprs=[
                    UnaryOp(op="&", expr=ID(name=symbol_name)),
                    UnaryOp(op="sizeof", expr=ID(name=symbol_name)),
                    Constant(type="string", value=f'"{symbol_name}"'),
                ]
            ),
        )

    def _make_assume_call(self, symbol_name: str) -> FuncCall:
        is_zero = BinaryOp(
            op="==",
            left=ID(name=symbol_name),
            right=Constant(type="int", value="0"),
        )
        is_one = BinaryOp(
            op="==",
            left=ID(name=symbol_name),
            right=Constant(type="int", value="1"),
        )
        return FuncCall(
            name=ID(name="klee_assume"),
            args=ExprList(exprs=[BinaryOp(op="||", left=is_zero, right=is_one)]),
        )

    def _make_break_if_false(self, condition: Node) -> If:
        return If(cond=UnaryOp(op="!", expr=condition), iftrue=Break(), iffalse=None)

    def _inject_before_continue(self, stmt: Optional[Node], tail_nodes: list[Node]) -> Optional[Node]:
        if stmt is None or not tail_nodes:
            return stmt

        if isinstance(stmt, Compound):
            stmt.block_items = self._inject_tail_before_continue_in_block(
                stmt.block_items, tail_nodes
            )
            return stmt

        if isinstance(stmt, Continue):
            return Compound(block_items=self._clone_nodes(tail_nodes) + [stmt])

        if isinstance(stmt, If):
            stmt.iftrue = self._inject_before_continue(stmt.iftrue, tail_nodes)
            stmt.iffalse = self._inject_before_continue(stmt.iffalse, tail_nodes)
            return stmt

        if isinstance(stmt, Switch):
            stmt.stmt = self._inject_before_continue(stmt.stmt, tail_nodes)
            return stmt

        if isinstance(stmt, Label):
            stmt.stmt = self._inject_before_continue(stmt.stmt, tail_nodes)
            return stmt

        if isinstance(stmt, (Case, Default)):
            stmt.stmts = self._inject_tail_before_continue_in_block(stmt.stmts, tail_nodes)
            return stmt

        if isinstance(stmt, (While, For)):
            return stmt

        return stmt

    def _inject_tail_before_continue_in_block(
        self, block_items: Optional[list[Node]], tail_nodes: list[Node]
    ) -> Optional[list[Node]]:
        if not block_items:
            return block_items

        rewritten_items = []
        for item in block_items:
            rewritten_item = self._inject_before_continue(item, tail_nodes)
            if rewritten_item is not None:
                rewritten_items.append(rewritten_item)
        return rewritten_items

    def _wrap_statements(self, nodes: list[Node]) -> Node:
        if not nodes:
            return Compound(block_items=[])
        if len(nodes) == 1:
            return nodes[0]
        return Compound(block_items=nodes)

    def _as_block_items(self, stmt: Optional[Node]) -> list[Node]:
        if stmt is None:
            return []
        if isinstance(stmt, Compound):
            return stmt.block_items or []
        return [stmt]

    def _for_init_to_statements(self, init: Optional[Node]) -> list[Node]:
        if init is None:
            return []
        if isinstance(init, DeclList):
            return list(init.decls)
        return [init]

    def _clone_nodes(self, nodes: list[Node]) -> list[Node]:
        return [deepcopy(node) for node in nodes]

    def _optional_node(self, node: Optional[Node]) -> list[Node]:
        return [node] if node is not None else []

    def _true_constant(self) -> Constant:
        return Constant(type="int", value="1")


def add_gpio_constraints(ast: FileAST) -> FileAST:
    """Rewrite supported GPIO reads into constrained symbolic values."""
    return GPIOConstraintVisitor().visit(ast)
