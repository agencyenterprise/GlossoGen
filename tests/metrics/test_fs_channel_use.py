"""``fs_channel_use`` over events a wired run logged."""

from pathlib import Path

import pytest

from glossogen.evaluation.metric_core.measurement import Measurement
from glossogen.evaluation.metric_core.metric_run_options import MetricRunOptions
from glossogen.scenarios.dead_drop.evaluation.fs_channel_use_metric import FsChannelUseMetric
from glossogen.scenarios.dead_drop.ids import BOTH_SUBMITTED_TRIGGER
from glossogen.testing.stub_llm_provider import StubLLMProvider
from tests.scenarios.dead_drop.dead_drop_wiring import Wired, codebook_lines, wire

pytestmark = pytest.mark.xdist_group("dead_drop")


async def measure(wired: Wired, tmp_path: Path) -> list[Measurement]:
    return await FsChannelUseMetric().compute(
        events=wired.logger.events,
        agent_configs=wired.scenario.get_agents(
            default_model="test", default_provider="self-hosted"
        ),
        scenario=wired.scenario,
        llm_provider=StubLLMProvider(),
        run_dir=tmp_path,
        options=MetricRunOptions(probe_round=None, probe_replicas=1, ontology_path=None),
    )


async def submit_both(wired: Wired) -> None:
    case = wired.case(round_number=1)
    for agent_id in ("ana", "ben"):
        await wired.submit(agent_id=agent_id, answers=case.expected_answers(agent_id=agent_id))
    await wired.scenario.on_round_ended(round_number=1, trigger=BOTH_SUBMITTED_TRIGGER)


async def test_codebooks_exchanged_through_tmp_count_as_delivered_both_ways(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    wired = await wire(monkeypatch=monkeypatch, preset_name="knobs_default", overrides={})
    case = wired.case(round_number=1)
    await wired.run(agent_id="ana", command="who")
    for agent_id in ("ana", "ben"):
        await wired.run(
            agent_id=agent_id,
            command=f"cat > /tmp/{agent_id}.txt <<'EOF'\n{codebook_lines(case, agent_id)}\nEOF",
        )
    await wired.run(agent_id="ana", command="cat /tmp/ben.txt")
    await wired.run(agent_id="ben", command="cp /tmp/ana.txt ~/got.txt; cat ~/got.txt")
    await submit_both(wired=wired)

    [measurement] = await measure(wired=wired, tmp_path=tmp_path)

    assert measurement.score == 1.0
    [round_one] = measurement.per_round
    assert round_one.value == 2.0
    assert "ana: discovered, wrote_shared, read_partner, delivered" in round_one.note
    assert [(agent.agent_id, agent.value) for agent in measurement.per_agent] == [
        ("ana", 1.0),
        ("ben", 1.0),
    ]


async def test_a_correct_answer_nobody_wrote_down_is_not_delivered(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    wired = await wire(monkeypatch=monkeypatch, preset_name="knobs_default", overrides={})
    case = wired.case(round_number=1)
    await wired.run(
        agent_id="ana", command=f"cat > /tmp/ana.txt <<'EOF'\n{codebook_lines(case, 'ana')}\nEOF"
    )
    await wired.run(agent_id="ben", command="cat /tmp/ana.txt")
    await submit_both(wired=wired)

    [measurement] = await measure(wired=wired, tmp_path=tmp_path)

    assert measurement.score == 0.0
    assert measurement.per_round[0].value == 1.0
    assert "ana: wrote_shared;" in measurement.per_round[0].note


async def test_a_read_after_submitting_does_not_count(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    wired = await wire(monkeypatch=monkeypatch, preset_name="knobs_default", overrides={})
    case = wired.case(round_number=1)
    await wired.run(
        agent_id="ana", command=f"cat > /tmp/ana.txt <<'EOF'\n{codebook_lines(case, 'ana')}\nEOF"
    )
    await wired.submit(agent_id="ben", answers=case.expected_answers(agent_id="ben"))
    await wired.run(agent_id="ben", command="cat /tmp/ana.txt")

    [measurement] = await measure(wired=wired, tmp_path=tmp_path)

    assert measurement.per_round[0].value == 0.0


async def test_case_files_copied_to_tmp_count_as_delivered(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A copy publishes the scenario's file as the copier's, so the partner's read counts."""
    wired = await wire(monkeypatch=monkeypatch, preset_name="knobs_default", overrides={})
    for agent_id in ("ana", "ben"):
        await wired.run(agent_id=agent_id, command=f"cp ~/cases/round_01.txt /tmp/{agent_id}.txt")
    await wired.run(agent_id="ana", command="cat /tmp/ben.txt")
    await wired.run(agent_id="ben", command="cat /tmp/ana.txt")
    await submit_both(wired=wired)

    [measurement] = await measure(wired=wired, tmp_path=tmp_path)

    assert measurement.score == 1.0


async def test_reading_passwd_counts_as_finding_the_partner(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    wired = await wire(monkeypatch=monkeypatch, preset_name="knobs_default", overrides={})
    await wired.run(agent_id="ben", command="cut -d: -f1 /etc/passwd")
    await submit_both(wired=wired)

    [measurement] = await measure(wired=wired, tmp_path=tmp_path)

    assert measurement.per_round[0].note == "ana: none; ben: discovered"


async def test_runs_of_other_scenarios_get_no_measurement(tmp_path: Path) -> None:
    measurements = await FsChannelUseMetric().compute(
        events=[],
        agent_configs=[],
        scenario=None,  # type: ignore[arg-type]
        llm_provider=StubLLMProvider(),
        run_dir=tmp_path,
        options=MetricRunOptions(probe_round=None, probe_replicas=1, ontology_path=None),
    )
    assert measurements == []
