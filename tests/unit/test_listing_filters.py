"""The paginated listing and the export listing agree on what a filter means.

Both call `_apply_descriptor_filters`, and both then apply the enriched filters on
their own. That shared helper is the reason the two are supposed to agree, and this
is the test that says they do: for each filter, the run-id set the runs list would
show is the set an export of the same filter covers.

Without it the extraction is only an intention. The export router's tests stub
resolution out, so nothing else reaches this.

Driven with `pool=None`, which is the no-database path: descriptors come from a
filesystem walk of the runs directory built here.
"""

from pathlib import Path
from typing import NamedTuple
from uuid import uuid4

import orjson
import pytest

from glossogen.models.event import (
    AgentRegistered,
    RunStatus,
    SimulationEnded,
    SimulationStarted,
)
from glossogen.server.runs.listing import list_runs_matching_filters, list_runs_page

SCENARIOS = ("veyru", "spot_the_difference")
GROUP_ID = uuid4()


def started(run_id: str, scenario_name: str) -> SimulationStarted:
    """The first event of a run."""
    return SimulationStarted(
        round_number=0,
        run_id=run_id,
        scenario_name=scenario_name,
        scenario_description="",
        channel_ids=["link"],
        provider="anthropic",
        scenario_config={"round_count": 15},
    )


ENDED = SimulationEnded(
    round_number=15,
    reason=RunStatus.SCENARIO_COMPLETE,
    total_messages=3,
    total_cost_usd=0.5,
)


def registered(agent_id: str) -> AgentRegistered:
    """One agent registration, so `contains_agent_id` has something to match."""
    return AgentRegistered(
        round_number=0,
        agent_id=agent_id,
        role_name=agent_id.replace("_", " ").title(),
        model="opus",
        provider="anthropic",
        system_prompt="",
        channel_ids=["link"],
        tool_names=["read_channel"],
        max_tokens=16384,
    )


def write_run(
    runs_dir: Path,
    scenario_name: str,
    run_dir_name: str,
    labels: list[str],
    agent_id: str,
    finished: bool,
) -> None:
    """Write one run directory the discovery walk can read."""
    run_dir = runs_dir / scenario_name / run_dir_name
    run_dir.mkdir(parents=True)
    events = [
        started(run_id=run_dir_name, scenario_name=scenario_name).model_dump_json().encode(),
        registered(agent_id=agent_id).model_dump_json().encode(),
    ]
    if finished:
        events.append(ENDED.model_dump_json().encode())
    (run_dir / f"{scenario_name}.jsonl").write_bytes(b"\n".join(events) + b"\n")
    (run_dir / "labels.json").write_bytes(orjson.dumps(labels))


@pytest.fixture(name="runs_dir")
def runs_dir_fixture(tmp_path: Path) -> Path:
    """Runs across two scenarios, two label sets, two agents, and two statuses."""
    runs_dir = tmp_path / "runs"
    write_run(
        runs_dir=runs_dir,
        scenario_name="veyru",
        run_dir_name="1000000001",
        labels=["baseline_oss", "budget=800"],
        agent_id="field_observer",
        finished=True,
    )
    write_run(
        runs_dir=runs_dir,
        scenario_name="veyru",
        run_dir_name="1000000002",
        labels=["baseline_oss"],
        agent_id="stabilization_engineer",
        finished=False,
    )
    write_run(
        runs_dir=runs_dir,
        scenario_name="spot_the_difference",
        run_dir_name="1000000003",
        labels=["budget=800"],
        agent_id="field_observer",
        finished=True,
    )
    return runs_dir


class Filters(NamedTuple):
    """One filter set, spelled out, so both listings are called identically."""

    name: str
    scenarios: list[str]
    labels: list[str]
    run_id_contains: str | None
    status: RunStatus | None
    contains_agent_id: str | None


def filters(
    name: str,
    scenarios: list[str] | None = None,
    labels: list[str] | None = None,
    run_id_contains: str | None = None,
    status: RunStatus | None = None,
    contains_agent_id: str | None = None,
) -> Filters:
    """Build a filter set, leaving the ones not named empty."""
    return Filters(
        name=name,
        scenarios=scenarios if scenarios is not None else [],
        labels=labels if labels is not None else [],
        run_id_contains=run_id_contains,
        status=status,
        contains_agent_id=contains_agent_id,
    )


FILTERS: list[Filters] = [
    filters(name="none"),
    filters(name="one-scenario", scenarios=["veyru"]),
    filters(name="two-scenarios", scenarios=list(SCENARIOS)),
    filters(name="one-label", labels=["baseline_oss"]),
    filters(name="label-and", labels=["baseline_oss", "budget=800"]),
    filters(name="substring", run_id_contains="spot"),
    filters(name="substring-uppercase", run_id_contains="SPOT"),
    filters(name="substring-digits", run_id_contains="0000000"),
    filters(name="status-complete", status=RunStatus.SCENARIO_COMPLETE),
    filters(name="status-running", status=RunStatus.IN_PROGRESS),
    filters(name="agent", contains_agent_id="field_observer"),
    filters(name="agent-other", contains_agent_id="stabilization_engineer"),
    filters(name="scenario-and-label", scenarios=["veyru"], labels=["baseline_oss"]),
    filters(name="scenario-and-status", scenarios=["veyru"], status=RunStatus.SCENARIO_COMPLETE),
    filters(name="label-and-agent", labels=["budget=800"], contains_agent_id="field_observer"),
]


@pytest.mark.parametrize("chosen", FILTERS, ids=lambda f: f.name)
async def test_the_two_listings_select_the_same_runs(runs_dir: Path, chosen: Filters) -> None:
    """Any selection the runs list can show is one an export of it reproduces."""
    page = await list_runs_page(
        pool=None,
        runs_dir=runs_dir,
        group_id=GROUP_ID,
        scenarios=chosen.scenarios,
        labels=chosen.labels,
        run_id_contains=chosen.run_id_contains,
        status=chosen.status,
        contains_agent_id=chosen.contains_agent_id,
        cursor=None,
        limit=100,
    )
    exported = await list_runs_matching_filters(
        pool=None,
        runs_dir=runs_dir,
        group_id=GROUP_ID,
        scenarios=chosen.scenarios,
        labels=chosen.labels,
        run_id_contains=chosen.run_id_contains,
        status=chosen.status,
        contains_agent_id=chosen.contains_agent_id,
    )

    assert {run.run_id for run in page.runs} == {run.run_id for run in exported}
    assert page.total == len(exported)


async def test_the_export_listing_is_newest_first(runs_dir: Path) -> None:
    """It shares the paginated listing's order, so a caller can rely on either."""
    exported = await list_runs_matching_filters(
        pool=None,
        runs_dir=runs_dir,
        group_id=GROUP_ID,
        scenarios=[],
        labels=[],
        run_id_contains=None,
        status=None,
        contains_agent_id=None,
    )
    timestamps = [run.timestamp for run in exported]
    assert timestamps == sorted(timestamps, reverse=True)


async def test_a_filter_matching_nothing_returns_nothing(runs_dir: Path) -> None:
    """The empty result is a real answer, and both paths have to give it."""
    missing = ["no_such_label"]
    page = await list_runs_page(
        pool=None,
        runs_dir=runs_dir,
        group_id=GROUP_ID,
        scenarios=[],
        labels=missing,
        run_id_contains=None,
        status=None,
        contains_agent_id=None,
        cursor=None,
        limit=100,
    )
    exported = await list_runs_matching_filters(
        pool=None,
        runs_dir=runs_dir,
        group_id=GROUP_ID,
        scenarios=[],
        labels=missing,
        run_id_contains=None,
        status=None,
        contains_agent_id=None,
    )

    assert page.runs == []
    assert exported == []
