"""The steps one ``act`` call takes, and what the scenario records of each.

An operator gives ``act`` a list of these and the scenario works through it in
order. ``PlannedCrateStep`` is the shape an operator working more than one crate
gives, so a step names the crate it is for; with one crate the field is absent
from the tool's schema rather than present and ignored.

The docstrings of ``CrateAction`` and the step models are for developers, and
each is kept out of the JSON schema the model reads.
"""

from enum import Enum
from typing import NamedTuple

from pydantic import BaseModel, ConfigDict, GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from glossogen.models.tool_definition import drop_schema_description
from glossogen.scenarios.move_a_box.ids import (
    FINISH_TOOL,
    PACK_ICE_TOOL,
    STAND_BY_TOOL,
    Direction,
    HaulMethod,
)
from glossogen.scenarios.move_a_box.world import LoggedAction


class CrateAction(str, Enum):
    """What one step of an ``act`` call does to a crate.

    Each action is named after the tool that takes it alone, and the three
    carrying methods after the way ``haul`` carries the crate. Those three take
    a direction and move the crate one square. Standing by and packing ice each
    spend a step in place, and finishing leaves the crate where it stands.
    """

    DRAG = HaulMethod.DRAG.value
    SLED = HaulMethod.SLED.value
    CART = HaulMethod.CART.value
    STAND_BY = STAND_BY_TOOL
    PACK_ICE = PACK_ICE_TOOL
    FINISH = FINISH_TOOL

    @classmethod
    def __get_pydantic_json_schema__(
        cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        """The enum's schema without the class docstring."""
        schema = handler(core_schema)
        drop_schema_description(schema=handler.resolve_ref_schema(schema))
        return schema


_HAUL_METHODS: dict[str, HaulMethod] = {method.value: method for method in HaulMethod}


def haul_method_of(action: CrateAction) -> HaulMethod | None:
    """The carrying method ``action`` names, or None when it does not move the crate."""
    return _HAUL_METHODS.get(action.value)


class PlannedStep(BaseModel):
    """One action of an ``act`` call, for an operator working a single crate.

    ``direction`` is the way to carry the crate under ``drag``, ``sled`` and
    ``cart``, and null under the actions that do not move it.
    """

    model_config = ConfigDict(json_schema_extra=drop_schema_description)

    action: CrateAction
    direction: Direction | None


class PlannedCrateStep(PlannedStep):
    """One action of an ``act`` call, naming the crate it is for by its marking."""

    crate: str


class ResolvedStep(NamedTuple):
    """One action checked against the operator's crates, ready for the floor."""

    crate_id: str
    action: CrateAction
    direction: Direction | None


class AppliedStep(NamedTuple):
    """An action the floor took, with what its event records.

    ``steps_used`` is the operator's step count right after the action. ``bay``
    is the bay a finish left the crate on, None for every other action and for a
    finish off the bays the depot assigned.
    """

    entry: LoggedAction
    steps_used: int
    bay: int | None


class AppliedList(NamedTuple):
    """How far the floor took one ``act`` list.

    ``stopped`` is the floor's refusal of the first action it would not take,
    or None when it took the whole list.
    """

    applied: list[AppliedStep]
    stopped: str | None


class StepReport(NamedTuple):
    """One action of an ``act`` list, as the call's result names it back.

    ``bay`` is the name of the bay a finish left the crate on, its square or its
    mark, and None for every other action.
    """

    crate: str
    action: str
    direction: str | None
    temperature: int
    bay: str | None
