"""Tests for building ATIF trajectories from a run's event log."""

import io
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath

import pytest
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from glossogen.atif_export.atif_models import AtifStepSource, AtifTrajectory
from glossogen.atif_export.atif_run_context import AtifRunContext, load_atif_run_context
from glossogen.atif_export.atif_trajectory_builder import (
    build_agent_trajectories,
    build_run_trajectories,
    trajectory_file_name,
)
from glossogen.atif_export.copied_context import (
    NO_COPIED_CONTEXT,
    CopiedContext,
    load_copied_context,
)
from glossogen.atif_export.tool_definition_reconstruction import reconstruct_tool_definitions
from glossogen.cli import main
from glossogen.models.event import (
    AgentRegistered,
    AgentRunCycleFailed,
    AgentSwappedMidRun,
    ContextCompacted,
    InjectionDelivered,
    LLMResponseReceived,
    SimulationEvent,
    SimulationStarted,
    StopReason,
    ToolCallInvoked,
    ToolResultReceived,
)
from glossogen.models.event_base import TokenUsage
from glossogen.models.tool_definition import RecordedToolDefinition, ToolCallRequest
from glossogen.replace_manifest import REPLACE_MANIFEST_FILENAME, ReplaceManifest
from glossogen.run_export.runs_zip_archive import add_run_to_zip
from glossogen.runners.communication_protocol import CONTINUE_PROMPT, INITIAL_PROMPT
from glossogen.scenario_loader import get_scenario_class

RUN_ID = "veyru/1700000000"
START = datetime(2026, 1, 1, tzinfo=UTC)
ZERO_USAGE = TokenUsage(
    input_tokens=0, output_tokens=0, cache_read_input_tokens=0, cache_creation_input_tokens=0
)
CYCLE_USAGE = TokenUsage(
    input_tokens=1_000_000,
    output_tokens=10_000,
    cache_read_input_tokens=800_000,
    cache_creation_input_tokens=100_000,
)


def _at(seconds: int) -> datetime:
    return START + timedelta(seconds=seconds)


def _started() -> SimulationStarted:
    return SimulationStarted(
        run_id=RUN_ID,
        scenario_name="veyru",
        scenario_description="",
        channel_ids=["link"],
        scenario_config={"round_count": 3},
        provider="anthropic",
        round_number=0,
        timestamp=_at(seconds=0),
    )


def _registered(agent_id: str, model: str, seconds: int) -> AgentRegistered:
    return AgentRegistered(
        agent_id=agent_id,
        role_name="Field Observer",
        system_prompt=f"You are {agent_id}.",
        channel_ids=["link"],
        tool_names=["read_channel", "send_message"],
        model=model,
        provider="anthropic",
        max_tokens=2048,
        round_number=0,
        timestamp=_at(seconds=seconds),
    )


def _injection(agent_id: str, round_number: int, seconds: int) -> InjectionDelivered:
    return InjectionDelivered(
        agent_id=agent_id,
        text=f"Round {round_number} begins.",
        round_number=round_number,
        timestamp=_at(seconds=seconds),
    )


def _response(
    agent_id: str,
    round_number: int,
    seconds: int,
    call_id: str,
    usage: TokenUsage,
) -> LLMResponseReceived:
    return LLMResponseReceived(
        agent_id=agent_id,
        thinking="plan the message",
        text="Sending the reading.",
        tool_calls=[
            ToolCallRequest(call_id=call_id, tool_name="send_message", arguments={"text": "hi"})
        ],
        stop_reason=StopReason.TOOL_USE,
        usage=usage,
        round_number=round_number,
        timestamp=_at(seconds=seconds),
    )


def _invoked(agent_id: str, round_number: int, seconds: int, call_id: str) -> ToolCallInvoked:
    return ToolCallInvoked(
        agent_id=agent_id,
        call_id=call_id,
        tool_name="send_message",
        arguments={"text": "hi"},
        round_number=round_number,
        timestamp=_at(seconds=seconds),
    )


def _result(agent_id: str, round_number: int, seconds: int, call_id: str) -> ToolResultReceived:
    return ToolResultReceived(
        agent_id=agent_id,
        tool_name="send_message",
        call_id=call_id,
        arguments={"text": "hi"},
        result="sent",
        round_number=round_number,
        timestamp=_at(seconds=seconds),
    )


def _single_agent_run() -> list[SimulationEvent]:
    """Two rounds; round 1's tool result is logged before the response that made the call."""
    return [
        _started(),
        _registered(agent_id="field_observer", model="claude-sonnet-4-6", seconds=1),
        _injection(agent_id="field_observer", round_number=1, seconds=2),
        _invoked(agent_id="field_observer", round_number=1, seconds=3, call_id="c1"),
        _result(agent_id="field_observer", round_number=1, seconds=3, call_id="c1"),
        _response(
            agent_id="field_observer", round_number=1, seconds=4, call_id="c1", usage=ZERO_USAGE
        ),
        AgentRunCycleFailed(
            agent_id="field_observer",
            cycle=2,
            error_type="ModelHTTPError",
            message="overloaded",
            round_number=2,
            timestamp=_at(seconds=5),
        ),
        _injection(agent_id="field_observer", round_number=2, seconds=6),
        _invoked(agent_id="field_observer", round_number=2, seconds=7, call_id="c2"),
        _response(
            agent_id="field_observer", round_number=2, seconds=7, call_id="c2", usage=CYCLE_USAGE
        ),
        _result(agent_id="field_observer", round_number=2, seconds=8, call_id="c2"),
    ]


def _only(trajectories: list[AtifTrajectory]) -> AtifTrajectory:
    assert len(trajectories) == 1
    return trajectories[0]


def _context(
    events: list[SimulationEvent],
    copied_context: CopiedContext,
    reconstructed: list[RecordedToolDefinition] | None,
) -> AtifRunContext:
    return AtifRunContext(
        events=events,
        run_id=RUN_ID,
        scenario_name="veyru",
        scenario_config={"round_count": 3},
        copied_context=copied_context,
        reconstructed_tool_definitions=reconstructed,
    )


def _build(events: list[SimulationEvent], cutoff_round: int | None) -> list[AtifTrajectory]:
    return build_agent_trajectories(
        context=_context(events=events, copied_context=NO_COPIED_CONTEXT, reconstructed=None),
        agent_id="field_observer",
        cutoff_round=cutoff_round,
    )


def test_steps_are_numbered_in_event_order_starting_with_the_system_prompt() -> None:
    trajectory = _only(_build(events=_single_agent_run(), cutoff_round=None))

    assert [step.step_id for step in trajectory.steps] == [1, 2, 3, 4, 5]
    assert [step.source for step in trajectory.steps] == [
        AtifStepSource.SYSTEM,
        AtifStepSource.USER,
        AtifStepSource.AGENT,
        AtifStepSource.USER,
        AtifStepSource.AGENT,
    ]
    assert trajectory.steps[0].message == "You are field_observer."
    assert trajectory.trajectory_id == f"{RUN_ID}/field_observer"
    assert trajectory.session_id == RUN_ID


def test_tool_results_attach_to_their_call_regardless_of_log_order() -> None:
    trajectory = _only(_build(events=_single_agent_run(), cutoff_round=None))

    for step in (trajectory.steps[2], trajectory.steps[4]):
        assert step.tool_calls is not None
        assert step.observation is not None
        assert [result.source_call_id for result in step.observation.results] == [
            call.tool_call_id for call in step.tool_calls
        ]
        assert step.observation.results[0].content == "sent"
        assert step.reasoning_content == "plan the message"


def test_only_responses_that_logged_usage_carry_metrics_and_totals_match() -> None:
    trajectory = _only(_build(events=_single_agent_run(), cutoff_round=None))

    assert trajectory.steps[2].metrics is None
    metrics = trajectory.steps[4].metrics
    assert metrics is not None
    assert metrics.prompt_tokens == 1_000_000
    assert metrics.cached_tokens == 800_000
    assert metrics.cost_usd is not None
    final = trajectory.final_metrics
    assert final.total_prompt_tokens == metrics.prompt_tokens
    assert final.total_completion_tokens == metrics.completion_tokens
    assert final.total_cost_usd == metrics.cost_usd
    assert final.total_steps == len(trajectory.steps)


def test_failed_cycles_are_recorded_on_the_next_agent_step() -> None:
    trajectory = _only(_build(events=_single_agent_run(), cutoff_round=None))

    assert "failed_cycles" not in trajectory.steps[2].extra
    assert trajectory.steps[4].extra["failed_cycles"] == [
        {"cycle": 2, "error_type": "ModelHTTPError", "message": "overloaded"}
    ]


def test_user_and_system_steps_carry_no_agent_only_fields() -> None:
    trajectory = _only(_build(events=_single_agent_run(), cutoff_round=None))

    for step in trajectory.steps:
        if step.source == AtifStepSource.AGENT:
            continue
        assert step.model_name is None
        assert step.reasoning_content is None
        assert step.tool_calls is None
        assert step.observation is None
        assert step.metrics is None


def test_cutoff_round_is_exclusive() -> None:
    trajectory = _only(_build(events=_single_agent_run(), cutoff_round=2))

    agent_rounds = [
        step.extra["round_number"]
        for step in trajectory.steps
        if step.source == AtifStepSource.AGENT
    ]
    assert agent_rounds == [1]
    assert trajectory.extra["cutoff_round"] == 2


def test_a_swap_to_another_model_starts_a_new_trajectory() -> None:
    events = _single_agent_run() + [
        AgentSwappedMidRun(
            agent_id="field_observer",
            new_model="gpt-5.4",
            new_provider="openai",
            channel_visibility={},
            round_number=3,
            timestamp=_at(seconds=9),
        ),
        _injection(agent_id="field_observer", round_number=3, seconds=10),
    ]

    first, second = _build(events=events, cutoff_round=None)

    assert first.trajectory_id == f"{RUN_ID}/field_observer/gen1"
    assert second.trajectory_id == f"{RUN_ID}/field_observer/gen2"
    assert first.agent.model_name == "claude-sonnet-4-6"
    assert second.agent.model_name == "gpt-5.4"
    assert second.agent.extra["provider"] == "openai"
    assert trajectory_file_name(trajectory=second) == "field_observer.gen2.json"


def test_a_swapped_in_generation_opens_with_its_seed_marked_copied() -> None:
    events = _single_agent_run() + [
        AgentSwappedMidRun(
            agent_id="field_observer",
            new_model="gpt-5.4",
            new_provider="openai",
            channel_visibility={},
            round_number=3,
            timestamp=_at(seconds=9),
        ),
        _invoked(agent_id="field_observer", round_number=3, seconds=10, call_id="c3"),
        _response(
            agent_id="field_observer", round_number=3, seconds=10, call_id="c3", usage=ZERO_USAGE
        ),
    ]

    _, second = _build(events=events, cutoff_round=None)

    system, *seed, prompt, live = second.steps
    assert system.source == AtifStepSource.SYSTEM
    assert system.is_copied_context is None
    assert seed
    assert all(step.is_copied_context for step in seed)
    assert all(step.timestamp is None for step in seed)
    assert prompt.message == CONTINUE_PROMPT
    assert prompt.is_copied_context is None
    assert live.tool_calls is not None
    assert live.tool_calls[0].tool_call_id == "c3"
    assert live.is_copied_context is None


def test_a_resume_re_registration_under_the_same_model_continues_the_trajectory() -> None:
    """The relaunched runner resumes the agent with its history, so it continues."""
    events: list[SimulationEvent] = [
        _started(),
        _registered(agent_id="field_observer", model="claude-sonnet-4-6", seconds=1),
        _invoked(agent_id="field_observer", round_number=1, seconds=2, call_id="c1"),
        _response(
            agent_id="field_observer", round_number=1, seconds=2, call_id="c1", usage=ZERO_USAGE
        ),
        _registered(agent_id="field_observer", model="claude-sonnet-4-6", seconds=9),
        _invoked(agent_id="field_observer", round_number=3, seconds=10, call_id="c3"),
        _response(
            agent_id="field_observer", round_number=3, seconds=10, call_id="c3", usage=ZERO_USAGE
        ),
    ]

    trajectory = _only(_build(events=events, cutoff_round=None))

    assert [step.message for step in trajectory.steps if step.source == AtifStepSource.USER] == [
        INITIAL_PROMPT,
        CONTINUE_PROMPT,
    ]
    assert trajectory_file_name(trajectory=trajectory) == "field_observer.json"


def test_run_trajectories_cover_every_agent_in_registration_order() -> None:
    events = _single_agent_run() + [
        _registered(agent_id="stabilization_engineer", model="claude-sonnet-4-6", seconds=9),
    ]

    trajectories = build_run_trajectories(
        context=_context(events=events, copied_context=NO_COPIED_CONTEXT, reconstructed=None),
        cutoff_round=None,
    )

    assert [trajectory.agent.extra["agent_id"] for trajectory in trajectories] == [
        "field_observer",
        "stabilization_engineer",
    ]


def test_raw_zip_includes_atif_trajectories_when_asked(tmp_path: Path) -> None:
    run_dir = tmp_path / "1700000000"
    run_dir.mkdir()
    lines = [event.model_dump_json() for event in _single_agent_run()]
    (run_dir / "veyru.jsonl").write_text("\n".join(lines) + "\n")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w") as archive:
        add_run_to_zip(
            archive=archive,
            run_dir=run_dir,
            arc_root=PurePosixPath("veyru/1700000000"),
            scenario_name="veyru",
            include_logs=False,
            include_atif=True,
        )
    buffer.seek(0)
    names = set(zipfile.ZipFile(buffer).namelist())

    assert "veyru/1700000000/atif/field_observer.json" in names
    assert "veyru/1700000000/veyru.jsonl" in names


def test_raw_zip_skips_atif_for_a_run_with_no_event_log(tmp_path: Path) -> None:
    run_dir = tmp_path / "1700000000"
    run_dir.mkdir()
    (run_dir / "labels.json").write_text("[]")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w") as archive:
        tally = add_run_to_zip(
            archive=archive,
            run_dir=run_dir,
            arc_root=PurePosixPath("veyru/1700000000"),
            scenario_name="veyru",
            include_logs=False,
            include_atif=True,
        )

    assert tally.file_count == 1


def _seed_history() -> list[ModelMessage]:
    return [
        ModelRequest(parts=[UserPromptPart(content="Round 1 begins.")]),
        ModelResponse(
            parts=[ToolCallPart(tool_name="send_message", args={"text": "hi"}, tool_call_id="s1")]
        ),
        ModelRequest(
            parts=[ToolReturnPart(tool_name="send_message", content="sent", tool_call_id="s1")]
        ),
    ]


def _replaced_run(source: list[SimulationEvent]) -> list[SimulationEvent]:
    """``source``, then a relaunch past its boundary re-registering the seat."""
    return source + [
        _registered(agent_id="field_observer", model="claude-sonnet-4-6", seconds=20),
        _invoked(agent_id="field_observer", round_number=3, seconds=21, call_id="c3"),
        _response(
            agent_id="field_observer", round_number=3, seconds=21, call_id="c3", usage=ZERO_USAGE
        ),
    ]


def _boundary_context(source: list[SimulationEvent], seeded: bool) -> CopiedContext:
    """Every event of ``source`` is copied."""
    seeded_agent_id: str | None = None
    seed: list[ModelMessage] = []
    if seeded:
        seeded_agent_id = "field_observer"
        seed = _seed_history()
    return CopiedContext(
        copied_event_ids=frozenset(event.event_id for event in source),
        seeded_agent_id=seeded_agent_id,
        boundary_seed=seed,
    )


def test_a_fork_marks_steps_up_to_the_boundary_as_copied() -> None:
    source = _single_agent_run()
    context = _context(
        events=_replaced_run(source=source),
        copied_context=_boundary_context(source=source, seeded=False),
        reconstructed=None,
    )

    trajectory = _only(
        build_agent_trajectories(context=context, agent_id="field_observer", cutoff_round=None)
    )

    assert [step.is_copied_context for step in trajectory.steps] == [
        True,
        True,
        True,
        True,
        True,
        None,
        None,
    ]


def test_a_replaced_seat_starts_a_new_generation_from_its_seed_under_the_same_model() -> None:
    source = _single_agent_run()
    context = _context(
        events=_replaced_run(source=source),
        copied_context=_boundary_context(source=source, seeded=True),
        reconstructed=None,
    )

    predecessor, replacement = build_agent_trajectories(
        context=context, agent_id="field_observer", cutoff_round=None
    )

    assert all(step.is_copied_context for step in predecessor.steps)
    system, seed_prompt, seed_call, prompt, live = replacement.steps
    assert system.is_copied_context is None
    assert seed_prompt.source == AtifStepSource.USER
    assert seed_prompt.message == "Round 1 begins."
    assert seed_call.tool_calls is not None
    assert seed_call.observation is not None
    assert seed_call.observation.results[0].content == "sent"
    assert seed_prompt.is_copied_context and seed_call.is_copied_context
    assert prompt.message == CONTINUE_PROMPT
    assert live.source == AtifStepSource.AGENT
    assert live.is_copied_context is None


SEND_MESSAGE = RecordedToolDefinition(
    name="send_message",
    description="Send a message.",
    input_schema={"type": "object", "properties": {"text": {"type": "string"}}},
)
READ_CHANNEL = RecordedToolDefinition(
    name="read_channel",
    description="Read a channel.",
    input_schema={"type": "object", "properties": {"channel_id": {"type": "string"}}},
)


def test_recorded_tool_definitions_win_over_reconstructed_ones() -> None:
    registration = _registered(agent_id="field_observer", model="claude-sonnet-4-6", seconds=1)
    registration.tool_definitions = [SEND_MESSAGE]
    events: list[SimulationEvent] = [_started(), registration]

    trajectory = _only(
        build_agent_trajectories(
            context=_context(
                events=events, copied_context=NO_COPIED_CONTEXT, reconstructed=[READ_CHANNEL]
            ),
            agent_id="field_observer",
            cutoff_round=None,
        )
    )

    assert trajectory.agent.tool_definitions == [SEND_MESSAGE.model_dump(mode="json")]
    assert trajectory.agent.extra["tool_definitions_source"] == "recorded"


@pytest.mark.parametrize(
    ("reconstructed", "source", "names"),
    [
        ([SEND_MESSAGE, READ_CHANNEL], "reconstructed", ["read_channel", "send_message"]),
        (None, "names_only", ["read_channel", "send_message"]),
    ],
)
def test_a_run_without_recorded_schemas_falls_back(
    reconstructed: list[RecordedToolDefinition] | None,
    source: str,
    names: list[str],
) -> None:
    events: list[SimulationEvent] = [
        _started(),
        _registered(agent_id="field_observer", model="claude-sonnet-4-6", seconds=1),
    ]

    trajectory = _only(
        build_agent_trajectories(
            context=_context(
                events=events, copied_context=NO_COPIED_CONTEXT, reconstructed=reconstructed
            ),
            agent_id="field_observer",
            cutoff_round=None,
        )
    )

    assert [tool["name"] for tool in trajectory.agent.tool_definitions] == names
    assert trajectory.agent.extra["tool_definitions_source"] == source


async def test_a_fork_at_round_manifest_copies_everything_through_its_boundary(
    tmp_path: Path,
) -> None:
    source = _single_agent_run()
    events = _replaced_run(source=source)
    boundary = source[-1]
    manifest = ReplaceManifest(
        source_run_id="veyru/1600000000",
        source_run_dir="runs/veyru/1600000000",
        round_start=3,
        rounds_after_swap=0,
        target_event_id=boundary.event_id,
        replaced_agent_id=None,
        replacement_model=None,
        replacement_provider=None,
        channels_with_visible_history=[],
        blocked_tool_call_channels=[],
        replaced_at=0.0,
    )
    (tmp_path / REPLACE_MANIFEST_FILENAME).write_text(manifest.model_dump_json())

    copied = await load_copied_context(run_dir=tmp_path, events=events)

    assert copied.copied_event_ids == frozenset(event.event_id for event in source)
    assert copied.seeded_agent_id is None


async def test_a_run_without_a_manifest_copies_nothing(tmp_path: Path) -> None:
    assert await load_copied_context(run_dir=tmp_path, events=_single_agent_run()) == (
        NO_COPIED_CONTEXT
    )


async def test_tool_definitions_rebuild_from_a_recorded_config() -> None:
    config = get_scenario_class(name="veyru").load_knobs_preset(preset_name="knobs_default")

    definitions = reconstruct_tool_definitions(scenario_name="veyru", scenario_config=config)

    assert definitions is not None
    by_name = {definition.name: definition for definition in definitions}
    assert "action" in by_name["stabilize_veyru"].input_schema["properties"]
    assert "text" in by_name["send_message"].input_schema["properties"]


async def test_tool_definitions_are_none_for_a_scenario_that_is_not_installed() -> None:
    definitions = reconstruct_tool_definitions(scenario_name="no_such_scenario", scenario_config={})

    assert definitions is None


def test_a_response_is_placed_at_its_tool_call_not_at_when_it_was_logged() -> None:
    """A slow tool returns after later events were logged; the turn still came first."""
    compaction = ContextCompacted(
        agent_id="field_observer",
        provider_name="anthropic",
        summary_char_count=7,
        summary_text="Summary",
        round_number=1,
        timestamp=_at(seconds=5),
    )
    events: list[SimulationEvent] = [
        _started(),
        _registered(agent_id="field_observer", model="claude-sonnet-4-6", seconds=1),
        _invoked(agent_id="field_observer", round_number=1, seconds=3, call_id="slow"),
        compaction,
        _result(agent_id="field_observer", round_number=1, seconds=8, call_id="slow"),
        _response(
            agent_id="field_observer", round_number=1, seconds=8, call_id="slow", usage=ZERO_USAGE
        ),
    ]

    trajectory = _only(_build(events=events, cutoff_round=None))

    _, _, turn, summary = trajectory.steps
    assert turn.source == AtifStepSource.AGENT
    assert turn.timestamp == _at(seconds=3).isoformat()
    assert summary.message == "Summary"


def test_a_tool_named_twice_by_an_older_registration_is_listed_once() -> None:
    registration = _registered(agent_id="field_observer", model="claude-sonnet-4-6", seconds=1)
    registration.tool_names = ["send_message", "read_channel", "send_message"]
    events: list[SimulationEvent] = [_started(), registration]

    trajectory = _only(
        build_agent_trajectories(
            context=_context(
                events=events,
                copied_context=NO_COPIED_CONTEXT,
                reconstructed=[SEND_MESSAGE, READ_CHANNEL],
            ),
            agent_id="field_observer",
            cutoff_round=None,
        )
    )

    assert [tool["name"] for tool in trajectory.agent.tool_definitions] == [
        "send_message",
        "read_channel",
    ]


def test_copied_steps_keep_their_metrics_but_stay_out_of_the_totals() -> None:
    source = _single_agent_run()
    context = _context(
        events=_replaced_run(source=source),
        copied_context=_boundary_context(source=source, seeded=False),
        reconstructed=None,
    )

    trajectory = _only(
        build_agent_trajectories(context=context, agent_id="field_observer", cutoff_round=None)
    )

    assert any(step.metrics is not None for step in trajectory.steps if step.is_copied_context)
    assert trajectory.final_metrics.total_prompt_tokens is None
    assert trajectory.final_metrics.total_cost_usd is None
    assert trajectory.final_metrics.total_steps == len(trajectory.steps)


def test_deliveries_are_not_steps_and_cycles_open_with_the_runner_prompt() -> None:
    """Injections reach the model through read_notifications; its user turns are the runner's."""
    trajectory = _only(_build(events=_single_agent_run(), cutoff_round=None))

    user_steps = [step for step in trajectory.steps if step.source == AtifStepSource.USER]
    assert [step.message for step in user_steps] == [INITIAL_PROMPT, CONTINUE_PROMPT]
    assert [step.extra["kind"] for step in user_steps] == ["initial_prompt", "continue_prompt"]
    assert all("Round" not in step.message for step in user_steps)


def test_a_cycle_closed_by_usage_opens_the_next_with_the_continue_prompt() -> None:
    events: list[SimulationEvent] = [
        _started(),
        _registered(agent_id="field_observer", model="claude-sonnet-4-6", seconds=1),
        _invoked(agent_id="field_observer", round_number=1, seconds=2, call_id="a"),
        _response(
            agent_id="field_observer", round_number=1, seconds=2, call_id="a", usage=ZERO_USAGE
        ),
        _invoked(agent_id="field_observer", round_number=1, seconds=3, call_id="b"),
        _response(
            agent_id="field_observer", round_number=1, seconds=3, call_id="b", usage=CYCLE_USAGE
        ),
        _invoked(agent_id="field_observer", round_number=1, seconds=4, call_id="c"),
        _response(
            agent_id="field_observer", round_number=1, seconds=4, call_id="c", usage=ZERO_USAGE
        ),
    ]

    trajectory = _only(_build(events=events, cutoff_round=None))

    assert [step.source for step in trajectory.steps] == [
        AtifStepSource.SYSTEM,
        AtifStepSource.USER,
        AtifStepSource.AGENT,
        AtifStepSource.AGENT,
        AtifStepSource.USER,
        AtifStepSource.AGENT,
    ]


def test_the_step_closing_a_cycle_counts_the_responses_it_aggregates() -> None:
    events: list[SimulationEvent] = [
        _started(),
        _registered(agent_id="field_observer", model="claude-sonnet-4-6", seconds=1),
        _invoked(agent_id="field_observer", round_number=1, seconds=2, call_id="a"),
        _response(
            agent_id="field_observer", round_number=1, seconds=2, call_id="a", usage=ZERO_USAGE
        ),
        _invoked(agent_id="field_observer", round_number=1, seconds=3, call_id="b"),
        _response(
            agent_id="field_observer", round_number=1, seconds=3, call_id="b", usage=CYCLE_USAGE
        ),
        _invoked(agent_id="field_observer", round_number=1, seconds=4, call_id="c"),
        _response(
            agent_id="field_observer", round_number=1, seconds=4, call_id="c", usage=CYCLE_USAGE
        ),
    ]

    trajectory = _only(_build(events=events, cutoff_round=None))

    agent_steps = [step for step in trajectory.steps if step.source == AtifStepSource.AGENT]
    assert [step.llm_call_count for step in agent_steps] == [None, 2, 1]
    assert all(step.llm_call_count is None for step in trajectory.steps if step not in agent_steps)
    closing_metrics = agent_steps[1].metrics
    assert closing_metrics is not None
    assert "usage_scope" not in closing_metrics.extra


def test_cycles_that_fail_after_the_last_response_are_recorded_on_the_trajectory() -> None:
    events = _single_agent_run() + [
        AgentRunCycleFailed(
            agent_id="field_observer",
            cycle=3,
            error_type="ModelHTTPError",
            message="overloaded",
            round_number=3,
            timestamp=_at(seconds=9),
        ),
    ]

    trajectory = _only(_build(events=events, cutoff_round=None))

    assert trajectory.extra["failed_cycles_after_last_response"] == [
        {"cycle": 3, "error_type": "ModelHTTPError", "message": "overloaded"}
    ]
    plain = _only(_build(events=_single_agent_run(), cutoff_round=None))
    assert "failed_cycles_after_last_response" not in plain.extra


def test_a_swapped_in_generation_opens_with_the_prompt_the_swap_seeded() -> None:
    def swapped(system_prompt: str | None) -> list[SimulationEvent]:
        return _single_agent_run() + [
            AgentSwappedMidRun(
                agent_id="field_observer",
                new_model="gpt-5.4",
                new_provider="openai",
                channel_visibility={},
                system_prompt=system_prompt,
                round_number=3,
                timestamp=_at(seconds=9),
            ),
        ]

    _, with_own = _build(
        events=swapped(system_prompt="You are the new observer."), cutoff_round=None
    )
    _, inherited = _build(events=swapped(system_prompt=None), cutoff_round=None)

    assert with_own.steps[0].message == "You are the new observer."
    assert inherited.steps[0].message == "You are field_observer."


async def test_the_run_id_names_the_scenario_not_the_parent_directory(tmp_path: Path) -> None:
    run_dir = tmp_path / "copied-elsewhere" / "1700000000"
    run_dir.mkdir(parents=True)
    lines = [event.model_dump_json() for event in _single_agent_run()]
    (run_dir / "veyru.jsonl").write_text("\n".join(lines) + "\n")

    context = await load_atif_run_context(run_dir=run_dir, scenario_name="veyru")

    assert context.run_id == "veyru/1700000000"


def test_the_cli_raw_export_writes_atif_from_inside_its_event_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The export command runs on a loop; the zip writer builds ATIF with a loop of its own."""
    run_dir = tmp_path / "runs" / "veyru" / "1700000000"
    run_dir.mkdir(parents=True)
    lines = [event.model_dump_json() for event in _single_agent_run()]
    (run_dir / "veyru.jsonl").write_text("\n".join(lines) + "\n")
    out_dir = tmp_path / "out"
    monkeypatch.setattr(
        "sys.argv",
        [
            "glossogen",
            "export",
            "--runs-dir",
            str(tmp_path / "runs"),
            "--out",
            str(out_dir),
            "--run-id",
            "veyru/1700000000",
            "--raw",
            "--include-atif",
        ],
    )

    main()

    names = set(zipfile.ZipFile(out_dir / "runs.zip").namelist())
    assert "veyru/1700000000/atif/field_observer.json" in names
