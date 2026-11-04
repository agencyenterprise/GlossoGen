"""What a run records as its spend, end to end.

``SimulationEnded.total_cost_usd`` is the number the runs list, the detail page
and the export show, and nothing checks it against anything else, so a seat or a
process it leaves out is simply missing money. These runs are priced at a flat
$1 per token, which makes each run's true spend the sum of the input and output
tokens its responses logged: a figure the test can work out from the log
without the code under test.
"""

from datetime import datetime
from pathlib import Path
from typing import Any

import orjson
import pytest

from glossogen.evaluation.log_reader import load_events
from glossogen.model_catalog import Provider
from glossogen.models.event import (
    AgentSwappedMidRun,
    LLMResponseReceived,
    RunStatus,
    SimulationEnded,
    SimulationEvent,
)
from glossogen.run_derivation.derived_run_start import derived_run_started_at
from glossogen.run_derivation.replace_agent import ReplaceAgentRequest, prepare_replace_agent_run
from glossogen.run_file_paths import event_log_path
from glossogen.runtime.autonomous_supervisor import AutonomousSupervisor
from glossogen.runtime.scheduled_events import ScheduledEvent, SwapAgent
from glossogen.server.runs.detail_reader import load_run_detail
from glossogen.server.runs.discovery import scan_jsonl
from glossogen.testing.scripted_agent import SayTurn, ScriptedTurn, ToolTurn
from glossogen.testing.simulation_harness import never_times_out, resume_simulation, run_simulation
from glossogen.testing.smoke_scenario import (
    FIRST_AGENT_ID,
    LINK_CHANNEL_ID,
    SECOND_AGENT_ID,
    SmokeKnobs,
    SmokeScenario,
)
from glossogen.token_pricing import TokenPricing

ROUND_COUNT = 2
SUCCESSOR_KEY = "first_agent_successor"
SUCCESSOR_MODEL = f"scripted::{SUCCESSOR_KEY}"

# compute_token_cost_usd divides by a million, so this is $1 per token.
DOLLAR_PER_TOKEN = TokenPricing(
    input_per_mtok=1_000_000.0,
    output_per_mtok=1_000_000.0,
    cache_read_per_mtok=1_000_000.0,
    cache_write_per_mtok=1_000_000.0,
)


def flat_pricing(model: str, provider: str, at: datetime) -> TokenPricing:
    """Price every model at a dollar a token, whatever the catalog says."""
    _ = model, provider, at
    return DOLLAR_PER_TOKEN


@pytest.fixture(autouse=True)
def priced_at_a_dollar_per_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """Price the runner's cycles and every reading of a log the same way."""
    monkeypatch.setattr("glossogen.runners.pydantic_ai_runner.find_pricing", flat_pricing)
    monkeypatch.setattr("glossogen.token_pricing.find_pricing", flat_pricing)


def speak_then_idle(*, text: str) -> list[ScriptedTurn]:
    """One send, then park."""
    return [
        ToolTurn(
            tool_name="send_message",
            args={"channel_id": LINK_CHANNEL_ID, "text": text, "force": True},
        ),
        ToolTurn(tool_name="read_notifications", args={}),
        SayTurn(text="idle"),
    ]


def build_scenario(*, swaps: list[ScheduledEvent]) -> SmokeScenario:
    """The smoke scenario for ``ROUND_COUNT`` rounds, carrying ``swaps``."""
    return SmokeScenario(
        knobs=SmokeKnobs(
            round_count=ROUND_COUNT,
            max_round_duration_seconds=45,
            model_overrides={},
            scheduled_events=swaps,
        )
    )


def logged_tokens(*, events: list[SimulationEvent], since: datetime | None) -> float:
    """The input plus output tokens of every response logged at or after ``since``."""
    total = 0.0
    for event in events:
        if not isinstance(event, LLMResponseReceived):
            continue
        if since is not None and event.timestamp < since:
            continue
        total += event.usage.input_tokens + event.usage.output_tokens
    return total


def last_end(*, events: list[SimulationEvent]) -> SimulationEnded:
    """The log's last ``SimulationEnded``."""
    ends = [event for event in events if isinstance(event, SimulationEnded)]
    assert ends, "the run logged no SimulationEnded"
    return ends[-1]


async def test_a_swapped_seat_keeps_its_predecessors_spend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The successor's runner adds to the seat's spend rather than starting it again.

    Both runners of the seat write to one entry of the supervisor's cost
    tracker. When the successor overwrote it, the predecessor's spend vanished
    from the run's total.
    """
    result = await run_simulation(
        scenario=build_scenario(
            swaps=[
                SwapAgent(
                    at_round=2,
                    agent_id=FIRST_AGENT_ID,
                    model=SUCCESSOR_MODEL,
                    provider=Provider.ANTHROPIC,
                )
            ]
        ),
        scripts={
            FIRST_AGENT_ID: speak_then_idle(text="first"),
            SECOND_AGENT_ID: speak_then_idle(text="second") * ROUND_COUNT,
            SUCCESSOR_KEY: speak_then_idle(text="successor"),
        },
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )

    swap_index = result.first_index(event_type=AgentSwappedMidRun, round_number=None)
    predecessor_tokens = sum(
        event.usage.input_tokens + event.usage.output_tokens
        for event in result.events[:swap_index]
        if isinstance(event, LLMResponseReceived) and event.agent_id == FIRST_AGENT_ID
    )
    assert predecessor_tokens > 0, "the predecessor logged no usage, so nothing is tested"
    assert last_end(events=result.events).total_cost_usd == pytest.approx(
        logged_tokens(events=result.events, since=None)
    )


async def test_a_failed_run_records_what_it_spent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A run that raises still logs the spend its agents ran up before the failure."""

    drain_runners = AutonomousSupervisor._drain_runners  # pyright: ignore[reportPrivateUsage]

    async def drain_then_fail(self: AutonomousSupervisor) -> None:
        await drain_runners(self)
        raise RuntimeError("simulated failure after the agents ran")

    monkeypatch.setattr(AutonomousSupervisor, "_drain_runners", drain_then_fail)
    with pytest.raises(RuntimeError, match="simulated failure"):
        await run_simulation(
            scenario=build_scenario(swaps=[]),
            scripts={
                FIRST_AGENT_ID: speak_then_idle(text="first") * ROUND_COUNT,
                SECOND_AGENT_ID: speak_then_idle(text="second") * ROUND_COUNT,
            },
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            phase_timed_out=never_times_out,
        )

    events = await load_events(log_path=tmp_path / "smoke.jsonl")
    ended = last_end(events=events)
    assert ended.reason is RunStatus.ERROR
    spent = logged_tokens(events=events, since=None)
    assert spent > 0, "the agents logged no usage, so nothing is tested"
    assert ended.total_cost_usd == pytest.approx(spent)


async def test_a_resumed_run_counts_the_spend_before_the_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The resumed process starts from what the log already recorded.

    The first process is cut off before it logs an end, as a killed process
    is, so its spend survives only as the usage on its responses. The resumed
    process's ``SimulationEnded`` is then the only total the log carries, and
    it has to cover both processes.
    """
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    first = await run_simulation(
        scenario=build_scenario(swaps=[]),
        scripts={
            FIRST_AGENT_ID: speak_then_idle(text="first") * ROUND_COUNT,
            SECOND_AGENT_ID: speak_then_idle(text="second") * ROUND_COUNT,
        },
        tmp_path=run_dir,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )
    killed_lines = [
        line
        for line in first.log_path.read_bytes().splitlines()
        if line and orjson.loads(line)["event_type"] != "simulation_ended"
    ]
    log_path = event_log_path(run_dir=run_dir, scenario_name="smoke")
    log_path.write_bytes(b"\n".join(killed_lines) + b"\n")
    spent_before = logged_tokens(events=await load_events(log_path=log_path), since=None)
    assert spent_before > 0, "the first process logged no usage, so nothing is tested"

    resumed = await resume_simulation(
        scenario=build_scenario(swaps=[]),
        scripts={
            FIRST_AGENT_ID: speak_then_idle(text="first-again"),
            SECOND_AGENT_ID: speak_then_idle(text="second-again"),
        },
        run_dir=run_dir,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )

    total = last_end(events=resumed.events).total_cost_usd
    assert total > spent_before
    assert total == pytest.approx(logged_tokens(events=resumed.events, since=None))


async def test_a_fork_counts_only_its_own_spend_on_every_surface(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fork's clone carries its source's responses, usage included, and that is not its spend.

    The fork's own ``SimulationEnded`` never counted them. The runs list and the
    detail page fall back to the log's token usage while the fork is live, or
    when it ended without a total, and that fallback did.
    """
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    await run_simulation(
        scenario=build_scenario(swaps=[]),
        scripts={
            FIRST_AGENT_ID: speak_then_idle(text="src-first") * ROUND_COUNT,
            SECOND_AGENT_ID: speak_then_idle(text="src-second") * ROUND_COUNT,
        },
        tmp_path=source_dir,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )

    def smoke_class(name: str) -> type[SmokeScenario]:
        assert name == "smoke"
        return SmokeScenario

    monkeypatch.setattr("glossogen.run_derivation.replace_agent.get_scenario_class", smoke_class)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    prepared = await prepare_replace_agent_run(
        request=ReplaceAgentRequest(
            source_run_dir=source_dir,
            scenario_name="smoke",
            after_round=1,
            rounds_after=None,
            replaced_agent_id=None,
            model=None,
            provider=None,
            knobs=None,
            channels_with_visible_history=None,
            channel_history_floors={},
            history_floor_round=None,
            runs_dir=tmp_path / "runs",
        )
    )
    fork_log = event_log_path(run_dir=prepared.new_run_dir, scenario_name="smoke")
    cloned_tokens = logged_tokens(events=await load_events(log_path=fork_log), since=None)
    assert cloned_tokens > 0, "the clone carries no source usage, so nothing is tested"

    config: dict[str, Any] = orjson.loads(
        (prepared.new_run_dir / "replace_config.json").read_bytes()
    )
    forked = await resume_simulation(
        scenario=SmokeScenario(knobs=SmokeKnobs.model_validate(config)),
        scripts={
            FIRST_AGENT_ID: speak_then_idle(text="fork-first"),
            SECOND_AGENT_ID: speak_then_idle(text="fork-second"),
        },
        run_dir=prepared.new_run_dir,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )
    own_tokens = logged_tokens(
        events=forked.events, since=derived_run_started_at(run_dir=prepared.new_run_dir)
    )
    assert own_tokens > 0, "the fork logged no usage of its own, so nothing is tested"
    assert last_end(events=forked.events).total_cost_usd == pytest.approx(own_tokens)

    # The same fork, seen live: drop its end so the surfaces read the token usage.
    live_lines = [
        line
        for line in fork_log.read_bytes().splitlines()
        if line and orjson.loads(line)["event_type"] != "simulation_ended"
    ]
    fork_log.write_bytes(b"\n".join(live_lines) + b"\n")
    listed = await scan_jsonl(file_path=fork_log)
    detail = await load_run_detail(log_path=fork_log, children=[])
    assert listed.cost_usd == pytest.approx(own_tokens)
    assert detail.total_cost_usd == pytest.approx(own_tokens)
    assert detail.agent_token_usage.input_tokens + detail.agent_token_usage.output_tokens == (
        pytest.approx(own_tokens)
    )
