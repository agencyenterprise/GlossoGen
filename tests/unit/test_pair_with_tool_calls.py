"""How a scenario's per-call verdict events are keyed by the tool call they judged."""

from typing import Literal

from glossogen.models.event import SimulationEvent, ToolResultReceived
from glossogen.models.event_base import EventBase
from glossogen.scenario_run_detail_extension import pair_with_tool_calls

JUDGED_TOOLS = frozenset({"act", "act_again"})


class ActJudged(EventBase):
    """A verdict on one ``act`` call, logged without the call's id."""

    event_type: Literal["act_judged"] = "act_judged"
    agent_id: str
    verdict: str


def judged(agent_id: str, verdict: str) -> ActJudged:
    return ActJudged(round_number=1, agent_id=agent_id, verdict=verdict)


def result(agent_id: str, call_id: str, tool_name: str) -> ToolResultReceived:
    return ToolResultReceived(
        round_number=1,
        agent_id=agent_id,
        tool_name=tool_name,
        call_id=call_id,
        arguments={},
        result="ok",
    )


def pair(events: list[SimulationEvent]) -> dict[str, str]:
    return pair_with_tool_calls(
        events=events,
        judged_event_cls=ActJudged,
        tool_names=JUDGED_TOOLS,
        build_payload=lambda event: event.verdict,
    )


def test_each_result_takes_the_oldest_verdict_queued_for_its_agent() -> None:
    events: list[SimulationEvent] = [
        judged(agent_id="a", verdict="first"),
        judged(agent_id="a", verdict="second"),
        result(agent_id="a", call_id="c1", tool_name="act"),
        result(agent_id="a", call_id="c2", tool_name="act_again"),
    ]

    assert pair(events=events) == {"c1": "first", "c2": "second"}


def test_agents_keep_separate_queues() -> None:
    events: list[SimulationEvent] = [
        judged(agent_id="a", verdict="for a"),
        judged(agent_id="b", verdict="for b"),
        result(agent_id="b", call_id="cb", tool_name="act"),
        result(agent_id="a", call_id="ca", tool_name="act"),
    ]

    assert pair(events=events) == {"ca": "for a", "cb": "for b"}


def test_results_of_other_tools_take_no_verdict() -> None:
    events: list[SimulationEvent] = [
        judged(agent_id="a", verdict="first"),
        result(agent_id="a", call_id="talk", tool_name="send_message"),
        result(agent_id="a", call_id="c1", tool_name="act"),
    ]

    assert pair(events=events) == {"c1": "first"}


def test_a_result_with_nothing_queued_stays_unpaired() -> None:
    events: list[SimulationEvent] = [
        result(agent_id="a", call_id="early", tool_name="act"),
        judged(agent_id="a", verdict="late"),
        result(agent_id="a", call_id="c2", tool_name="act"),
    ]

    assert pair(events=events) == {"c2": "late"}
