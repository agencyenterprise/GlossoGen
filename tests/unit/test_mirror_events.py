"""How a scenario's events of one class are copied into the response model that mirrors them."""

from typing import Literal

import pytest
from pydantic import BaseModel, ValidationError

from glossogen.models.event import SimulationEvent, ToolResultReceived
from glossogen.models.event_base import EventBase
from glossogen.scenario_run_detail_extension import mirror_events


class Stage(BaseModel):
    """A nested part of the event, with a field the mirror leaves out."""

    name: str
    secret: str


class CaseOpened(EventBase):
    """A case-start event with fields the mirror does not declare."""

    event_type: Literal["case_opened"] = "case_opened"
    case_number: int
    stages: list[Stage]


class StageMirror(BaseModel):
    name: str


class CaseMirror(BaseModel):
    round_number: int
    case_number: int
    stages: list[StageMirror]


class NeedsMore(BaseModel):
    case_number: int
    missing: str


def opened(round_number: int, case_number: int) -> CaseOpened:
    return CaseOpened(
        round_number=round_number,
        case_number=case_number,
        stages=[Stage(name=f"stage {case_number}", secret="hidden")],
    )


def unrelated() -> ToolResultReceived:
    return ToolResultReceived(
        round_number=1, agent_id="a", tool_name="act", call_id="c", arguments={}, result="ok"
    )


def test_each_event_of_the_class_is_copied_in_log_order() -> None:
    events: list[SimulationEvent] = [opened(round_number=1, case_number=7), unrelated()]
    events.append(opened(round_number=2, case_number=3))

    mirrored = mirror_events(events=events, event_cls=CaseOpened, mirror_cls=CaseMirror)

    assert mirrored == [
        CaseMirror(round_number=1, case_number=7, stages=[StageMirror(name="stage 7")]),
        CaseMirror(round_number=2, case_number=3, stages=[StageMirror(name="stage 3")]),
    ]


def test_a_field_the_event_lacks_is_an_error() -> None:
    events: list[SimulationEvent] = [opened(round_number=1, case_number=7)]

    with pytest.raises(ValidationError):
        mirror_events(events=events, event_cls=CaseOpened, mirror_cls=NeedsMore)
