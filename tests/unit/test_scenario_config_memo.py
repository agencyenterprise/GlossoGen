"""Tests that ``read_scenario_config`` reads a run's files again only when one changed.

A knob filter reads the config of every run in the cohort on every request, so
the answer is remembered against the stamps of the files it comes from. These
tests count the reads behind it and check that a change to each source file
reaches the next answer.
"""

from pathlib import Path
from typing import Any

import orjson
import pytest

from glossogen.models.event import RunStatus, SimulationEnded, SimulationStarted
from glossogen.run_storage import run_discovery
from glossogen.run_storage.run_discovery import build_summary, read_scenario_config

SCENARIO = "veyru"


def started_line(round_count: int) -> bytes:
    """The first event of a run recording ``round_count``."""
    return (
        SimulationStarted(
            round_number=0,
            run_id="1000000001",
            scenario_name=SCENARIO,
            scenario_description="",
            channel_ids=["link"],
            provider="anthropic",
            scenario_config={"round_count": round_count},
        )
        .model_dump_json()
        .encode()
    )


ENDED_LINE = (
    SimulationEnded(
        round_number=15,
        reason=RunStatus.SCENARIO_COMPLETE,
        total_messages=0,
        total_cost_usd=0.0,
    )
    .model_dump_json()
    .encode()
)


@pytest.fixture(name="run_dir")
def run_dir_fixture(tmp_path: Path) -> Path:
    """A run that has not ended, so it has a log and no summary cache."""
    run_dir = tmp_path / SCENARIO / "1000000001"
    run_dir.mkdir(parents=True)
    (run_dir / f"{SCENARIO}.jsonl").write_bytes(started_line(round_count=15) + b"\n")
    return run_dir


@pytest.fixture(name="disk_reads")
def disk_reads_fixture(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Start from an empty memo and record each run directory read from disk."""
    monkeypatch.setattr(run_discovery, "_SCENARIO_CONFIG_MEMO", {})
    reads: list[Path] = []
    uncached = run_discovery._read_scenario_config_uncached  # pyright: ignore[reportPrivateUsage]

    def counting(scenario_name: str, timestamp_dir: Path) -> dict[str, Any] | None:
        reads.append(timestamp_dir)
        return uncached(scenario_name=scenario_name, timestamp_dir=timestamp_dir)

    monkeypatch.setattr(run_discovery, "_read_scenario_config_uncached", counting)
    return reads


def test_an_unchanged_run_is_read_from_disk_once(run_dir: Path, disk_reads: list[Path]) -> None:
    for _ in range(3):
        config = read_scenario_config(scenario_name=SCENARIO, timestamp_dir=run_dir)
        assert config == {"round_count": 15}

    assert disk_reads == [run_dir]


def test_a_write_to_the_event_log_is_read_on_the_next_call(
    run_dir: Path, disk_reads: list[Path]
) -> None:
    read_scenario_config(scenario_name=SCENARIO, timestamp_dir=run_dir)
    (run_dir / f"{SCENARIO}.jsonl").write_bytes(started_line(round_count=150) + b"\n")

    config = read_scenario_config(scenario_name=SCENARIO, timestamp_dir=run_dir)

    assert config == {"round_count": 150}
    assert len(disk_reads) == 2


def test_a_new_replace_config_is_read_on_the_next_call(
    run_dir: Path, disk_reads: list[Path]
) -> None:
    read_scenario_config(scenario_name=SCENARIO, timestamp_dir=run_dir)
    (run_dir / "replace_config.json").write_bytes(orjson.dumps({"round_count": 20}))

    config = read_scenario_config(scenario_name=SCENARIO, timestamp_dir=run_dir)

    assert config == {"round_count": 20}
    assert len(disk_reads) == 2


async def test_a_run_that_ends_is_read_again_from_its_new_summary_cache(
    run_dir: Path, disk_reads: list[Path]
) -> None:
    read_scenario_config(scenario_name=SCENARIO, timestamp_dir=run_dir)
    log = run_dir / f"{SCENARIO}.jsonl"
    log.write_bytes(log.read_bytes() + ENDED_LINE + b"\n")
    # Building the summary of an ended run writes its summary cache.
    await build_summary(scenario_name=SCENARIO, timestamp_dir=run_dir, evaluation_content_hash=None)
    assert (run_dir / "run_summary_cache.json").exists()

    read_scenario_config(scenario_name=SCENARIO, timestamp_dir=run_dir)
    read_scenario_config(scenario_name=SCENARIO, timestamp_dir=run_dir)

    assert len(disk_reads) == 2


def test_a_log_that_cannot_be_read_is_remembered_until_it_changes(
    run_dir: Path, disk_reads: list[Path]
) -> None:
    log = run_dir / f"{SCENARIO}.jsonl"
    log.write_bytes(b"not json\n")
    assert read_scenario_config(scenario_name=SCENARIO, timestamp_dir=run_dir) is None
    assert read_scenario_config(scenario_name=SCENARIO, timestamp_dir=run_dir) is None
    assert len(disk_reads) == 1

    log.write_bytes(started_line(round_count=15) + b"\n")

    assert read_scenario_config(scenario_name=SCENARIO, timestamp_dir=run_dir) == {
        "round_count": 15
    }
    assert len(disk_reads) == 2


def test_a_directory_without_a_log_is_not_a_run(tmp_path: Path, disk_reads: list[Path]) -> None:
    empty = tmp_path / SCENARIO / "1000000002"
    empty.mkdir(parents=True)

    assert read_scenario_config(scenario_name=SCENARIO, timestamp_dir=empty) is None
    assert disk_reads == []
