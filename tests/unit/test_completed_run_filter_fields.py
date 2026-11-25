"""Tests for ``read_completed_run_filter_fields``.

The runs list's status and agent filters read these fields for every run in the
cohort. They have to equal what the run's full summary reports, and the summary
cache behind them is read again only when it changed.
"""

from pathlib import Path

import pytest

from glossogen.models.agent_model_settings import AgentModelSettings
from glossogen.models.event import AgentRegistered, RunStatus, SimulationEnded, SimulationStarted
from glossogen.run_storage import run_discovery
from glossogen.run_storage.run_discovery import _SummaryCache  # pyright: ignore[reportPrivateUsage]
from glossogen.run_storage.run_discovery import (
    build_summary,
    read_completed_run_filter_fields,
)

SCENARIO = "veyru"


def event_lines(ended: bool) -> bytes:
    """A run's log: start, one agent, and the end when ``ended``."""
    events: list[SimulationStarted | AgentRegistered | SimulationEnded] = [
        SimulationStarted(
            round_number=0,
            run_id="1000000001",
            scenario_name=SCENARIO,
            scenario_description="",
            channel_ids=["link"],
            provider="anthropic",
            scenario_config={"round_count": 15},
        ),
        AgentRegistered(
            round_number=0,
            agent_id="field_observer",
            role_name="Field Observer",
            model="opus",
            provider="anthropic",
            system_prompt="",
            channel_ids=["link"],
            tool_names=["read_channel"],
            model_settings=AgentModelSettings(max_tokens=16384),
        ),
    ]
    if ended:
        events.append(
            SimulationEnded(
                round_number=15,
                reason=RunStatus.KILLED,
                total_messages=0,
                total_cost_usd=0.0,
            )
        )
    return b"".join(event.model_dump_json().encode() + b"\n" for event in events)


def make_run(tmp_path: Path, ended: bool) -> Path:
    """Write one run directory holding only its event log."""
    run_dir = tmp_path / SCENARIO / "1000000001"
    run_dir.mkdir(parents=True)
    (run_dir / f"{SCENARIO}.jsonl").write_bytes(event_lines(ended=ended))
    return run_dir


@pytest.fixture(autouse=True)
def empty_memo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start each test from an empty memo."""
    monkeypatch.setattr(run_discovery, "_FILTER_FIELDS_MEMO", {})


@pytest.fixture(name="cache_reads")
def cache_reads_fixture(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Record each summary-cache read."""
    reads: list[Path] = []
    read = run_discovery._read_summary_cache  # pyright: ignore[reportPrivateUsage]

    def counting(run_dir: Path) -> _SummaryCache | None:
        reads.append(run_dir)
        return read(run_dir=run_dir)

    monkeypatch.setattr(run_discovery, "_read_summary_cache", counting)
    return reads


async def test_a_completed_run_reports_what_its_summary_reports(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path=tmp_path, ended=True)
    # Building the summary of an ended run writes its summary cache.
    summary = await build_summary(
        scenario_name=SCENARIO, timestamp_dir=run_dir, evaluation_content_hash=None
    )
    assert summary is not None

    fields = read_completed_run_filter_fields(scenario_name=SCENARIO, timestamp_dir=run_dir)

    assert fields is not None
    assert fields.status == summary.status == RunStatus.KILLED
    assert fields.agent_ids == {agent.agent_id for agent in summary.agent_models}
    assert fields.scenario_name == summary.scenario_name
    assert fields.timestamp == summary.timestamp


async def test_an_unchanged_cache_is_read_once(tmp_path: Path, cache_reads: list[Path]) -> None:
    run_dir = make_run(tmp_path=tmp_path, ended=True)
    await build_summary(scenario_name=SCENARIO, timestamp_dir=run_dir, evaluation_content_hash=None)
    cache_reads.clear()

    for _ in range(3):
        assert read_completed_run_filter_fields(scenario_name=SCENARIO, timestamp_dir=run_dir)

    assert cache_reads == [run_dir]


async def test_a_rewritten_cache_is_read_on_the_next_call(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path=tmp_path, ended=True)
    await build_summary(scenario_name=SCENARIO, timestamp_dir=run_dir, evaluation_content_hash=None)
    read_completed_run_filter_fields(scenario_name=SCENARIO, timestamp_dir=run_dir)
    cache_path = run_dir / "run_summary_cache.json"
    cache_path.write_bytes(cache_path.read_bytes().replace(b'"killed"', b'"scenario_complete"'))

    fields = read_completed_run_filter_fields(scenario_name=SCENARIO, timestamp_dir=run_dir)

    assert fields is not None
    assert fields.status == RunStatus.SCENARIO_COMPLETE


def test_a_run_that_has_not_ended_has_no_cached_fields(
    tmp_path: Path, cache_reads: list[Path]
) -> None:
    """Its status depends on its manifests, so the caller builds its summary."""
    run_dir = make_run(tmp_path=tmp_path, ended=False)

    assert read_completed_run_filter_fields(scenario_name=SCENARIO, timestamp_dir=run_dir) is None
    assert cache_reads == []


async def test_a_cache_without_its_event_log_is_not_a_run(tmp_path: Path) -> None:
    """``build_summary`` drops a directory whose log is gone, so these fields drop it too."""
    run_dir = make_run(tmp_path=tmp_path, ended=True)
    await build_summary(scenario_name=SCENARIO, timestamp_dir=run_dir, evaluation_content_hash=None)
    (run_dir / f"{SCENARIO}.jsonl").unlink()

    assert read_completed_run_filter_fields(scenario_name=SCENARIO, timestamp_dir=run_dir) is None


def test_a_cache_that_does_not_parse_has_no_cached_fields(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path=tmp_path, ended=True)
    (run_dir / "run_summary_cache.json").write_bytes(b"not json")

    assert read_completed_run_filter_fields(scenario_name=SCENARIO, timestamp_dir=run_dir) is None
