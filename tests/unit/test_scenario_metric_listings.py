"""Which metrics the REST and MCP surfaces offer for each scenario, and accept.

A scenario's own metrics are offered for that scenario and no other. The REST
scenario list and the MCP ``list_scenarios`` tool are what the run-launch and
evaluation pickers read, and the REST evaluate endpoint validates against the
same per-scenario list. A metric listed under the wrong scenario is offered to a
researcher and then fails inside the evaluation subprocess, where nobody sees it.

Driven through the app with no database, as the knob-filter HTTP tests are. The
evaluate endpoint launches a subprocess when it accepts a request, so
``subprocess.Popen`` is replaced with a recorder: nothing is launched whatever
the endpoint decides.
"""

from pathlib import Path

import httpx
import pytest

from glossogen.evaluation.metric_core.generic_metric_names import GENERIC_METRIC_NAMES
from glossogen.evaluation.metric_core.metric_entry_points import METRIC_ENTRY_POINT_GROUP
from glossogen.models.event import RunStatus, SimulationEnded, SimulationStarted
from glossogen.scenario_registry import SCENARIO_REGISTRY
from glossogen.scenarios.signal_game.scenario import SignalGameScenario
from glossogen.server.mcp.browser import _tool_list_scenarios  # pyright: ignore[reportPrivateUsage]
from tests.fakes.evaluation_launches import RecordedLaunch, record_evaluation_launches
from tests.fakes.local_app import build_local_app, local_client
from tests.unit.test_scenario_loader import declare_in_groups

GROUP = "local"
RUN_DIR_NAME = "1700000000"
SIGNAL_GAME_METRICS = {metric_cls.name for metric_cls in SignalGameScenario.scenario_metrics()}


def write_finished_run(runs_dir: Path, scenario_name: str) -> None:
    """Write a run directory whose log says the simulation started and completed."""
    run_dir = runs_dir / scenario_name / RUN_DIR_NAME
    run_dir.mkdir(parents=True)
    started = SimulationStarted(
        round_number=0,
        run_id=f"{scenario_name}/{RUN_DIR_NAME}",
        scenario_name=scenario_name,
        scenario_description="",
        channel_ids=[],
        scenario_config={},
        provider="anthropic",
    )
    ended = SimulationEnded(
        round_number=1,
        reason=RunStatus.SCENARIO_COMPLETE,
        total_messages=0,
        total_cost_usd=0.0,
    )
    lines = [started.model_dump_json(), ended.model_dump_json()]
    (run_dir / f"{scenario_name}.jsonl").write_text("\n".join(lines) + "\n")


@pytest.fixture(name="runs_dir")
def runs_dir_fixture(tmp_path: Path) -> Path:
    """An empty runs directory under the test's own temp dir."""
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    return runs_dir


@pytest.fixture(name="client")
def client_fixture(runs_dir: Path) -> httpx.AsyncClient:
    """An HTTP client bound to the app, with no network involved."""
    return local_client(app=build_local_app(runs_dir=runs_dir))


@pytest.fixture(name="launches")
def launches_fixture(monkeypatch: pytest.MonkeyPatch) -> list[RecordedLaunch]:
    """Record evaluation launches instead of starting a process."""
    return record_evaluation_launches(monkeypatch=monkeypatch)


@pytest.fixture(autouse=True)
def nothing_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    """No external scenario or metric, so the lists hold only what ships here."""
    declare_in_groups(monkeypatch, {METRIC_ENTRY_POINT_GROUP: []})


async def test_the_scenario_list_offers_signal_games_metrics_on_signal_game_only(
    client: httpx.AsyncClient,
) -> None:
    async with client:
        response = await client.get(f"/api/g/{GROUP}/scenarios")

    assert response.status_code == 200
    offered = {
        info["scenario_name"]: set(info["available_metrics"])
        for info in response.json()["scenarios"]
    }
    assert set(SCENARIO_REGISTRY) <= set(offered)
    for name, metrics in offered.items():
        assert set(GENERIC_METRIC_NAMES) <= metrics, name
        if name == "signal_game":
            assert SIGNAL_GAME_METRICS <= metrics
        else:
            assert not SIGNAL_GAME_METRICS & metrics, f"{name} offers signal_game's metrics"


async def test_the_mcp_listing_offers_signal_games_metrics_on_signal_game_only() -> None:
    result = await _tool_list_scenarios()

    offered = {scenario.name: set(scenario.metrics) for scenario in result.scenarios}
    assert set(SCENARIO_REGISTRY) <= set(offered)
    for name, metrics in offered.items():
        assert set(GENERIC_METRIC_NAMES) <= metrics, name
        if name == "signal_game":
            assert SIGNAL_GAME_METRICS <= metrics
        else:
            assert not SIGNAL_GAME_METRICS & metrics, f"{name} offers signal_game's metrics"


async def test_evaluating_another_scenarios_metric_is_a_422(
    client: httpx.AsyncClient, runs_dir: Path, launches: list[RecordedLaunch]
) -> None:
    """Refused at the request, before a subprocess would fail on it unseen."""
    write_finished_run(runs_dir=runs_dir, scenario_name="veyru")

    async with client:
        response = await client.post(
            f"/api/g/{GROUP}/runs/veyru/{RUN_DIR_NAME}/evaluate",
            json={
                "model": "claude-haiku-4-5-20251001",
                "provider": "anthropic",
                "metrics": ["excess_moves"],
            },
        )

    assert response.status_code == 422
    assert "excess_moves" in response.json()["detail"]
    assert launches == []


async def test_evaluating_a_scenarios_own_metric_is_launched(
    client: httpx.AsyncClient, runs_dir: Path, launches: list[RecordedLaunch]
) -> None:
    """The control for the 422: the same metric on its own scenario is accepted."""
    write_finished_run(runs_dir=runs_dir, scenario_name="signal_game")

    async with client:
        response = await client.post(
            f"/api/g/{GROUP}/runs/signal_game/{RUN_DIR_NAME}/evaluate",
            json={
                "model": "claude-haiku-4-5-20251001",
                "provider": "anthropic",
                "metrics": ["excess_moves"],
            },
        )

    assert response.status_code == 200, response.text
    assert len(launches) == 1
    command = launches[0].command
    assert command[command.index("--metrics") + 1] == "excess_moves"
