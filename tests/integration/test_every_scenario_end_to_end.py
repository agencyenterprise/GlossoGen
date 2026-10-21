"""Every shipped scenario, from a scripted run to its evaluated run page.

Each scenario's own tests stop at the event log, and the metric and server tests
each start from a log some other test wrote. This one walks the whole chain per
scenario: play a round, write the log into a runs directory, score it with the
deterministic metrics the way `glossogen evaluate` does, then read it back
through the HTTP app. A scenario whose metrics, run-detail extension or listing
entry stopped resolving fails here under its own name.

Only the model is faked. No judge is called: scripted agents never take the
action a scenario judges, and the metrics asked for are the deterministic ones.
"""

from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from glossogen.evaluation.metric_core.metric_run_options import MetricRunOptions
from glossogen.scenario_registry import SCENARIO_REGISTRY
from glossogen.scenarios.signal_game.scenario import SignalGameScenario
from glossogen.server.app_factory import create_app
from glossogen.server.server_runtime_config import FeatureFlags, ServerRuntimeConfig
from glossogen.testing.metric_harness import MetricRun, score_metrics
from glossogen.testing.scenario_runtime import (
    assert_no_agent_crashed,
    assert_round_loop_completed,
    build_scenario,
    run_rounds,
)
from glossogen.testing.scripted_agent import ScriptedTurn, ToolTurn
from glossogen.testing.simulation_harness import (
    SimulationResult,
    never_times_out,
    run_simulation,
)

GROUP = "local"
PRESET = "knobs_default"
RUN_DIR_NAME = "1700000000"

DETERMINISTIC_METRICS = [
    "round_success",
    "mean_chars_per_round",
    "mean_chars_per_message",
    "round_ended_idle",
    "round_ended_timeout",
    "content_filter_refusal",
    "gzip_compression_ratio",
    "message_entropy",
]

TEXTCRAFT_SMALL = {
    "crafter_count": 2,
    "steps_per_agent": 1,
    "pool_agent_count": 2,
    "dag_cross_edge_density": 0.0,
    "virtual_clock": False,
}


def build_app(runs_dir: Path) -> FastAPI:
    """An app over ``runs_dir``, with MCP and the database both off."""
    app = create_app(
        identity_provider=None,
        runtime_config=ServerRuntimeConfig(
            runs_dir=runs_dir,
            oauth_issuer_url=None,
            allowed_origins=("http://localhost:3000",),
            feature_flags=FeatureFlags(evaluations_enabled=True),
        ),
    )
    # Normally settled by the lifespan, which wants a real database.
    app.state.db_pool = None
    app.state.local_group_id = uuid4()
    return app


def client_for(app: FastAPI) -> httpx.AsyncClient:
    """An HTTP client bound to the app, with no network involved."""
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    )


SKIPPED_OWN_METRICS: dict[str, frozenset[str]] = {"signal_game": frozenset({"excess_moves"})}
"""Scenario metrics that do not apply to the round ``play_one_round`` plays: signal_game's
round is a ``file_system`` one, which has no moves for ``excess_moves`` to count."""


async def play_signal_game(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimulationResult:
    """One round in which each player names its square.

    The signal game has no chat channel, so the chat script the other scenarios
    use has nothing to send on. The round is played on the ``file_system`` medium,
    which ``cheated_rounds`` reads; it has no moves, so ``excess_moves`` skips it
    (see ``SKIPPED_OWN_METRICS``). Nothing is written to the server, so its judge
    is not called.
    """
    scenario = build_scenario(
        scenario_name="signal_game", preset_name="knobs_file_system", overrides={"round_count": 1}
    )
    assert isinstance(scenario, SignalGameScenario)
    read = ToolTurn(tool_name="read_notifications", args={})
    end_round = ToolTurn(
        tool_name="end_round", args={"row": 1, "col": 1, "reasoning": "Scripted end."}
    )
    wait = ToolTurn(tool_name="read_notifications", args={"wait_for": "next_round"})
    scripts: dict[str, list[ScriptedTurn]] = {
        "player_a": [read, end_round, wait],
        "player_b": [read, end_round, wait],
    }
    return await run_simulation(
        scenario=scenario,
        scripts=scripts,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )


async def play_one_round(
    scenario_name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> SimulationResult:
    """Play one scripted round of ``scenario_name`` from its default preset."""
    if scenario_name == "signal_game":
        return await play_signal_game(tmp_path=tmp_path, monkeypatch=monkeypatch)
    overrides: dict[str, object] = {}
    if scenario_name == "textcraft_shared_workspace":
        overrides = dict(TEXTCRAFT_SMALL)
    return await run_rounds(
        scenario_name=scenario_name,
        preset_name=PRESET,
        round_count=1,
        overrides=overrides,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )


def file_into_runs_dir(result: SimulationResult, runs_dir: Path, scenario_name: str) -> Path:
    """Write the run's log where the server and the CLI expect a run to be."""
    run_dir = runs_dir / scenario_name / RUN_DIR_NAME
    run_dir.mkdir(parents=True)
    log_path = run_dir / f"{scenario_name}.jsonl"
    log_path.write_bytes(result.log_path.read_bytes())
    return run_dir


@pytest.mark.parametrize("scenario_name", sorted(SCENARIO_REGISTRY))
async def test_a_scripted_round_evaluates_and_serves(
    scenario_name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Play, score and serve one round, checking the scenario-owned parts at each step."""
    scenario_cls = SCENARIO_REGISTRY[scenario_name]
    result = await play_one_round(
        scenario_name=scenario_name, tmp_path=tmp_path / "sim", monkeypatch=monkeypatch
    )
    assert_round_loop_completed(result=result, round_count=1)
    assert_no_agent_crashed(result=result)

    runs_dir = tmp_path / "runs"
    run_dir = file_into_runs_dir(result=result, runs_dir=runs_dir, scenario_name=scenario_name)
    own_metric_names = [metric.name for metric in scenario_cls.scenario_metrics()]
    scored = await score_metrics(
        run=MetricRun(
            scenario=result.scenario,
            run_dir=run_dir,
            log_path=run_dir / f"{scenario_name}.jsonl",
            simulation=result,
        ),
        metric_names=DETERMINISTIC_METRICS + own_metric_names,
        judge_responses=[],
        options=MetricRunOptions(probe_round=None, probe_replicas=None, ontology_path=None),
        report_path=run_dir / f"{scenario_name}_report.json",
        monkeypatch=monkeypatch,
    )
    assert scored.judge.calls == [], "a deterministic metric called the judge"
    assert any(name.startswith("round_success") for name in scored.names())
    for metric_name in own_metric_names:
        if metric_name in SKIPPED_OWN_METRICS.get(scenario_name, frozenset()):
            assert not scored.has(metric_name=metric_name), f"{metric_name} should skip this round"
            continue
        assert scored.has(metric_name=metric_name), f"{metric_name} wrote no measurement"

    async with client_for(app=build_app(runs_dir=runs_dir)) as client:
        detail = await client.get(f"/api/g/{GROUP}/runs/{scenario_name}/{RUN_DIR_NAME}")
        evaluation = await client.get(
            f"/api/g/{GROUP}/runs/{scenario_name}/{RUN_DIR_NAME}/evaluation"
        )
        listing = await client.get(f"/api/g/{GROUP}/scenarios")

    assert detail.status_code == 200, detail.text
    extras = detail.json()["scenario_extras"]
    if scenario_cls.run_detail_extension() is None:
        assert extras is None
    else:
        assert extras is not None, "the scenario's run-detail extension produced nothing"
        assert extras["scenario_name"] == scenario_name
        assert extras["cases"], "the extension found no case in a run that played one"

    assert evaluation.status_code == 200, evaluation.text
    served = {m["metric_name"] for m in evaluation.json()["measurements"]}
    assert served == set(scored.names())

    assert listing.status_code == 200
    entry = next(s for s in listing.json()["scenarios"] if s["scenario_name"] == scenario_name)
    for metric_name in own_metric_names:
        assert metric_name in entry["available_metrics"]


def test_the_scenarios_with_run_page_extras_are_the_expected_ones() -> None:
    """Pins which built-ins carry extras, so one silently losing its extension fails."""
    with_extension = {
        name for name, cls in SCENARIO_REGISTRY.items() if cls.run_detail_extension() is not None
    }

    assert with_extension == {
        "container_yard_stacking",
        "drive_module_repair",
        "orbital_anomaly",
        "spot_the_difference",
        "spot_the_intersection",
        "veyru",
    }


def test_only_signal_game_lists_the_signal_game_metrics() -> None:
    """A scenario's own metric must not leak into another scenario's offer."""
    owners = {
        name: sorted(metric.name for metric in cls.scenario_metrics())
        for name, cls in SCENARIO_REGISTRY.items()
        if cls.scenario_metrics()
    }

    assert owners == {"signal_game": ["cheated_rounds", "excess_moves", "longest_streak"]}


async def test_a_signal_game_metric_is_refused_on_a_veyru_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Through the REST evaluate endpoint, a 422 before any subprocess starts."""
    result = await play_one_round(
        scenario_name="veyru", tmp_path=tmp_path / "sim", monkeypatch=monkeypatch
    )
    runs_dir = tmp_path / "runs"
    file_into_runs_dir(result=result, runs_dir=runs_dir, scenario_name="veyru")

    async with client_for(app=build_app(runs_dir=runs_dir)) as client:
        response = await client.post(
            f"/api/g/{GROUP}/runs/veyru/{RUN_DIR_NAME}/evaluate",
            json={
                "model": "claude-haiku-4-5-20251001",
                "provider": "anthropic",
                "metrics": ["round_success", "excess_moves"],
            },
        )

    assert response.status_code == 422
    assert "excess_moves" in response.json()["detail"]
