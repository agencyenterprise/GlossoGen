"""Which runs an export selection names, answered through the preview endpoint.

The export routers' own tests stub `resolve_export_selection`, and the listing
tests call the listings directly, so this is where the two meet: a selection posted
to the app, resolved against the runs the group owns. No database: ``db_pool`` is
None and runs are discovered from the directory written here.
"""

from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest

from glossogen.models.agent_model_settings import AgentModelSettings
from glossogen.models.event import AgentRegistered, RunStatus, SimulationEnded, SimulationStarted
from glossogen.models.event_base import EventBase
from glossogen.run_file_paths import event_log_path
from glossogen.server.app_factory import create_app
from glossogen.server.server_runtime_config import FeatureFlags, ServerRuntimeConfig

PREVIEW_URL = "/api/g/local/runs/export/preview"


def write_run(runs_dir: Path, scenario_name: str, run_dir_name: str, finished: bool) -> None:
    """One run directory the discovery walk can read."""
    run_dir = runs_dir / scenario_name / run_dir_name
    run_dir.mkdir(parents=True)
    events: list[EventBase] = [
        SimulationStarted(
            round_number=0,
            run_id=run_dir_name,
            scenario_name=scenario_name,
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
            tool_names=["send_message"],
            model_settings=AgentModelSettings(max_tokens=1024),
        ),
    ]
    if finished:
        events.append(
            SimulationEnded(
                round_number=15,
                reason=RunStatus.SCENARIO_COMPLETE,
                total_messages=0,
                total_cost_usd=0.0,
            )
        )
    log_path = event_log_path(run_dir=run_dir, scenario_name=scenario_name)
    log_path.write_bytes(b"".join(e.model_dump_json().encode() + b"\n" for e in events))


@pytest.fixture(name="client")
def client_fixture(tmp_path: Path) -> httpx.AsyncClient:
    """A client for an app over two veyru runs, one finished, and one other scenario's run."""
    runs_dir = tmp_path / "runs"
    write_run(runs_dir=runs_dir, scenario_name="veyru", run_dir_name="1000000001", finished=True)
    write_run(runs_dir=runs_dir, scenario_name="veyru", run_dir_name="1000000002", finished=False)
    write_run(
        runs_dir=runs_dir,
        scenario_name="spot_the_difference",
        run_dir_name="1000000003",
        finished=True,
    )
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
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    )


async def preview(client: httpx.AsyncClient, selection: dict[str, Any]) -> httpx.Response:
    """Post ``selection`` to the export preview."""
    async with client:
        return await client.post(
            PREVIEW_URL,
            json={
                "selection": selection,
                "include_raw_size_estimate": False,
                "include_logs": False,
            },
        )


def filter_selection(scenario: list[str], status: str | None) -> dict[str, Any]:
    """A filter selection on scenario and status, every other filter empty."""
    return {
        "kind": "filters",
        "scenario": scenario,
        "labels": [],
        "run_id_contains": None,
        "status": status,
        "contains_agent_id": None,
        "knob": [],
    }


async def test_an_explicit_selection_reports_the_ids_it_cannot_resolve(
    client: httpx.AsyncClient,
) -> None:
    """Ids from any scenario resolve; an unknown id is reported instead of failing the preview."""
    response = await preview(
        client=client,
        selection={
            "kind": "explicit",
            "run_ids": ["spot_the_difference/1000000003", "veyru/1000000001", "veyru/9999999999"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["run_ids"] == ["spot_the_difference/1000000003", "veyru/1000000001"]
    assert body["missing_run_ids"] == ["veyru/9999999999"]


async def test_a_filter_selection_returns_only_the_runs_its_filters_match(
    client: httpx.AsyncClient,
) -> None:
    response = await preview(
        client=client,
        selection=filter_selection(scenario=["veyru"], status=RunStatus.SCENARIO_COMPLETE.value),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["run_ids"] == ["veyru/1000000001"]
    assert body["missing_run_ids"] == []


async def test_an_empty_filter_selection_covers_every_scenario(
    client: httpx.AsyncClient,
) -> None:
    response = await preview(client=client, selection=filter_selection(scenario=[], status=None))

    assert response.status_code == 200
    assert response.json()["run_ids"] == [
        "spot_the_difference/1000000003",
        "veyru/1000000001",
        "veyru/1000000002",
    ]
