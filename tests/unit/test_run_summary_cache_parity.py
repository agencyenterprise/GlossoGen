"""A completed run's summary reads the same from its JSONL as from its summary cache.

The first listing of a completed run scans its JSONL and writes
``run_summary_cache.json``; every later listing reads the cache instead. The two
must agree on every field, or a run would change in the list the second time it
was shown.
"""

from pathlib import Path

import orjson

from glossogen.evaluation.metric_core.measurement import Measurement
from glossogen.evaluation.reports.evaluation_report import EvaluationReport, write_report
from glossogen.models.agent_model_settings import AgentModelSettings
from glossogen.models.event import (
    AgentRegistered,
    RunStatus,
    SimulationEnded,
    SimulationStarted,
)
from glossogen.server.runs.discovery import build_summary
from glossogen.server.runs.models import RunSummary
from tests.fakes.export_run_records import ZERO_COST


def _write_completed_run(run_dir: Path) -> None:
    """Write a finished run with labels, a note, a report and a config overlay."""
    run_dir.mkdir(parents=True)
    events = [
        SimulationStarted(
            round_number=0,
            run_id=run_dir.name,
            scenario_name="smoke",
            scenario_description="parity run",
            channel_ids=["link"],
            provider="anthropic",
            scenario_config={"round_count": 3, "seed": 42},
        ),
        AgentRegistered(
            round_number=0,
            agent_id="first_agent",
            role_name="First Agent",
            model="claude-sonnet-4-6",
            provider="anthropic",
            system_prompt="",
            channel_ids=["link"],
            tool_names=["read_channel"],
            model_settings=AgentModelSettings(max_tokens=16384),
        ),
        SimulationEnded(
            round_number=3,
            reason=RunStatus.SCENARIO_COMPLETE,
            total_messages=7,
            total_cost_usd=0.25,
        ),
    ]
    (run_dir / "smoke.jsonl").write_bytes(
        b"\n".join(event.model_dump_json().encode() for event in events) + b"\n"
    )
    (run_dir / "labels.json").write_bytes(orjson.dumps(["baseline"]))
    (run_dir / "note.md").write_text("a note")
    (run_dir / "replace_config.json").write_bytes(orjson.dumps({"seed": 7}))


async def _summary(run_dir: Path) -> RunSummary:
    summary = await build_summary(
        scenario_name="smoke",
        timestamp_dir=run_dir,
        evaluation_content_hash="abc123",
    )
    assert summary is not None
    return summary


async def test_a_completed_run_reads_the_same_from_its_cache(tmp_path: Path) -> None:
    run_dir = tmp_path / "1700000000"
    _write_completed_run(run_dir=run_dir)
    await write_report(
        report=EvaluationReport(
            simulation_id="smoke/1700000000",
            scenario_name="smoke",
            measurements=[
                Measurement(
                    metric_name="round_success",
                    score=0.5,
                    score_unit="fraction",
                    summary="half",
                    per_round=[],
                    per_agent=[],
                )
            ],
            evaluation_cost=ZERO_COST,
        ),
        report_path=run_dir / "smoke_report.json",
    )

    scanned = await _summary(run_dir=run_dir)
    assert (run_dir / "run_summary_cache.json").exists()
    cached = await _summary(run_dir=run_dir)

    assert cached == scanned
    assert scanned.scenario_config == {"round_count": 3, "seed": 7}
    assert scanned.labels == ["baseline"]
    assert scanned.has_note
    assert scanned.has_evaluation
    assert scanned.evaluation_content_hash == "abc123"


async def test_a_forked_run_reads_the_same_from_its_cache(tmp_path: Path) -> None:
    run_dir = tmp_path / "1700000000"
    _write_completed_run(run_dir=run_dir)
    (run_dir / "fork_manifest.json").write_bytes(
        orjson.dumps(
            {
                "source_run_id": "smoke/1600000000",
                "target_message_id": "message-1",
                "forked_at": 1700000000.0,
            }
        )
    )

    scanned = await _summary(run_dir=run_dir)
    cached = await _summary(run_dir=run_dir)

    assert cached == scanned
    assert scanned.fork_source is not None
    assert not scanned.has_evaluation
