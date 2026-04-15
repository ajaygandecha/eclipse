from dataclasses import dataclass
from pathlib import Path

import yaml
from pycparser import c_parser
from pycparser.c_ast import ArrayDecl, Decl, FileAST, FuncDecl, FuncDef, IdentifierType, PtrDecl, TypeDecl

HARNESS_MAIN_NAME = "main"
ORIGINAL_MAIN_NAME = "__eclipse_original_main"
KLEE_PREAMBLE = """#include <klee/klee.h>
#include <stdio.h>

static char *__eclipse_int_to_string(int value, char *buffer, int buffer_size)
{
  snprintf(buffer, buffer_size, "%d", value);
  return buffer;
}

"""


@dataclass(frozen=True)
class DependencySpec:
    option_name: str
    choice_name: str | None = None


@dataclass(frozen=True)
class ValueSpec:
    kind: str
    min_value: int | None = None
    max_value: int | None = None
    max_length: int | None = None
    enum_values: tuple[str, ...] = ()


@dataclass(frozen=True)
class ChoiceSpec:
    name: str
    flag: str
    value: ValueSpec


@dataclass(frozen=True)
class OptionSpec:
    name: str
    kind: str
    required: bool
    flag: str | None = None
    value: ValueSpec | None = None
    choices: tuple[ChoiceSpec, ...] = ()
    requires: tuple[DependencySpec, ...] = ()
    excludes: tuple[str, ...] = ()


@dataclass(frozen=True)
class PositionalSpec:
    name: str
    kind: str
    min_count: int
    max_count: int
    max_length: int


@dataclass(frozen=True)
class CLIConfig:
    program: str
    options: tuple[OptionSpec, ...]
    positionals: tuple[PositionalSpec, ...]


class CodeWriter:
    """Tiny helper for readable generated C source."""

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

    def render(self) -> str:
        return "\n".join(self._lines) + "\n"


class ArgumentConstraintVisitor:
    """Renames the original CLI main and appends a generated harness main."""

    def __init__(self, config: CLIConfig):
        self.config = config

    def visit(self, ast: FileAST) -> FileAST:
        main_function = self._find_main_definition(ast)
        self._validate_main_signature(main_function)
        self._rename_existing_main(ast)
        ast.ext.extend(self._parse_harness_source().ext)
        return ast

    def _find_main_definition(self, ast: FileAST) -> FuncDef:
        for node in ast.ext:
            if isinstance(node, FuncDef) and node.decl.name == HARNESS_MAIN_NAME:
                return node
        raise ValueError("Input program must define main(argc, argv) for CLI harness generation.")

    def _validate_main_signature(self, main_function: FuncDef) -> None:
        func_decl = main_function.decl.type
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
        if len(params) != 2:
            raise ValueError("Input main must have the signature int main(int argc, char **argv).")

        argc_param, argv_param = params
        if not self._is_int_param(argc_param):
            raise ValueError("Input main must take int argc as its first parameter.")
        if not self._is_argv_param(argv_param):
            raise ValueError("Input main must take char **argv or char *argv[] as its second parameter.")

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

    def _rename_existing_main(self, ast: FileAST) -> None:
        for node in ast.ext:
            if isinstance(node, FuncDef) and node.decl.name == HARNESS_MAIN_NAME:
                self._rename_decl(node.decl, ORIGINAL_MAIN_NAME)
            elif (
                isinstance(node, Decl)
                and node.name == HARNESS_MAIN_NAME
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
        builder = HarnessSourceBuilder(self.config)
        return parser.parse(builder.build())


class HarnessSourceBuilder:
    """Builds readable C source for a harness main from the CLI config."""

    def __init__(self, config: CLIConfig):
        self.config = config
        self.writer = CodeWriter()

    def build(self) -> str:
        self.writer.start_block("int main(void)")
        self.writer.line("int __eclipse_argc = 1;")
        self.writer.line(f"char *__eclipse_argv[{self._max_argv_slots() + 1}];")
        self.writer.line(f'__eclipse_argv[0] = {self._c_string(self.config.program)};')

        if self.config.options or self.config.positionals:
            self.writer.blank()

        self._emit_symbolic_setup()
        self._emit_relationship_constraints()
        self._emit_argv_construction()

        self.writer.blank()
        self.writer.line("__eclipse_argv[__eclipse_argc] = 0;")
        self.writer.line(
            f"return {ORIGINAL_MAIN_NAME}(__eclipse_argc, __eclipse_argv);"
        )
        self.writer.end_block()
        return self.writer.render()

    def _emit_symbolic_setup(self) -> None:
        setup_sections = []
        for option in self.config.options:
            setup_sections.extend(self._setup_lines_for_option(option))
        for positional in self.config.positionals:
            setup_sections.extend(self._setup_lines_for_positional(positional))

        for lines in setup_sections:
            for line in lines:
                self.writer.line(line)
            self.writer.blank()

        if setup_sections:
            self._trim_trailing_blank()

    def _emit_relationship_constraints(self) -> None:
        constraint_lines = self._relationship_constraints()
        if not constraint_lines:
            return

        self.writer.blank()
        for line in constraint_lines:
            self.writer.line(line)

    def _emit_argv_construction(self) -> None:
        self.writer.blank()
        for option in self.config.options:
            self._emit_option_into_argv(option)
        for positional in self.config.positionals:
            self._emit_positional_into_argv(positional)

    def _setup_lines_for_option(self, option: OptionSpec) -> list[list[str]]:
        if option.kind == "one_of":
            return self._setup_lines_for_one_of(option)
        return self._setup_lines_for_simple_option(option)

    def _setup_lines_for_simple_option(self, option: OptionSpec) -> list[list[str]]:
        sections: list[list[str]] = []

        if not option.required:
            sections.append(self._symbolic_boolean(self._presence_var(option), f"use_{option.name}"))

        if option.kind == "bool":
            return sections

        if option.kind == "int":
            sections.append(
                [
                    f"int {self._value_var(option)};",
                    *self._symbolic_integer(self._value_var(option), option.name),
                    self._assume(
                        self._range_expr(
                            self._value_var(option),
                            option.value.min_value,
                            option.value.max_value,
                        )
                    ),
                    f"char {self._int_buffer_var(option)}[{self._int_buffer_size(option)}];",
                ]
            )
            return sections

        if option.kind == "string":
            sections.append(
                [
                    f"char {self._value_var(option)}[{option.value.max_length + 1}];",
                    *self._symbolic_buffer(
                        self._value_var(option),
                        option.name,
                        option.value.max_length,
                    ),
                ]
            )
            return sections

        if option.kind == "enum_flag":
            selector_var = self._selector_var(option)
            lower_bound = 1 if option.required else 0
            upper_bound = len(option.value.enum_values)
            sections.append(
                [
                    f"int {selector_var};",
                    *self._symbolic_integer(selector_var, f"{option.name}_state"),
                    self._assume(self._range_expr(selector_var, lower_bound, upper_bound)),
                ]
            )
            return sections

        raise ValueError(f"Unsupported option kind '{option.kind}'.")

    def _setup_lines_for_one_of(self, option: OptionSpec) -> list[list[str]]:
        selector_var = self._selector_var(option)
        lower_bound = 1 if option.required else 0
        upper_bound = len(option.choices)
        sections = [
            [
                f"int {selector_var};",
                *self._symbolic_integer(selector_var, f"{option.name}_choice"),
                self._assume(self._range_expr(selector_var, lower_bound, upper_bound)),
            ]
        ]

        for choice in option.choices:
            if choice.value.kind == "bool":
                continue
            if choice.value.kind == "int":
                sections.append(
                    [
                        f"int {self._choice_value_var(option, choice)};",
                        *self._symbolic_integer(
                            self._choice_value_var(option, choice),
                            f"{option.name}_{choice.name}",
                        ),
                        self._assume(
                            self._range_expr(
                                self._choice_value_var(option, choice),
                                choice.value.min_value,
                                choice.value.max_value,
                            )
                        ),
                        (
                            f"char {self._choice_buffer_var(option, choice)}"
                            f"[{self._int_buffer_size_for_range(choice.value.min_value, choice.value.max_value)}];"
                        ),
                    ]
                )
            elif choice.value.kind == "string":
                sections.append(
                    [
                        (
                            f"char {self._choice_value_var(option, choice)}"
                            f"[{choice.value.max_length + 1}];"
                        ),
                        *self._symbolic_buffer(
                            self._choice_value_var(option, choice),
                            f"{option.name}_{choice.name}",
                            choice.value.max_length,
                        ),
                    ]
                )
            else:
                raise ValueError(
                    f"Unsupported one_of choice kind '{choice.value.kind}'."
                )

        return sections

    def _setup_lines_for_positional(self, positional: PositionalSpec) -> list[list[str]]:
        sections: list[list[str]] = []

        if positional.min_count != positional.max_count:
            sections.append(
                [
                    f"int {self._positional_count_var(positional)};",
                    *self._symbolic_integer(
                        self._positional_count_var(positional),
                        f"{positional.name}_count",
                    ),
                    self._assume(
                        self._range_expr(
                            self._positional_count_var(positional),
                            positional.min_count,
                            positional.max_count,
                        )
                    ),
                ]
            )

        for index in range(positional.max_count):
            buffer_name = self._positional_value_var(positional, index)
            sections.append(
                [
                    f"char {buffer_name}[{positional.max_length + 1}];",
                    *self._symbolic_buffer(
                        buffer_name,
                        f"{positional.name}_{index}",
                        positional.max_length,
                    ),
                ]
            )

        return sections

    def _relationship_constraints(self) -> list[str]:
        constraints: list[str] = []
        emitted: set[str] = set()

        for option in self.config.options:
            source_presence = self._presence_expr(option)
            for dependency in option.requires:
                expr = self._requirement_expr(dependency)
                line = self._assume(f"(!({source_presence})) || ({expr})")
                if line not in emitted:
                    emitted.add(line)
                    constraints.append(line)

            for excluded_name in option.excludes:
                target_presence = self._presence_expr(self._option_by_name(excluded_name))
                line = self._assume(f"(!({source_presence})) || (!({target_presence}))")
                if line not in emitted:
                    emitted.add(line)
                    constraints.append(line)

        return constraints

    def _emit_option_into_argv(self, option: OptionSpec) -> None:
        if option.kind == "one_of":
            self._emit_one_of_into_argv(option)
            return

        presence_expr = self._presence_expr(option)
        if presence_expr == "1":
            self._emit_simple_option_body(option)
            return

        self.writer.start_block(f"if ({presence_expr})")
        self._emit_simple_option_body(option)
        self.writer.end_block()

    def _emit_simple_option_body(self, option: OptionSpec) -> None:
        if option.kind == "bool":
            self._append_argv_item(self._c_string(option.flag))
            return

        if option.kind == "int":
            self._append_argv_item(self._c_string(option.flag))
            self._append_argv_item(
                (
                    f"__eclipse_int_to_string({self._value_var(option)}, "
                    f"{self._int_buffer_var(option)}, sizeof({self._int_buffer_var(option)}))"
                )
            )
            return

        if option.kind == "string":
            self._append_argv_item(self._c_string(option.flag))
            self._append_argv_item(self._value_var(option))
            return

        if option.kind == "enum_flag":
            for index, value in enumerate(option.value.enum_values, start=1):
                state_expr = self._state_expr(option, value)
                self.writer.start_block(f"if ({state_expr})")
                if value == "present":
                    self._append_argv_item(self._c_string(option.flag))
                else:
                    self._append_argv_item(self._c_string(f"{option.flag}={value}"))
                self.writer.end_block()
            return

        raise ValueError(f"Unsupported option kind '{option.kind}'.")

    def _emit_one_of_into_argv(self, option: OptionSpec) -> None:
        for choice in option.choices:
            self.writer.start_block(f"if ({self._state_expr(option, choice.name)})")
            self._append_argv_item(self._c_string(choice.flag))
            if choice.value.kind == "int":
                self._append_argv_item(
                    (
                        f"__eclipse_int_to_string({self._choice_value_var(option, choice)}, "
                        f"{self._choice_buffer_var(option, choice)}, "
                        f"sizeof({self._choice_buffer_var(option, choice)}))"
                    )
                )
            elif choice.value.kind == "string":
                self._append_argv_item(self._choice_value_var(option, choice))
            self.writer.end_block()

    def _emit_positional_into_argv(self, positional: PositionalSpec) -> None:
        for index in range(positional.max_count):
            if positional.min_count > index:
                self._append_argv_item(self._positional_value_var(positional, index))
                continue

            self.writer.start_block(
                f"if ({self._positional_count_expr(positional)} > {index})"
            )
            self._append_argv_item(self._positional_value_var(positional, index))
            self.writer.end_block()

    def _append_argv_item(self, expr: str) -> None:
        self.writer.line(f"__eclipse_argv[__eclipse_argc] = {expr};")
        self.writer.line("__eclipse_argc++;")

    def _trim_trailing_blank(self) -> None:
        while self.writer._lines and self.writer._lines[-1] == "":
            self.writer._lines.pop()

    def _presence_expr(self, option: OptionSpec) -> str:
        if option.required:
            return "1"
        if option.kind == "one_of":
            return f"({self._selector_var(option)} != 0)"
        if option.kind == "enum_flag":
            return f"({self._selector_var(option)} != 0)"
        return self._presence_var(option)

    def _requirement_expr(self, dependency: DependencySpec) -> str:
        target_option = self._option_by_name(dependency.option_name)
        if dependency.choice_name is None:
            return self._presence_expr(target_option)
        return self._state_expr(target_option, dependency.choice_name)

    def _state_expr(self, option: OptionSpec, state_name: str) -> str:
        selector_var = self._selector_var(option)

        if option.kind == "one_of":
            for index, choice in enumerate(option.choices, start=1):
                if choice.name == state_name:
                    return f"({selector_var} == {index})"
            raise ValueError(
                f"Option '{option.name}' has no choice named '{state_name}'."
            )

        if option.kind == "enum_flag":
            for index, value in enumerate(option.value.enum_values, start=1):
                if value == state_name:
                    return f"({selector_var} == {index})"
            raise ValueError(
                f"Option '{option.name}' has no enum state named '{state_name}'."
            )

        raise ValueError(
            f"Option '{option.name}' does not support state selection."
        )

    def _option_by_name(self, option_name: str) -> OptionSpec:
        for option in self.config.options:
            if option.name == option_name:
                return option
        raise ValueError(f"Unknown option '{option_name}'.")

    def _presence_var(self, option: OptionSpec) -> str:
        return f"__eclipse_use_{option.name}"

    def _selector_var(self, option: OptionSpec) -> str:
        return f"__eclipse_{option.name}_selector"

    def _value_var(self, option: OptionSpec) -> str:
        return f"sym_{option.name}"

    def _int_buffer_var(self, option: OptionSpec) -> str:
        return f"__eclipse_{option.name}_value"

    def _choice_value_var(self, option: OptionSpec, choice: ChoiceSpec) -> str:
        return f"sym_{option.name}_{choice.name}"

    def _choice_buffer_var(self, option: OptionSpec, choice: ChoiceSpec) -> str:
        return f"__eclipse_{option.name}_{choice.name}_value"

    def _positional_count_var(self, positional: PositionalSpec) -> str:
        return f"__eclipse_{positional.name}_count"

    def _positional_count_expr(self, positional: PositionalSpec) -> str:
        if positional.min_count == positional.max_count:
            return str(positional.max_count)
        return self._positional_count_var(positional)

    def _positional_value_var(self, positional: PositionalSpec, index: int) -> str:
        return f"sym_{positional.name}_{index}"

    def _max_argv_slots(self) -> int:
        slots = 1
        for option in self.config.options:
            if option.kind == "bool":
                slots += 1
            elif option.kind in {"int", "string"}:
                slots += 2
            elif option.kind == "enum_flag":
                slots += 1
            elif option.kind == "one_of":
                slots += max(self._tokens_for_choice(choice) for choice in option.choices)
        for positional in self.config.positionals:
            slots += positional.max_count
        return slots

    def _tokens_for_choice(self, choice: ChoiceSpec) -> int:
        return 1 if choice.value.kind == "bool" else 2

    def _symbolic_boolean(self, variable_name: str, label: str) -> list[str]:
        return [
            f"int {variable_name};",
            *self._symbolic_integer(variable_name, label),
            self._assume(f"(({variable_name} == 0) || ({variable_name} == 1))"),
        ]

    def _symbolic_integer(self, variable_name: str, label: str) -> list[str]:
        return [
            (
                f'klee_make_symbolic(&{variable_name}, sizeof({variable_name}), '
                f'{self._c_string(label)});'
            )
        ]

    def _symbolic_buffer(self, buffer_name: str, label: str, max_length: int) -> list[str]:
        return [
            (
                f'klee_make_symbolic({buffer_name}, sizeof({buffer_name}), '
                f'{self._c_string(label)});'
            ),
            self._assume(f"{buffer_name}[{max_length}] == '\\0'"),
        ]

    def _assume(self, expr: str) -> str:
        return f"klee_assume({expr});"

    def _range_expr(self, variable_name: str, min_value: int, max_value: int) -> str:
        return (
            f"(({variable_name} >= {min_value}) && ({variable_name} <= {max_value}))"
        )

    def _int_buffer_size(self, option: OptionSpec) -> int:
        return self._int_buffer_size_for_range(
            option.value.min_value, option.value.max_value
        )

    def _int_buffer_size_for_range(self, min_value: int, max_value: int) -> int:
        return max(len(str(min_value)), len(str(max_value))) + 1

    def _c_string(self, value: str) -> str:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'


def load_cli_config(config_path: str | Path) -> CLIConfig:
    config_path = Path(config_path)
    raw_config = yaml.safe_load(config_path.read_text()) or {}
    if not isinstance(raw_config, dict):
        raise ValueError("CLI config must contain a YAML mapping.")

    program = raw_config.get("program")
    if not isinstance(program, str) or not program:
        raise ValueError("CLI config must define a non-empty 'program' name.")

    raw_options = raw_config.get("options", {})
    if not isinstance(raw_options, dict):
        raise ValueError("'options' must be a YAML mapping.")

    raw_positionals = raw_config.get("positionals", {})
    if not isinstance(raw_positionals, dict):
        raise ValueError("'positionals' must be a YAML mapping.")

    options = tuple(
        _load_option_spec(option_name, raw_option)
        for option_name, raw_option in raw_options.items()
    )
    positionals = tuple(
        _load_positional_spec(positional_name, raw_positional)
        for positional_name, raw_positional in raw_positionals.items()
    )

    config = CLIConfig(program=program, options=options, positionals=positionals)
    _validate_config(config)
    return config


def _load_option_spec(option_name: str, raw_option: object) -> OptionSpec:
    _validate_identifier(option_name, "option name")
    if not isinstance(raw_option, dict):
        raise ValueError(f"Option '{option_name}' must be a YAML object.")

    raw_kind = raw_option.get("kind")
    if raw_kind == "one_of":
        raw_choices = raw_option.get("choices")
        if not isinstance(raw_choices, dict) or not raw_choices:
            raise ValueError(f"Option '{option_name}' must define non-empty one_of choices.")
        choices = tuple(
            _load_choice_spec(choice_name, raw_choice)
            for choice_name, raw_choice in raw_choices.items()
        )
        return OptionSpec(
            name=option_name,
            kind="one_of",
            required=_load_required(raw_option, default=True),
            choices=choices,
            requires=_load_dependencies(raw_option.get("requires", [])),
            excludes=_load_excludes(raw_option.get("excludes", [])),
        )

    flag = raw_option.get("flag")
    if not isinstance(flag, str) or not flag.startswith("-"):
        raise ValueError(f"Option '{option_name}' requires a flag string like '--pin'.")

    value_spec = _load_value_spec(option_name, raw_option)
    return OptionSpec(
        name=option_name,
        kind=value_spec.kind,
        required=_load_required(raw_option, default=False),
        flag=flag,
        value=value_spec,
        requires=_load_dependencies(raw_option.get("requires", [])),
        excludes=_load_excludes(raw_option.get("excludes", [])),
    )


def _load_choice_spec(choice_name: str, raw_choice: object) -> ChoiceSpec:
    _validate_identifier(choice_name, "choice name")
    if not isinstance(raw_choice, dict):
        raise ValueError(f"Choice '{choice_name}' must be a YAML object.")

    flag = raw_choice.get("flag")
    if not isinstance(flag, str) or not flag.startswith("-"):
        raise ValueError(f"Choice '{choice_name}' requires a flag string.")

    value_spec = _load_value_spec(choice_name, raw_choice, default_kind="bool")
    return ChoiceSpec(name=choice_name, flag=flag, value=value_spec)


def _load_value_spec(
    spec_name: str, raw_spec: dict[str, object], default_kind: str | None = None
) -> ValueSpec:
    raw_kind = raw_spec.get("type", default_kind)
    if raw_kind == "bool":
        return ValueSpec(kind="bool")

    if raw_kind == "int":
        min_value = raw_spec.get("min")
        max_value = raw_spec.get("max")
        if not isinstance(min_value, int) or not isinstance(max_value, int):
            raise ValueError(f"Integer spec '{spec_name}' requires integer min and max.")
        if min_value > max_value:
            raise ValueError(f"Integer spec '{spec_name}' must satisfy min <= max.")
        return ValueSpec(kind="int", min_value=min_value, max_value=max_value)

    if raw_kind == "string":
        max_length = raw_spec.get("max_length")
        if not isinstance(max_length, int) or max_length < 0:
            raise ValueError(
                f"String spec '{spec_name}' requires a non-negative integer max_length."
            )
        return ValueSpec(kind="string", max_length=max_length)

    if raw_kind == "enum_flag":
        raw_values = raw_spec.get("values")
        if not isinstance(raw_values, list) or not raw_values:
            raise ValueError(f"Enum flag '{spec_name}' requires a non-empty values list.")
        values = []
        for value in raw_values:
            if not isinstance(value, str) or not value:
                raise ValueError(
                    f"Enum flag '{spec_name}' values must be non-empty strings."
                )
            values.append(value)
        return ValueSpec(kind="enum_flag", enum_values=tuple(values))

    raise ValueError(
        f"Spec '{spec_name}' must use type bool, int, string, or enum_flag."
    )


def _load_positional_spec(positional_name: str, raw_positional: object) -> PositionalSpec:
    _validate_identifier(positional_name, "positional name")
    if not isinstance(raw_positional, dict):
        raise ValueError(f"Positional '{positional_name}' must be a YAML object.")

    positional_kind = raw_positional.get("type")
    if positional_kind != "string_list":
        raise ValueError(
            f"Positional '{positional_name}' must currently use type string_list."
        )

    min_count = raw_positional.get("min_count")
    max_count = raw_positional.get("max_count")
    max_length = raw_positional.get("max_length")

    if not isinstance(min_count, int) or not isinstance(max_count, int):
        raise ValueError(
            f"Positional '{positional_name}' requires integer min_count and max_count."
        )
    if min_count < 0 or min_count > max_count:
        raise ValueError(
            f"Positional '{positional_name}' must satisfy 0 <= min_count <= max_count."
        )
    if not isinstance(max_length, int) or max_length < 0:
        raise ValueError(
            f"Positional '{positional_name}' requires a non-negative integer max_length."
        )

    return PositionalSpec(
        name=positional_name,
        kind="string_list",
        min_count=min_count,
        max_count=max_count,
        max_length=max_length,
    )


def _load_required(raw_spec: dict[str, object], default: bool) -> bool:
    required = raw_spec.get("required", default)
    if not isinstance(required, bool):
        raise ValueError("'required' must be true or false.")
    return required


def _load_dependencies(raw_requires: object) -> tuple[DependencySpec, ...]:
    if raw_requires is None:
        return ()
    if not isinstance(raw_requires, list):
        raise ValueError("'requires' must be a YAML list.")

    dependencies = []
    for raw_dependency in raw_requires:
        if isinstance(raw_dependency, str):
            dependencies.append(DependencySpec(option_name=raw_dependency))
            continue
        if isinstance(raw_dependency, dict):
            option_name = raw_dependency.get("option")
            choice_name = raw_dependency.get("choice")
            if not isinstance(option_name, str) or not option_name:
                raise ValueError("Each dependency must include a non-empty option name.")
            if choice_name is not None and (not isinstance(choice_name, str) or not choice_name):
                raise ValueError("Dependency choice names must be non-empty strings.")
            dependencies.append(DependencySpec(option_name=option_name, choice_name=choice_name))
            continue
        raise ValueError("Each dependency must be a string or YAML object.")
    return tuple(dependencies)


def _load_excludes(raw_excludes: object) -> tuple[str, ...]:
    if raw_excludes is None:
        return ()
    if not isinstance(raw_excludes, list):
        raise ValueError("'excludes' must be a YAML list.")

    excludes = []
    for raw_exclude in raw_excludes:
        if not isinstance(raw_exclude, str) or not raw_exclude:
            raise ValueError("Excluded option names must be non-empty strings.")
        excludes.append(raw_exclude)
    return tuple(excludes)


def _validate_config(config: CLIConfig) -> None:
    option_lookup = {option.name: option for option in config.options}
    positional_lookup = {positional.name: positional for positional in config.positionals}

    if len(option_lookup) != len(config.options):
        raise ValueError("CLI config reuses an option name.")
    if len(positional_lookup) != len(config.positionals):
        raise ValueError("CLI config reuses a positional name.")

    used_flags: dict[str, str] = {}
    for option in config.options:
        if option.kind == "one_of":
            if not option.choices:
                raise ValueError(f"Option '{option.name}' must define at least one choice.")
            for choice in option.choices:
                _record_flag(used_flags, choice.flag, f"{option.name}.{choice.name}")
        else:
            _record_flag(used_flags, option.flag, option.name)

    for option in config.options:
        for excluded_name in option.excludes:
            if excluded_name not in option_lookup:
                raise ValueError(
                    f"Option '{option.name}' excludes unknown option '{excluded_name}'."
                )
            if excluded_name == option.name:
                raise ValueError(f"Option '{option.name}' cannot exclude itself.")

        for dependency in option.requires:
            target = option_lookup.get(dependency.option_name)
            if target is None:
                raise ValueError(
                    f"Option '{option.name}' requires unknown option '{dependency.option_name}'."
                )
            if dependency.choice_name is None:
                continue
            if target.kind == "one_of":
                choice_names = {choice.name for choice in target.choices}
                if dependency.choice_name not in choice_names:
                    raise ValueError(
                        f"Option '{option.name}' requires unknown choice "
                        f"'{dependency.choice_name}' on option '{target.name}'."
                    )
                continue
            if target.kind == "enum_flag":
                if dependency.choice_name not in set(target.value.enum_values):
                    raise ValueError(
                        f"Option '{option.name}' requires unknown state "
                        f"'{dependency.choice_name}' on option '{target.name}'."
                    )
                continue
            raise ValueError(
                f"Option '{option.name}' requires choice '{dependency.choice_name}' "
                f"on '{target.name}', but that option has no selectable states."
            )


def _record_flag(used_flags: dict[str, str], flag: str, owner: str) -> None:
    if flag in used_flags:
        raise ValueError(f"Flag '{flag}' is used by both '{used_flags[flag]}' and '{owner}'.")
    used_flags[flag] = owner


def _validate_identifier(name: str, description: str) -> None:
    if not isinstance(name, str) or not name or not name.isidentifier():
        raise ValueError(f"{description.capitalize()} '{name}' must be a valid identifier.")


def add_argument_constraints(ast: FileAST, config_path: str | Path) -> FileAST:
    """Generate a symbolic CLI harness around the program's main function."""

    return ArgumentConstraintVisitor(load_cli_config(config_path)).visit(ast)
