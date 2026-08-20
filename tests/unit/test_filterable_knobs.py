"""Reading a knobs JSON Schema into the controls the runs list can offer.

Driven with hand-written schemas rather than a scenario's, so each shape a
Pydantic model can produce is stated here rather than depending on which shapes
the shipped scenarios happen to use. One test does run over every installed
scenario, to catch a schema shape nothing here anticipated.
"""

from typing import Any

import pytest

from glossogen.scenario_loader import available_scenario_names, get_scenario_class
from glossogen.server.scenarios.filterable_knobs import (
    FilterableKnobType,
    filterable_knobs_from_schema,
)


def schema_of(properties: dict[str, Any], defs: dict[str, Any]) -> dict[str, Any]:
    """A knobs schema carrying these properties."""
    return {"type": "object", "properties": properties, "$defs": defs}


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        ({"type": "integer"}, FilterableKnobType.INTEGER),
        ({"type": "number"}, FilterableKnobType.NUMBER),
        ({"type": "boolean"}, FilterableKnobType.BOOLEAN),
        ({"type": "string"}, FilterableKnobType.STRING),
    ],
)
def test_each_scalar_type_maps_to_its_control(
    spec: dict[str, Any],
    expected: FilterableKnobType,
) -> None:
    """The four scalar JSON Schema types each become a filterable knob."""
    knobs = filterable_knobs_from_schema(knobs_schema=schema_of({"k": spec}, {}))
    assert [(knob.name, knob.knob_type, knob.enum_values, knob.nullable) for knob in knobs] == [
        ("k", expected, None, False)
    ]


@pytest.mark.parametrize(
    "spec",
    [
        {"type": "array", "items": {"type": "integer"}},
        {"type": "object", "additionalProperties": {"type": "string"}},
        {"type": "null"},
        {"const": 3},
        {},
    ],
)
def test_a_knob_with_no_scalar_comparison_is_not_offered(spec: dict[str, Any]) -> None:
    """A list or a mapping has no comparison that means the obvious thing."""
    assert filterable_knobs_from_schema(knobs_schema=schema_of({"k": spec}, {})) == []


def test_an_optional_scalar_keeps_its_type_and_reports_nullable() -> None:
    """``int | None`` is filterable on its values, and on being unset.

    ``nullable`` is what lets a control offer "not set", which is the question
    worth asking of a knob like veyru's ``swap_round``.
    """
    spec = {"anyOf": [{"type": "integer"}, {"type": "null"}]}
    knobs = filterable_knobs_from_schema(knobs_schema=schema_of({"k": spec}, {}))
    assert [(knob.name, knob.knob_type, knob.nullable) for knob in knobs] == [
        ("k", FilterableKnobType.INTEGER, True)
    ]


def test_a_union_of_two_concrete_types_is_not_offered() -> None:
    """One control cannot stand for two types, so there is nothing to render."""
    spec = {"anyOf": [{"type": "integer"}, {"type": "string"}]}
    assert filterable_knobs_from_schema(knobs_schema=schema_of({"k": spec}, {})) == []


def test_a_ref_to_a_string_enum_carries_its_values() -> None:
    """A knob typed as an Enum is a select, so its values travel with it."""
    schema = schema_of(
        {"mode": {"$ref": "#/$defs/Mode"}},
        {"Mode": {"enum": ["mask", "random_letter"], "type": "string"}},
    )
    knobs = filterable_knobs_from_schema(knobs_schema=schema)
    assert [(knob.name, knob.knob_type, knob.enum_values, knob.nullable) for knob in knobs] == [
        ("mode", FilterableKnobType.ENUM, ["mask", "random_letter"], False)
    ]


def test_an_optional_ref_to_an_enum_is_unwrapped_then_followed() -> None:
    """``Mode | None`` is both shapes at once, and still a select."""
    schema = schema_of(
        {"mode": {"anyOf": [{"$ref": "#/$defs/Mode"}, {"type": "null"}]}},
        {"Mode": {"enum": ["mask"], "type": "string"}},
    )
    knobs = filterable_knobs_from_schema(knobs_schema=schema)
    assert [(knob.name, knob.knob_type, knob.nullable) for knob in knobs] == [
        ("mode", FilterableKnobType.ENUM, True)
    ]


def test_a_ref_to_a_nested_model_is_not_offered() -> None:
    """A model-valued knob is an object, which has no scalar comparison."""
    schema = schema_of(
        {"compaction": {"$ref": "#/$defs/Compaction"}},
        {"Compaction": {"type": "object", "properties": {"enabled": {"type": "boolean"}}}},
    )
    assert filterable_knobs_from_schema(knobs_schema=schema) == []


def test_a_ref_that_resolves_to_nothing_is_not_offered() -> None:
    """A dangling ``$ref`` is not a crash and not a guess."""
    schema = schema_of({"k": {"$ref": "#/$defs/Missing"}}, {})
    assert filterable_knobs_from_schema(knobs_schema=schema) == []


def test_a_non_string_enum_is_not_offered() -> None:
    """The values travel to the browser as strings, so a mixed enum is dropped."""
    schema = schema_of({"k": {"enum": [1, "two"]}}, {})
    assert filterable_knobs_from_schema(knobs_schema=schema) == []


def test_the_schema_order_is_preserved() -> None:
    """The dropdown lists knobs the way the knobs model declares them."""
    schema = schema_of(
        {
            "b": {"type": "integer"},
            "skipped": {"type": "array", "items": {"type": "integer"}},
            "a": {"type": "boolean"},
        },
        {},
    )
    assert [knob.name for knob in filterable_knobs_from_schema(knobs_schema=schema)] == ["b", "a"]


@pytest.mark.parametrize("schema", [{}, {"properties": []}, {"type": "object"}])
def test_a_schema_with_no_properties_offers_nothing(schema: dict[str, Any]) -> None:
    """A malformed or empty schema answers with no knobs rather than raising."""
    assert filterable_knobs_from_schema(knobs_schema=schema) == []


@pytest.mark.parametrize("scenario_name", sorted(available_scenario_names()))
def test_every_installed_scenario_yields_filterable_knobs(scenario_name: str) -> None:
    """A real knobs schema is readable, and every knob it offers is named and typed.

    Each scenario extends ``BaseKnobs``, which declares scalars, so a scenario
    offering none of them means the reader stopped understanding the schema.
    """
    schema = get_scenario_class(name=scenario_name).knobs_json_schema()
    knobs = filterable_knobs_from_schema(knobs_schema=schema)

    assert knobs, f"{scenario_name} offered no filterable knobs"
    declared = set(schema["properties"])
    for knob in knobs:
        assert knob.name in declared
        if knob.knob_type is FilterableKnobType.ENUM:
            assert knob.enum_values
        else:
            assert knob.enum_values is None
