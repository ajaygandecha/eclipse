from __future__ import annotations

from pycparser import c_parser
from pycparser.c_ast import ArrayDecl, Decl, FileAST, FuncDecl, FuncDef, IdentifierType, PtrDecl, TypeDecl

from cli_config import CLIProgramSpec, OptionElement, OptionValueElement, PositionalElement, load_cli_config

HARNESS_MAIN_NAME = "main"
ORIGINAL_MAIN_NAME = "__eclipse_original_main"


class CodeWriter:
    """Small helper for readable generated C source."""

    def __init__(self) -> None:
        self._indent = 0
        self._lines: list[str] = []

    def line(self, text: str = "") -> None:
        self._lines.append(("  " * self._indent) + text)

    def blank(self) -> None:
        if self._lines and self._lines[-1] != "":
            self._lines.append("")

    def start_block(self, header: str) -> None:
        self.line(header)
        self.line("{")
        self._indent += 1

    def end_block(self) -> None:
        self._indent -= 1
        self.line("}")

    def trim_trailing_blank(self) -> None:
        while self._lines and self._lines[-1] == "":
            self._lines.pop()

    def render(self) -> str:
        return "\n".join(self._lines) + "\n"


class ArgumentConstraintVisitor:
    """Turn a program entrypoint into a symbolic CLI harness.

    This visitor performs the CLI transformation in three steps:

    1. validate that the original entrypoint has a supported signature
    2. rename that entrypoint to `__eclipse_original_main`
    3. append a newly generated `main` function that creates symbolic CLI input

    The resulting program keeps the original logic intact, but routes execution
    through a harness that constructs symbolic `argc`/`argv` according to the
    declarative YAML CLI specification.
    """

    def __init__(self, spec: CLIProgramSpec):
        self.spec = spec
        self.uses_argv = False

    def visit(self, ast: FileAST) -> FileAST:
        """Apply the full entrypoint-to-harness rewrite to a translation unit."""

        self._validate_original_name_is_available(ast)
        entrypoint = self._find_entrypoint_definition(ast)
        self._validate_entrypoint_signature(entrypoint)
        self._rename_entrypoint(ast)
        ast.ext.extend(self._parse_harness_source().ext)
        return ast

    def _validate_original_name_is_available(self, ast: FileAST) -> None:
        for node in ast.ext:
            if isinstance(node, FuncDef) and node.decl.name == ORIGINAL_MAIN_NAME:
                raise ValueError(
                    f"Input program already defines '{ORIGINAL_MAIN_NAME}'."
                )
            if (
                isinstance(node, Decl)
                and node.name == ORIGINAL_MAIN_NAME
                and isinstance(node.type, FuncDecl)
            ):
                raise ValueError(
                    f"Input program already declares '{ORIGINAL_MAIN_NAME}'."
                )

    def _find_entrypoint_definition(self, ast: FileAST) -> FuncDef:
        for node in ast.ext:
            if isinstance(node, FuncDef) and node.decl.name == self.spec.entry_point:
                return node
        raise ValueError(
            "Input program must define main(argc, argv) for CLI harness generation."
        )

    def _validate_entrypoint_signature(self, entrypoint: FuncDef) -> None:
        func_decl = entrypoint.decl.type
        if not isinstance(func_decl, FuncDecl):
            raise ValueError("Input main has an unsupported signature.")

        return_type = func_decl.type
        if not (
            isinstance(return_type, TypeDecl)
            and isinstance(return_type.type, IdentifierType)
            and tuple(return_type.type.names) == ("int",)
        ):
            raise ValueError("Input main must return int.")

        params = func_decl.args.params if func_decl.args is not None else []
        if not params:
            self.uses_argv = False
            return

        if len(params) != 2:
            raise ValueError(
                "Input main must have the signature int main() or "
                "int main(int argc, char **argv)."
            )

        argc_param, argv_param = params
        if not self._is_int_param(argc_param):
            raise ValueError("Input main must take int argc as its first parameter.")
        if not self._is_argv_param(argv_param):
            raise ValueError(
                "Input main must take char **argv or char *argv[] as its second parameter."
            )
        self.uses_argv = True

    def _is_int_param(self, param: object) -> bool:
        return (
            isinstance(param, Decl)
            and isinstance(param.type, TypeDecl)
            and isinstance(param.type.type, IdentifierType)
            and tuple(param.type.type.names) == ("int",)
        )

    def _is_argv_param(self, param: object) -> bool:
        if not isinstance(param, Decl):
            return False

        type_node = param.type
        if isinstance(type_node, PtrDecl):
            return (
                isinstance(type_node.type, PtrDecl)
                and isinstance(type_node.type.type, TypeDecl)
                and isinstance(type_node.type.type.type, IdentifierType)
                and tuple(type_node.type.type.type.names) == ("char",)
            )

        if isinstance(type_node, ArrayDecl):
            return (
                isinstance(type_node.type, PtrDecl)
                and isinstance(type_node.type.type, TypeDecl)
                and isinstance(type_node.type.type.type, IdentifierType)
                and tuple(type_node.type.type.type.names) == ("char",)
            )

        return False

    def _rename_entrypoint(self, ast: FileAST) -> None:
        for node in ast.ext:
            if isinstance(node, FuncDef) and node.decl.name == self.spec.entry_point:
                self._rename_decl(node.decl, ORIGINAL_MAIN_NAME)
            elif (
                isinstance(node, Decl)
                and node.name == self.spec.entry_point
                and isinstance(node.type, FuncDecl)
            ):
                self._rename_decl(node, ORIGINAL_MAIN_NAME)

    def _rename_decl(self, decl: Decl, new_name: str) -> None:
        decl.name = new_name
        type_node = decl.type
        while hasattr(type_node, "type") and not isinstance(type_node, TypeDecl):
            type_node = type_node.type
        if isinstance(type_node, TypeDecl):
            type_node.declname = new_name

    def _parse_harness_source(self) -> FileAST:
        parser = c_parser.CParser()
        return parser.parse(HarnessSourceBuilder(self.spec, self.uses_argv).build())


class HarnessSourceBuilder:
    """Generate readable C for the synthetic symbolic CLI harness.

    The builder mirrors the structure of the CLI config:

    - options become presence booleans and optional spelling selectors
    - integer-valued arguments become symbolic ints plus range checks
    - string-like arguments become symbolic buffers plus length/null checks
    - the final `argv` array is assembled in the declared element order

    The emitted harness ends by calling `__eclipse_original_main(...)`, so the
    original program logic runs unchanged once symbolic inputs have been set up.
    """

    def __init__(self, spec: CLIProgramSpec, uses_argv: bool):
        self.spec = spec
        self.uses_argv = uses_argv
        self.writer = CodeWriter()
        self.option_lookup = {
            element.id: element
            for element in spec.elements
            if isinstance(element, OptionElement)
        }

    def build(self) -> str:
        """Render the full synthetic `main` function as C source."""

        self.writer.start_block("int main(void)")
        if self.uses_argv:
            self.writer.line("int __eclipse_argc = 1;")
            self.writer.line(f"char *__eclipse_argv[{self._max_argv_slots() + 1}];")
            self.writer.line(f"__eclipse_argv[0] = {self._c_string(self.spec.argv0)};")

        if self.spec.elements and self.uses_argv:
            self.writer.blank()
            self._emit_symbolic_setup()
            self.writer.blank()
            self._emit_argv_construction()

        self.writer.blank()
        if self.uses_argv:
            self.writer.line("__eclipse_argv[__eclipse_argc] = 0;")
            self.writer.line(
                f"return {ORIGINAL_MAIN_NAME}(__eclipse_argc, __eclipse_argv);"
            )
        else:
            self.writer.line(f"return {ORIGINAL_MAIN_NAME}();")
        self.writer.end_block()
        return self.writer.render()

    def _emit_symbolic_setup(self) -> None:
        for index, element in enumerate(self.spec.elements):
            self._emit_element_setup(element)
            if index != len(self.spec.elements) - 1:
                self.writer.blank()
        self.writer.trim_trailing_blank()

    def _emit_element_setup(
        self, element: OptionElement | OptionValueElement | PositionalElement
    ) -> None:
        if isinstance(element, OptionElement):
            self._emit_option_setup(element)
            return
        if isinstance(element, OptionValueElement):
            self._emit_option_value_setup(element)
            return
        self._emit_positional_setup(element)

    def _emit_option_setup(self, element: OptionElement) -> None:
        if element.optional:
            self._emit_symbolic_boolean(
                self._presence_var(element.id),
                f"{element.id}_present",
            )

        if len(element.spellings) > 1:
            selector = self._spelling_selector_var(element.id)
            self.writer.line(f"int {selector};")
            self._emit_symbolic_integer(selector, f"{element.id}_spelling")
            self.writer.line(
                self._assume(self._range_expr(selector, 0, len(element.spellings) - 1))
            )

    def _emit_option_value_setup(self, element: OptionValueElement) -> None:
        if element.optional:
            self._emit_symbolic_boolean(
                self._presence_var(element.id),
                f"{element.id}_present",
            )

        if element.value_kind == "int":
            value_var = self._int_value_var(element.id)
            self.writer.line(f"int {value_var};")
            self._emit_symbolic_integer(value_var, element.id)
            self.writer.line(
                self._assume(self._range_expr(value_var, element.min, element.max))
            )
            self.writer.line(
                f"char {self._int_buffer_var(element.id)}[{self._int_buffer_size(element.min, element.max)}];"
            )
            return

        self._emit_string_storage(
            buffer_name=self._string_buffer_var(element.id),
            length_name=self._length_var(element.id),
            min_length=element.min,
            max_length=element.max,
            label=element.id,
        )

    def _emit_positional_setup(self, element: PositionalElement) -> None:
        if element.optional:
            self._emit_symbolic_boolean(
                self._presence_var(element.id),
                f"{element.id}_present",
            )

        self._emit_string_storage(
            buffer_name=self._string_buffer_var(element.id),
            length_name=self._length_var(element.id),
            min_length=element.min_length,
            max_length=element.max_length,
            label=element.id,
        )

    def _emit_string_storage(
        self,
        buffer_name: str,
        length_name: str,
        min_length: int,
        max_length: int,
        label: str,
    ) -> None:
        self.writer.line(f"int {length_name};")
        self._emit_symbolic_integer(length_name, f"{label}_length")
        self.writer.line(
            self._assume(self._range_expr(length_name, min_length, max_length))
        )
        self.writer.line(f"char {buffer_name}[{max_length + 1}];")
        self.writer.line(
            f"klee_make_symbolic({buffer_name}, sizeof({buffer_name}), {self._c_string(label)});"
        )
        self.writer.line(self._assume(f"{buffer_name}[{length_name}] == '\\0'"))
        for index in range(max_length):
            self.writer.line(
                self._assume(
                    f"(({length_name} <= {index}) || ({buffer_name}[{index}] != '\\0'))"
                )
            )

    def _emit_symbolic_boolean(self, variable_name: str, label: str) -> None:
        self.writer.line(f"int {variable_name};")
        self._emit_symbolic_integer(variable_name, label)
        self.writer.line(
            self._assume(f"(({variable_name} == 0) || ({variable_name} == 1))")
        )

    def _emit_symbolic_integer(self, variable_name: str, label: str) -> None:
        self.writer.line(
            f"klee_make_symbolic(&{variable_name}, sizeof({variable_name}), {self._c_string(label)});"
        )

    def _emit_argv_construction(self) -> None:
        for element in self.spec.elements:
            if isinstance(element, OptionElement):
                self._emit_option_into_argv(element)
            elif isinstance(element, OptionValueElement):
                self._emit_option_value_into_argv(element)
            else:
                self._emit_positional_into_argv(element)

    def _emit_option_into_argv(self, element: OptionElement) -> None:
        presence_expr = self._presence_expr(element.id, element.optional)
        if presence_expr == "1":
            self._emit_option_token(element)
            return

        self.writer.start_block(f"if ({presence_expr})")
        self._emit_option_token(element)
        self.writer.end_block()

    def _emit_option_token(self, element: OptionElement) -> None:
        if len(element.spellings) == 1:
            self._append_argv_item(self._c_string(element.spellings[0]))
            return

        selector = self._spelling_selector_var(element.id)
        for index, spelling in enumerate(element.spellings):
            self.writer.start_block(f"if ({selector} == {index})")
            self._append_argv_item(self._c_string(spelling))
            self.writer.end_block()

    def _emit_option_value_into_argv(self, element: OptionValueElement) -> None:
        guard_parts = [
            self._presence_expr(
                element.parent,
                self.option_lookup[element.parent].optional,
            )
        ]
        if element.optional:
            guard_parts.append(self._presence_var(element.id))

        guard_expr = " && ".join(f"({part})" for part in guard_parts if part != "1")
        if not guard_expr:
            self._append_option_value_token(element)
            return

        self.writer.start_block(f"if ({guard_expr})")
        self._append_option_value_token(element)
        self.writer.end_block()

    def _append_option_value_token(self, element: OptionValueElement) -> None:
        if element.value_kind == "int":
            self._append_argv_item(
                "__eclipse_int_to_string("
                f"{self._int_value_var(element.id)}, "
                f"{self._int_buffer_var(element.id)}, "
                f"sizeof({self._int_buffer_var(element.id)}))"
            )
            return

        self._append_argv_item(self._string_buffer_var(element.id))

    def _emit_positional_into_argv(self, element: PositionalElement) -> None:
        presence_expr = self._presence_expr(element.id, element.optional)
        if presence_expr == "1":
            self._append_argv_item(self._string_buffer_var(element.id))
            return

        self.writer.start_block(f"if ({presence_expr})")
        self._append_argv_item(self._string_buffer_var(element.id))
        self.writer.end_block()

    def _append_argv_item(self, expr: str) -> None:
        self.writer.line(f"__eclipse_argv[__eclipse_argc] = {expr};")
        self.writer.line("__eclipse_argc++;")

    def _presence_expr(self, element_id: str, optional: bool) -> str:
        if optional:
            return self._presence_var(element_id)
        return "1"

    def _presence_var(self, element_id: str) -> str:
        return f"__eclipse_use_{element_id}"

    def _spelling_selector_var(self, element_id: str) -> str:
        return f"__eclipse_{element_id}_spelling"

    def _length_var(self, element_id: str) -> str:
        return f"__eclipse_{element_id}_length"

    def _string_buffer_var(self, element_id: str) -> str:
        return f"sym_{element_id}"

    def _int_value_var(self, element_id: str) -> str:
        return f"sym_{element_id}"

    def _int_buffer_var(self, element_id: str) -> str:
        return f"__eclipse_{element_id}_value"

    def _max_argv_slots(self) -> int:
        return 1 + len(self.spec.elements)

    def _int_buffer_size(self, min_value: int, max_value: int) -> int:
        return max(len(str(min_value)), len(str(max_value))) + 1

    def _assume(self, expr: str) -> str:
        return f"klee_assume({expr});"

    def _range_expr(self, variable_name: str, min_value: int, max_value: int) -> str:
        return f"(({variable_name} >= {min_value}) && ({variable_name} <= {max_value}))"

    def _c_string(self, value: str) -> str:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'


def add_argument_constraints(ast: FileAST, config_path: str) -> FileAST:
    """Load the CLI spec and apply the argument-constraint visitor."""

    return ArgumentConstraintVisitor(load_cli_config(config_path)).visit(ast)


def build_cli_harness_source(spec: CLIProgramSpec, uses_argv: bool) -> str:
    """Render harness source for a validated CLI spec without mutating an AST."""

    return HarnessSourceBuilder(spec, uses_argv).build()
