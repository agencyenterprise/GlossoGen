"""The canvas medium: viewers draw on the link, read each other's drawings as images, pay in pixels.

Scripted viewers play one round of the canvas preset, so the drawing goes
through the real tools, runtime and runner. The tests check what was stored,
what the reading viewer received, what the team was charged, and that a resume
rebuilds the reader's history with the image.
"""

import asyncio
import io
import json
from pathlib import Path

import pytest
from PIL import Image
from pydantic import ValidationError
from pydantic_ai.messages import ModelRequest, ToolReturnPart

from glossogen.engine.canvas_link import (
    SEND_DRAWING_TOOL,
    TEXT_REFUSED_ON_CANVAS_LINK,
)
from glossogen.models.event import MessageSent, ToolResultReceived
from glossogen.models.mcp_responses import SendStatus
from glossogen.run_replay.message_history_builder import build_message_history
from glossogen.run_replay.tool_return_images import split_tool_return
from glossogen.scenario_contract.platform_runner_prompts import platform_runner_prompts
from glossogen.scenario_contract.protocol import SimulationScenario
from glossogen.scenarios.spot_the_intersection.events import IntersectionSubmissionRecorded
from glossogen.scenarios.spot_the_intersection.knobs import SpotTheIntersectionKnobs
from glossogen.testing.scenario_runtime import ROUND_SECONDS, build_scenario
from glossogen.testing.scripted_agent import EventGate, GatedTurn, SayTurn, ToolTurn
from glossogen.testing.simulation_harness import SimulationResult, never_times_out, run_simulation
from tests.scenarios.spot_the_intersection.conftest import SCENARIO, answer_of, submit

pytestmark = pytest.mark.xdist_group(SCENARIO)

DRAWER = "viewer_a_1"
READER = "viewer_a_2"
LINK = "link_a"
PIXELS = [[0, 0], [5, 3], [15, 15]]


def canvas_scenario() -> SimulationScenario:
    """The canvas preset, cut to one round with no debrief."""
    return build_scenario(
        scenario_name=SCENARIO,
        preset_name="knobs_canvas",
        overrides={
            "round_count": 1,
            "max_round_duration_seconds": ROUND_SECONDS,
            "postmortem_enabled": False,
        },
    )


def draw(pixels: list[list[int]]) -> ToolTurn:
    """A turn sending a drawing of ``pixels`` on Team A's link."""
    return ToolTurn(
        tool_name=SEND_DRAWING_TOOL, args={"channel_id": LINK, "pixels": pixels, "force": True}
    )


def once_drawn() -> EventGate:
    """Holds a script until the drawer's drawing is on the link."""

    def drawn(event: dict[str, object]) -> bool:
        if event["event_type"] != "message_sent":
            return False
        return MessageSent.model_validate(event).message.drawing is not None

    return EventGate(matches=drawn, description=f"{DRAWER} sends a drawing")


async def play(
    scenario: SimulationScenario,
    scripts: dict[str, list[GatedTurn]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> SimulationResult:
    """One round inside a timeout, so a gate that never opens fails the test."""
    for agent in scenario.get_agents(default_model="m", default_provider="anthropic"):
        scripts.setdefault(
            agent.agent_id, [submit(obj=answer_of(scenario=scenario)), SayTurn(text="done")]
        )
    async with asyncio.timeout(60):
        return await run_simulation(
            scenario=scenario,
            scripts=scripts,
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            phase_timed_out=never_times_out,
        )


async def play_drawing_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[SimulationScenario, SimulationResult]:
    """The drawer draws and submits; the reader waits for the drawing, reads the link, submits."""
    scenario = canvas_scenario()
    answer = submit(obj=answer_of(scenario=scenario))
    result = await play(
        scenario=scenario,
        scripts={
            DRAWER: [draw(pixels=PIXELS), answer, SayTurn(text="done")],
            READER: [
                once_drawn(),
                ToolTurn(tool_name="read_channel", args={"channel_id": LINK, "last_n": 10}),
                answer,
                SayTurn(text="done"),
            ],
        },
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    return scenario, result


def reader_read(result: SimulationResult) -> ToolResultReceived:
    """The reader's read_channel result."""
    (read,) = [
        event
        for event in result.of_type(event_type=ToolResultReceived)
        if event.agent_id == READER and event.tool_name == "read_channel"
    ]
    return read


async def test_a_drawing_is_stored_with_its_pixels_and_no_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, result = await play_drawing_round(tmp_path=tmp_path, monkeypatch=monkeypatch)

    (sent,) = [
        event
        for event in result.of_type(event_type=MessageSent)
        if event.message.sender_agent_id == DRAWER
    ]
    assert sent.message.text == ""
    assert sent.message.drawing is not None
    assert [(p.x, p.y) for p in sent.message.drawing.pixels] == [(0, 0), (5, 3), (15, 15)]


async def test_the_reader_receives_the_drawing_as_an_image_and_never_its_coordinates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, result = await play_drawing_round(tmp_path=tmp_path, monkeypatch=monkeypatch)

    read = reader_read(result=result)
    (message,) = json.loads(read.result)["messages"]
    assert message["text"] == ""
    assert message["image"] == 1
    assert "pixels" not in read.result
    (image,) = read.images
    assert image.number == 1
    assert Image.open(io.BytesIO(image.data)).size == (16 * 32 + 1, 16 * 32 + 1)


async def test_a_team_is_charged_one_per_painted_pixel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, result = await play_drawing_round(tmp_path=tmp_path, monkeypatch=monkeypatch)

    locked = [
        event
        for event in result.of_type(event_type=IntersectionSubmissionRecorded)
        if event.team_id == "team_a" and event.members_submitted == event.members_required
    ]
    assert [event.team_characters for event in locked] == [len(PIXELS)]


async def test_a_resumed_reader_gets_the_image_back_in_its_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, result = await play_drawing_round(tmp_path=tmp_path, monkeypatch=monkeypatch)
    recorded = reader_read(result=result).images

    history = build_message_history(
        events=result.events,
        agent_id=READER,
        system_prompt="rebuilt",
        runner_prompts=platform_runner_prompts(role_name="Viewer 2"),
        target_timestamp=result.events[-1].timestamp,
        cutoff_round=None,
        tool_calls_only=False,
        channel_visibility={},
        history_floor_round=None,
        filter_below_round=None,
        split_parallel_tool_calls=False,
    )

    returns = [
        part
        for message in history
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, ToolReturnPart) and part.tool_name == "read_channel"
    ]
    (read_return,) = returns
    rebuilt = split_tool_return(content=read_return.content)
    assert rebuilt is not None
    assert rebuilt.images == recorded


async def test_text_on_the_link_is_refused_during_a_canvas_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = canvas_scenario()
    result = await play(
        scenario=scenario,
        scripts={
            DRAWER: [
                ToolTurn(
                    tool_name="send_message",
                    args={"channel_id": LINK, "text": "C4 red circle", "force": True},
                ),
                submit(obj=answer_of(scenario=scenario)),
                SayTurn(text="done"),
            ]
        },
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    (refused,) = [
        event
        for event in result.of_type(event_type=ToolResultReceived)
        if event.agent_id == DRAWER and event.tool_name == "send_message"
    ]
    assert json.loads(refused.result)["status"] == SendStatus.REJECTED.value
    assert json.loads(refused.result)["detail"] == TEXT_REFUSED_ON_CANVAS_LINK
    assert result.of_type(event_type=MessageSent) == []


async def test_a_pixel_off_the_canvas_reaches_the_drawer_as_the_tools_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = canvas_scenario()
    result = await play(
        scenario=scenario,
        scripts={
            DRAWER: [
                draw(pixels=[[16, 0]]),
                submit(obj=answer_of(scenario=scenario)),
                SayTurn(text="done"),
            ]
        },
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    assert result.of_type(event_type=MessageSent) == []


def test_only_a_canvas_run_offers_send_drawing_and_describes_the_canvas() -> None:
    canvas = canvas_scenario()
    text = build_scenario(scenario_name=SCENARIO, preset_name="knobs_default", overrides={})

    assert [tool.name for tool in canvas.get_tools()] == ["submit_object", SEND_DRAWING_TOOL]
    assert [tool.name for tool in text.get_tools()] == ["submit_object"]
    prompt, *_ = [
        agent.system_prompt
        for agent in canvas.get_agents(default_model="m", default_provider="anthropic")
    ]
    assert "16x16 canvas" in prompt
    assert "FEWEST pixels" in prompt


def test_a_canvas_run_refuses_channel_noise() -> None:
    preset = SpotTheIntersectionKnobs.model_validate(
        build_scenario(scenario_name=SCENARIO, preset_name="knobs_canvas", overrides={})
        .get_knobs()
        .model_dump()
    )
    with pytest.raises(ValidationError, match="channel_noise_level=0"):
        SpotTheIntersectionKnobs.model_validate({**preset.model_dump(), "channel_noise_level": 0.1})
