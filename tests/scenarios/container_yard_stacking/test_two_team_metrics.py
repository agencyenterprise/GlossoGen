"""What a two-team yard run reports to the char and language metrics.

Those metrics read the channels the scenario names as primary. A name that no
channel answers to costs nothing at run time and everything at evaluation: the
run completes, the report is written, and the throughput figures are absent
rather than wrong, which is the harder kind to notice.
"""

from pathlib import Path

import pytest

from glossogen.evaluation.log_reader import load_events
from glossogen.evaluation.metrics.mcr_metric import MCRMetric
from tests.fakes.stub_llm_provider import StubLLMProvider
from tests.scenarios.scenario_runtime import run_rounds
from tests.testbed.metric_harness import NO_OPTIONS

SCENARIO = "container_yard_stacking"

pytestmark = pytest.mark.xdist_group(SCENARIO)


@pytest.mark.asyncio
async def test_two_team_mode_meters_each_team_link(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both links are named, so throughput is reported once per team.

    Two-team mode used to name `link`, the solo channel, which exists in
    neither team. Every metric keyed on primary channels then had nothing to
    read and emitted no measurement at all.
    """
    result = await run_rounds(
        scenario_name=SCENARIO,
        round_count=2,
        overrides={"two_teams": True},
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    assert [(c.channel_id, c.team_id) for c in result.scenario.get_primary_channels()] == [
        ("link_a", "team_a"),
        ("link_b", "team_b"),
    ]

    events = await load_events(log_path=result.log_path)
    measurements = await MCRMetric().compute(
        events=events,
        agent_configs=[],
        scenario=result.scenario,
        # MCR reads neither; both are on the Metric contract.
        llm_provider=StubLLMProvider(),
        run_dir=tmp_path,
        options=NO_OPTIONS,
    )

    assert sorted(m.metric_name for m in measurements) == [
        "mean_chars_per_round_team_a",
        "mean_chars_per_round_team_b",
    ]
    assert all(m.score > 0 for m in measurements), "a metered link reported no characters"
