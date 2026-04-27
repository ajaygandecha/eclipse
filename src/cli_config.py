from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class OptionElement:
    id: str
    optional: bool
    spellings: tuple[str, ...]


@dataclass(frozen=True)
class PositionalElement:
    id: str
    optional: bool
    value_kind: str
    min: int
    max: int

    @property
    def min_length(self) -> int:
        return self.min

    @property
    def max_length(self) -> int:
        return self.max


@dataclass(frozen=True)
class OptionValueElement:
    id: str
    parent: str
    optional: bool
    value_kind: str
    min: int
    max: int


CLIElementSpec = OptionElement | PositionalElement | OptionValueElement


@dataclass(frozen=True)
class CLIProgramSpec:
    program: str
    entry_point: str
    klee_posix_command: str | None
    argv0: str
    elements: tuple[CLIElementSpec, ...]


_TOP_LEVEL_KEYS = {"program", "entry_point", "klee_posix_command", "args"}
_ARGS_KEYS = {"argv0", "elements"}
_LEGACY_KEYS = {"options", "positionals"}


def load_cli_config(config_path: str | Path) -> CLIProgramSpec:
    """Load and validate the canonical CLI YAML specification."""

    path = Path(config_path)
    raw_config = yaml.safe_load(path.read_text()) or {}
    if not isinstance(raw_config, dict):
        raise ValueError("CLI config must contain a YAML mapping.")

    _reject_legacy_schema(raw_config)
    _reject_unknown_keys(raw_config, _TOP_LEVEL_KEYS, "CLI config")

    program = _require_non_empty_string(raw_config.get("program"), "program")
    entry_point = _require_non_empty_string(
        raw_config.get("entry_point"), "entry_point"
    )
    if entry_point != "main":
        raise ValueError("CLI config entry_point must be 'main' in V1.")
    klee_posix_command = _load_optional_string(
        raw_config.get("klee_posix_command"),
        "klee_posix_command",
    )

    raw_args = raw_config.get("args")
    if not isinstance(raw_args, dict):
        raise ValueError("CLI config must define an 'args' mapping.")
    _reject_unknown_keys(raw_args, _ARGS_KEYS, "args")

    argv0 = _require_non_empty_string(raw_args.get("argv0"), "args.argv0")
    raw_elements = raw_args.get("elements", [])
    if raw_elements is None:
        raw_elements = []
    if not isinstance(raw_elements, list):
        raise ValueError("CLI config args.elements must be a YAML list.")

    elements = tuple(
        _load_element_spec(raw_element, index)
        for index, raw_element in enumerate(raw_elements)
    )

    spec = CLIProgramSpec(
        program=program,
        entry_point=entry_point,
        klee_posix_command=klee_posix_command,
        argv0=argv0,
        elements=elements,
    )
    _validate_element_relationships(spec.elements)
    return spec


def _reject_legacy_schema(raw_config: dict[str, object]) -> None:
    legacy_keys = _LEGACY_KEYS.intersection(raw_config)
    if legacy_keys:
        keys = ", ".join(sorted(legacy_keys))
        raise ValueError(
            "Legacy CLI schema is not supported in V1. Remove "
            f"{keys} and use args.argv0 plus args.elements instead."
        )


def _load_element_spec(raw_element: object, index: int) -> CLIElementSpec:
    if not isinstance(raw_element, dict):
        raise ValueError(f"CLI element #{index} must be a YAML mapping.")

    element_type = raw_element.get("type")
    if not isinstance(element_type, str) or not element_type:
        raise ValueError(f"CLI element #{index} must define a non-empty 'type'.")

    if element_type == "option":
        return _load_option_element(raw_element)
    if element_type == "positional":
        return _load_positional_element(raw_element)
    if element_type == "option_value":
        return _load_option_value_element(raw_element)

    raise ValueError(
        f"CLI element #{index} has unsupported type '{element_type}'. "
        "Supported types are option, positional, and option_value."
    )


def _load_option_element(raw_element: dict[str, object]) -> OptionElement:
    _reject_unknown_keys(
        raw_element,
        {"id", "type", "optional", "spellings"},
        "option element",
    )
    element_id = _require_identifier(raw_element.get("id"), "option id")
    optional = _load_optional(raw_element)
    spellings = _load_spellings(raw_element.get("spellings"), element_id)
    return OptionElement(id=element_id, optional=optional, spellings=spellings)


def _load_positional_element(raw_element: dict[str, object]) -> PositionalElement:
    _reject_unknown_keys(
        raw_element,
        {
            "id",
            "type",
            "optional",
            "value_kind",
            "min",
            "max",
            "min_length",
            "max_length",
        },
        "positional element",
    )
    element_id = _require_identifier(raw_element.get("id"), "positional id")
    optional = _load_optional(raw_element)
    value_kind = raw_element.get("value_kind", "string")
    if value_kind not in {"int", "string"}:
        raise ValueError(
            f"Positional '{element_id}' must use value_kind 'int' or 'string'."
        )

    if value_kind == "int":
        if "min_length" in raw_element or "max_length" in raw_element:
            raise ValueError(
                f"Integer positional '{element_id}' must use min/max, not min_length/max_length."
            )
        min_value = raw_element.get("min")
        max_value = raw_element.get("max")
        if not isinstance(min_value, int) or not isinstance(max_value, int):
            raise ValueError(
                f"Integer positional '{element_id}' must define integer min and max."
            )
        if min_value > max_value:
            raise ValueError(
                f"Integer positional '{element_id}' must satisfy min <= max."
            )
        return PositionalElement(
            id=element_id,
            optional=optional,
            value_kind=value_kind,
            min=min_value,
            max=max_value,
        )

    if "min" in raw_element or "max" in raw_element:
        raise ValueError(
            f"String positional '{element_id}' must use min_length/max_length, not min/max."
        )

    min_length = raw_element.get("min_length", 0)
    max_length = raw_element.get("max_length")

    if not isinstance(min_length, int) or min_length < 0:
        raise ValueError(
            f"Positional '{element_id}' must define a non-negative integer min_length."
        )
    if not isinstance(max_length, int) or max_length < 0:
        raise ValueError(
            f"Positional '{element_id}' must define a non-negative integer max_length."
        )
    if min_length > max_length:
        raise ValueError(
            f"Positional '{element_id}' must satisfy min_length <= max_length."
        )

    return PositionalElement(
        id=element_id,
        optional=optional,
        value_kind=value_kind,
        min=min_length,
        max=max_length,
    )


def _load_option_value_element(raw_element: dict[str, object]) -> OptionValueElement:
    _reject_unknown_keys(
        raw_element,
        {"id", "type", "parent", "optional", "value_kind", "min", "max"},
        "option_value element",
    )
    element_id = _require_identifier(raw_element.get("id"), "option_value id")
    parent = _require_identifier(raw_element.get("parent"), "option_value parent")
    optional = _load_optional(raw_element)

    value_kind = raw_element.get("value_kind")
    if value_kind not in {"int", "string"}:
        raise ValueError(
            f"Option value '{element_id}' must use value_kind 'int' or 'string'."
        )

    min_value = raw_element.get("min")
    max_value = raw_element.get("max")
    if not isinstance(min_value, int) or not isinstance(max_value, int):
        raise ValueError(
            f"Option value '{element_id}' must define integer min and max."
        )
    if min_value < 0 and value_kind == "string":
        raise ValueError(
            f"String option value '{element_id}' must use a non-negative min length."
        )
    if max_value < 0 and value_kind == "string":
        raise ValueError(
            f"String option value '{element_id}' must use a non-negative max length."
        )
    if min_value > max_value:
        raise ValueError(f"Option value '{element_id}' must satisfy min <= max.")

    return OptionValueElement(
        id=element_id,
        parent=parent,
        optional=optional,
        value_kind=value_kind,
        min=min_value,
        max=max_value,
    )


def _validate_element_relationships(elements: tuple[CLIElementSpec, ...]) -> None:
    element_lookup: dict[str, CLIElementSpec] = {}

    for element in elements:
        if element.id in element_lookup:
            raise ValueError(f"CLI config reuses element id '{element.id}'.")
        element_lookup[element.id] = element

        if not isinstance(element, OptionValueElement):
            continue

        parent = element_lookup.get(element.parent)
        if parent is None:
            raise ValueError(
                f"Option value '{element.id}' must reference a previously declared "
                f"option parent '{element.parent}'."
            )
        if not isinstance(parent, OptionElement):
            raise ValueError(
                f"Option value '{element.id}' parent '{element.parent}' must be "
                "an option element."
            )


def _load_optional(raw_element: dict[str, object]) -> bool:
    optional = raw_element.get("optional", False)
    if not isinstance(optional, bool):
        raise ValueError("Element 'optional' must be true or false.")
    return optional


def _load_spellings(raw_spellings: object, element_id: str) -> tuple[str, ...]:
    if not isinstance(raw_spellings, list) or not raw_spellings:
        raise ValueError(
            f"Option '{element_id}' must define a non-empty spellings list."
        )

    spellings: list[str] = []
    for spelling in raw_spellings:
        if not isinstance(spelling, str):
            raise ValueError(
                f"Option '{element_id}' spellings must be strings like '-n' or '--name'."
            )
        if spelling in spellings:
            raise ValueError(f"Option '{element_id}' repeats spelling '{spelling}'.")
        spellings.append(spelling)

    return tuple(spellings)


def _require_non_empty_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"CLI config must define a non-empty '{field_name}'.")
    return value


def _load_optional_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"CLI config '{field_name}' must be a non-empty string.")
    if field_name == "klee_posix_command" and "--sys-args" in value:
        raise ValueError(
            "CLI config 'klee_posix_command' uses '--sys-args', but KLEE's POSIX "
            "runtime option is '--sym-args'."
        )
    return value


def _require_identifier(value: object, description: str) -> str:
    if not isinstance(value, str) or not value or not value.isidentifier():
        raise ValueError(
            f"{description.capitalize()} '{value}' must be a valid identifier."
        )
    return value


def _reject_unknown_keys(
    raw_mapping: dict[str, object], allowed_keys: set[str], context: str
) -> None:
    unknown_keys = sorted(set(raw_mapping) - allowed_keys)
    if not unknown_keys:
        return

    unknown = ", ".join(unknown_keys)
    raise ValueError(f"{context.capitalize()} contains unsupported keys: {unknown}.")
