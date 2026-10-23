"""veyru's stabilize_veyru tool, driven with its judge stubbed.

The executor is where the scenario mutates its world, spends budget, records
its verdict event and decides the round. Nothing else in the suite enters it,
so a break here surfaces as a run that completes and reports a wrong number.

The assertion is on the recorded verdict event rather than the round outcome.
A round can need several judged actions before it is won, so the round result
cannot tell "the judge said no" apart from "the work is not finished yet".
"""

from pathlib import Path
from typing import Any

import pytest

from glossogen.evaluation.reports.evaluation_cost import (
    EvaluationTokenUsage,
    compute_evaluation_cost,
)
from glossogen.models.event import SimulationEnded
from glossogen.scenarios.veyru.events import VeyruStabilizationJudged
from glossogen.scenarios.veyru.knobs import VeyruKnobs
from glossogen.scenarios.veyru.stabilization_judge import StabilizationJudgment
from tests.scenarios.custom_tool_harness import (
    assert_the_tool_ran,
    call_tool,
    round_verdicts,
    stub_the_judge,
)

SCENARIO = "veyru"
TOOL = "stabilize_veyru"
CALLER = "field_observer"
ARGS: dict[str, Any] = {"action": "apply the stabilization the engineer described"}
OVERRIDES: dict[str, Any] = {"postmortem_after_swap": False}
JUDGED_EVENT = VeyruStabilizationJudged

pytestmark = pytest.mark.xdist_group(SCENARIO)


def verdict(*, met: bool) -> StabilizationJudgment:
    """Build a judge verdict where every criterion is ``met``."""
    return StabilizationJudgment(match=met, explanation="stubbed")


async def test_a_passing_judgement_is_recorded_as_a_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The executor turns the judge's answer into an event; this is that wiring."""
    stub = stub_the_judge(monkeypatch=monkeypatch, verdict=verdict(met=True))

    result = await call_tool(
        scenario_name=SCENARIO,
        caller_agent_id=CALLER,
        tool_name=TOOL,
        args=ARGS,
        overrides=OVERRIDES,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    assert_the_tool_ran(result=result, tool_name=TOOL)
    assert stub.calls, "the tool reached a verdict without consulting its judge"
    judged = result.of_type(event_type=JUDGED_EVENT)
    assert judged, f"the tool ran but logged no {JUDGED_EVENT.__name__}"
    assert judged[-1].judge_match is True, "a passing judgement was recorded as a failure"


async def test_a_failing_judgement_is_recorded_and_loses_the_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The mirror case. Without it, a tool hardcoded to pass still looks correct."""
    stub = stub_the_judge(monkeypatch=monkeypatch, verdict=verdict(met=False))

    result = await call_tool(
        scenario_name=SCENARIO,
        caller_agent_id=CALLER,
        tool_name=TOOL,
        args=ARGS,
        overrides=OVERRIDES,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    assert_the_tool_ran(result=result, tool_name=TOOL)
    assert stub.calls, "the tool refused the action without consulting its judge"
    judged = result.of_type(event_type=JUDGED_EVENT)
    assert judged, f"the tool ran but logged no {JUDGED_EVENT.__name__}"
    assert judged[-1].judge_match is False, "a failing judgement was recorded as a pass"
    assert round_verdicts(result=result) == [False], "a refused action still won the round"


async def test_the_judges_spend_is_billed_to_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The run's cost used to count only the agents, so every judge call was free."""
    stub = stub_the_judge(monkeypatch=monkeypatch, verdict=verdict(met=True))
    usage = EvaluationTokenUsage(
        input_tokens=50_000,
        output_tokens=2_000,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )
    stub._record_usage(  # pyright: ignore[reportPrivateUsage]
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )

    result = await call_tool(
        scenario_name=SCENARIO,
        caller_agent_id=CALLER,
        tool_name=TOOL,
        args=ARGS,
        overrides=OVERRIDES,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    assert stub.calls, "the judge was never consulted, so it has nothing to bill"
    knobs = result.scenario.get_knobs()
    assert isinstance(knobs, VeyruKnobs)
    judge_cost = compute_evaluation_cost(
        usage=usage,
        model=knobs.judge_model,
        provider_name=knobs.judge_provider,
        model_settings=knobs.judge_model_settings,
    ).estimated_cost_usd
    assert judge_cost > 0
    ended = result.of_type(event_type=SimulationEnded)
    # The scripted agents run under a model with no price, so the run's whole
    # cost is the judge's.
    assert ended[-1].total_cost_usd == pytest.approx(judge_cost)
