"""Veyru's canvas medium: the agents draw on the comm link and pay one second per pixel.

Scripted agents play the canvas preset through the real tools, runtime and
runner: one round with one team, or two rounds with two teams that swap their
observers.
"""

import asyncio
import json
from pathlib import Path

import pytest

from glossogen.models.canvas import CanvasDrawing, CanvasPixel
from glossogen.models.event import MessageSent, ToolResultReceived, WorldEventDelivered
from glossogen.scenario_contract.protocol import SimulationScenario
from glossogen.scenarios.veyru.ids import (
    LINK_A_CHANNEL_ID,
    LINK_B_CHANNEL_ID,
    OBSERVER_A_ID,
    OBSERVER_B_ID,
    STABILIZATION_ENGINEER_A_ID,
    STABILIZATION_ENGINEER_B_ID,
    TEAM_A_ID,
    TEAM_B_ID,
    VEYRU_COLLAPSED_MARKER,
)
from glossogen.scenarios.veyru.world import VeyruWorld
from glossogen.testing.scenario_runtime import ROUND_SECONDS, build_scenario
from glossogen.testing.scripted_agent import EventGate, GatedTurn, RoundGate, SayTurn, ToolTurn
from glossogen.testing.simulation_harness import (
    SimulationResult,
    never_times_out,
    run_round_paced_simulation,
    run_simulation,
)

pytestmark = pytest.mark.xdist_group("veyru")

OBSERVER = "field_observer"
ENGINEER = "stabilization_engineer"
LINK = "link"
THREE_PIXELS = [[0, 0], [1, 1], [2, 2]]


def canvas_scenario(budget: int) -> SimulationScenario:
    """The canvas preset, cut to one round with no discussion phase and a ``budget``."""
    return build_scenario(
        scenario_name="veyru",
        preset_name="knobs_canvas",
        overrides={
            "round_count": 1,
            "max_round_duration_seconds": ROUND_SECONDS,
            "postmortem_enabled": False,
            "postmortem_after_swap": False,
            "round_time_budget_seconds": budget,
        },
    )


def once_drawn() -> EventGate:
    """Holds a script until the observer's drawing is on the link."""

    def drawn(event: dict[str, object]) -> bool:
        if event["event_type"] != "message_sent":
            return False
        return MessageSent.model_validate(event).message.drawing is not None

    return EventGate(matches=drawn, description=f"{OBSERVER} sends a drawing")


async def play(
    scenario: SimulationScenario,
    scripts: dict[str, list[GatedTurn]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> SimulationResult:
    """One round inside a timeout, so a gate that never opens fails the test."""
    async with asyncio.timeout(60):
        return await run_simulation(
            scenario=scenario,
            scripts=scripts,
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            phase_timed_out=never_times_out,
        )


def draw() -> ToolTurn:
    """A turn painting three pixels on the comm link."""
    return ToolTurn(
        tool_name="send_drawing", args={"channel_id": LINK, "pixels": THREE_PIXELS, "force": True}
    )


async def test_the_engineer_reads_the_observers_drawing_as_an_image(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = await play(
        scenario=canvas_scenario(budget=150),
        scripts={
            OBSERVER: [draw(), SayTurn(text="done")],
            ENGINEER: [
                once_drawn(),
                ToolTurn(tool_name="read_channel", args={"channel_id": LINK, "last_n": 10}),
                SayTurn(text="done"),
            ],
        },
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    (read,) = [
        event
        for event in result.of_type(event_type=ToolResultReceived)
        if event.agent_id == ENGINEER and event.tool_name == "read_channel"
    ]
    (message,) = json.loads(read.result)["messages"]
    assert message["text"] == ""
    assert message["image"] == 1
    assert len(read.images) == 1


async def test_pixels_over_the_budget_collapse_the_veyru(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = await play(
        scenario=canvas_scenario(budget=2),
        scripts={OBSERVER: [draw(), SayTurn(text="done")], ENGINEER: [SayTurn(text="done")]},
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    notices = {
        event.text
        for event in result.of_type(event_type=WorldEventDelivered)
        if VEYRU_COLLAPSED_MARKER in event.text
    }
    assert notices == {
        f"{VEYRU_COLLAPSED_MARKER}. Communication time: 3s (3 pixels) exceeded budget of 2s."
    }


async def test_text_on_the_comm_link_is_refused_in_a_canvas_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = await play(
        scenario=canvas_scenario(budget=150),
        scripts={
            OBSERVER: [
                ToolTurn(
                    tool_name="send_message",
                    args={"channel_id": LINK, "text": "faces flicker", "force": True},
                ),
                SayTurn(text="done"),
            ],
            ENGINEER: [SayTurn(text="done")],
        },
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    (refused,) = [
        event
        for event in result.of_type(event_type=ToolResultReceived)
        if event.tool_name == "send_message"
    ]
    assert json.loads(refused.result)["status"] == "rejected"
    assert result.of_type(event_type=MessageSent) == []


def two_team_swap_scenario() -> SimulationScenario:
    """The canvas preset with two teams over three rounds, swapping the observers after round 1."""
    return build_scenario(
        scenario_name="veyru",
        preset_name="knobs_canvas",
        overrides={
            "two_teams": True,
            "swap_round": 1,
            "round_count": 3,
            "max_round_duration_seconds": ROUND_SECONDS,
            "postmortem_enabled": False,
            "postmortem_after_swap": False,
        },
    )


def test_each_link_bills_its_drawings_to_its_own_team_after_the_swap() -> None:
    """The observer that arrives on a link pays that link's team for its pixels."""
    world = two_team_swap_scenario().get_world()
    assert isinstance(world, VeyruWorld)
    arrived_on_a, arrived_on_b = world.swap_observers()
    world.begin_round()

    world.on_drawing(
        agent_id=arrived_on_a,
        channel_id=LINK_A_CHANNEL_ID,
        drawing=CanvasDrawing(
            width=16, height=16, pixels=[CanvasPixel(x=x, y=0) for x in range(5)]
        ),
    )
    world.on_drawing(
        agent_id=arrived_on_b,
        channel_id=LINK_B_CHANNEL_ID,
        drawing=CanvasDrawing(width=16, height=16, pixels=[CanvasPixel(x=0, y=0)]),
    )

    assert world.characters_used(team_id=TEAM_A_ID) == 5
    assert world.characters_used(team_id=TEAM_B_ID) == 1


async def test_after_the_swap_an_observer_draws_to_its_new_engineer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Team A's observer moves to team B's link and team B's engineer reads its drawing.

    The observer draws in round 2 and the engineer reads in round 3, so the read
    comes after the drawing whatever order the agents' cycles run in.
    """
    async with asyncio.timeout(60):
        result = await run_round_paced_simulation(
            scenario=two_team_swap_scenario(),
            scripts={
                OBSERVER_A_ID: [
                    RoundGate(round_number=2),
                    ToolTurn(
                        tool_name="send_drawing",
                        args={
                            "channel_id": LINK_B_CHANNEL_ID,
                            "pixels": THREE_PIXELS,
                            "force": True,
                        },
                    ),
                    SayTurn(text="drawn"),
                ],
                OBSERVER_B_ID: [],
                STABILIZATION_ENGINEER_A_ID: [],
                STABILIZATION_ENGINEER_B_ID: [
                    RoundGate(round_number=3),
                    ToolTurn(
                        tool_name="read_channel",
                        args={"channel_id": LINK_B_CHANNEL_ID, "last_n": 10},
                    ),
                    SayTurn(text="read"),
                ],
            },
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            phase_timed_out=never_times_out,
        )

    (drawing,) = [
        event for event in result.of_type(event_type=MessageSent) if event.message.drawing
    ]
    assert (drawing.round_number, drawing.message.sender_agent_id) == (2, OBSERVER_A_ID)
    (read,) = [
        event
        for event in result.of_type(event_type=ToolResultReceived)
        if event.agent_id == STABILIZATION_ENGINEER_B_ID and event.tool_name == "read_channel"
    ]
    (message,) = json.loads(read.result)["messages"]
    assert message["image"] == 1
    assert len(read.images) == 1


async def test_no_budget_never_collapses_the_veyru(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = await play(
        scenario=canvas_scenario(budget=-1),
        scripts={OBSERVER: [draw(), SayTurn(text="done")], ENGINEER: [SayTurn(text="done")]},
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    assert [
        event.text
        for event in result.of_type(event_type=WorldEventDelivered)
        if "exceeded budget" in event.text or "CRITICAL" in event.text
    ] == []
