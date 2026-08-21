"""Which of a scenario's knobs the runs list can filter on, and with what widget.

Reads the knobs JSON Schema and keeps the scalar-valued knobs: a number, a
boolean, a string, or a string enum. Lists and mappings are dropped, because
there is no single comparison that means the obvious thing for them.

Interpreting the schema here rather than in the browser keeps one reading of it.
The frontend receives a knob name, a type, and for an enum its values, which is
enough to choose a widget and an operator set without knowing JSON Schema.
"""

import logging
from enum import Enum
from typing import Any, NamedTuple, cast

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# The JSON Schema type names that map onto a filter widget. Each is spelled the
# same as its FilterableKnobType member, so the member is looked up by value.
_SCALAR_SCHEMA_TYPES = frozenset({"integer", "number", "boolean", "string"})


class FilterableKnobType(str, Enum):
    """The widget and operator set a knob's filter control should use."""

    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    STRING = "string"
    ENUM = "enum"


class FilterableKnob(BaseModel):
    """One knob the runs list can filter on.

    ``enum_values`` is populated only for :attr:`FilterableKnobType.ENUM`, and
    is the full set of values the knob accepts.

    ``nullable`` says the knob may be left unset, so a filter control should
    offer "not set" alongside the values. A run recording null there is still
    filterable, with ``null`` as the value a condition compares against.
    """

    name: str
    knob_type: FilterableKnobType
    enum_values: list[str] | None
    nullable: bool


def _resolve_ref(spec: dict[str, Any], defs: dict[str, Any]) -> dict[str, Any] | None:
    """Follow a local ``$ref`` into ``$defs``, or None when it points elsewhere."""
    ref = spec.get("$ref")
    if not isinstance(ref, str):
        return None
    prefix = "#/$defs/"
    if not ref.startswith(prefix):
        return None
    target = defs.get(ref[len(prefix) :])
    if not isinstance(target, dict):
        return None
    return cast(dict[str, Any], target)


class _Unwrapped(NamedTuple):
    """A property's schema with any ``| None`` removed, and whether one was there."""

    spec: dict[str, Any]
    nullable: bool


def _unwrap_optional(spec: dict[str, Any]) -> _Unwrapped:
    """Reduce ``T | None`` to ``T``, reporting whether the None was present.

    Pydantic writes an optional knob as ``anyOf: [T, {"type": "null"}]``. Such a
    knob is filterable on the values it does take, and on being unset.
    """
    raw_branches = spec.get("anyOf")
    if not isinstance(raw_branches, list):
        return _Unwrapped(spec=spec, nullable=False)
    branches = cast(list[Any], raw_branches)
    concrete: list[dict[str, Any]] = [
        cast(dict[str, Any], branch)
        for branch in branches
        if isinstance(branch, dict) and cast(dict[str, Any], branch).get("type") != "null"
    ]
    if len(concrete) != 1:
        return _Unwrapped(spec=spec, nullable=False)
    return _Unwrapped(spec=concrete[0], nullable=len(concrete) < len(branches))


def _string_enum_values(spec: dict[str, Any]) -> list[str] | None:
    """The values of a string enum, or None when the spec is not one."""
    values = spec.get("enum")
    if not isinstance(values, list) or not values:
        return None
    typed_values = cast(list[Any], values)
    if not all(isinstance(value, str) for value in typed_values):
        return None
    return [str(value) for value in typed_values]


def _classify(name: str, spec: dict[str, Any], defs: dict[str, Any]) -> FilterableKnob | None:
    """Read one property's schema into a filterable knob, or None when it is not one."""
    unwrapped = _unwrap_optional(spec=spec)
    resolved = unwrapped.spec
    target = _resolve_ref(spec=resolved, defs=defs)
    if target is not None:
        resolved = target

    enum_values = _string_enum_values(spec=resolved)
    if enum_values is not None:
        return FilterableKnob(
            name=name,
            knob_type=FilterableKnobType.ENUM,
            enum_values=enum_values,
            nullable=unwrapped.nullable,
        )

    schema_type = resolved.get("type")
    if not isinstance(schema_type, str) or schema_type not in _SCALAR_SCHEMA_TYPES:
        return None
    return FilterableKnob(
        name=name,
        knob_type=FilterableKnobType(schema_type),
        enum_values=None,
        nullable=unwrapped.nullable,
    )


def filterable_knobs_from_schema(knobs_schema: dict[str, Any]) -> list[FilterableKnob]:
    """Every scalar knob in a knobs JSON Schema, in the schema's own order."""
    properties = knobs_schema.get("properties")
    if not isinstance(properties, dict):
        return []
    raw_defs = knobs_schema.get("$defs")
    defs: dict[str, Any] = {}
    if isinstance(raw_defs, dict):
        defs = cast(dict[str, Any], raw_defs)

    knobs: list[FilterableKnob] = []
    for name, spec in cast(dict[str, Any], properties).items():
        if not isinstance(spec, dict):
            continue
        classified = _classify(
            name=str(name),
            spec=cast(dict[str, Any], spec),
            defs=defs,
        )
        if classified is None:
            continue
        knobs.append(classified)
    return knobs
