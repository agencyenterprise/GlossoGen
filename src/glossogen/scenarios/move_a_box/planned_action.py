"""The steps one ``act`` call takes, and the record of a step that was applied.

An operator gives ``act`` a list of these and the scenario works through it in
order. ``PlannedCrateStep`` is the shape an operator working more than one crate
gives, so a step names the crate it is for; with one crate the field is absent
from the tool's schema rather than present and ignored.
"""

from typing import NamedTuple

from pydantic import BaseModel

from glossogen.scenarios.move_a_box.ids import CrateAction, Direction


class PlannedStep(BaseModel):
    """One action of an ``act`` call, for an operator working a single crate.

    ``direction`` is the square to carry the crate to under ``drag``, ``sled``
    and ``cart``, and null under the actions that do not move it.
    """

    action: CrateAction
    direction: Direction | None


class PlannedCrateStep(PlannedStep):
    """One action of an ``act`` call, naming the crate it is for by its marking."""

    crate: str


class ResolvedStep(NamedTuple):
    """A step checked against the operator's crates before any of the list is applied."""

    crate_id: str
    action: CrateAction
    direction: Direction | None


class AppliedStep(NamedTuple):
    """A step that stood, as the call's result reports it back.

    ``bay`` is the square a finished crate was left on, filled in only when the
    step finished a crate on a bay the depot had assigned that operator.
    """

    sequence: int
    crate: str
    action: str
    direction: str | None
    temperature: int
    bay: str | None
