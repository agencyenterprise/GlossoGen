"""The HTTP surface of knob filtering: the schema endpoint, and how a bad filter fails.

Driven through the app rather than by calling handlers, because the status codes
are the thing under test and FastAPI is what produces them. A malformed
condition has to reach the client as a 422; reaching it as a 500 would say the
server broke rather than the request did.

No database: ``db_pool`` is None, which is the no-database single-tenant path,
and the identity middleware answers every request as the synthetic local group.
"""

from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from glossogen.server.app_factory import create_app
from glossogen.server.server_runtime_config import FeatureFlags, ServerRuntimeConfig

GROUP = "local"


def build_app(tmp_path: Path) -> FastAPI:
    """An app over an empty runs directory, with MCP and the database both off."""
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
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


@pytest.fixture(name="client")
def client_fixture(tmp_path: Path) -> httpx.AsyncClient:
    """An HTTP client bound to the app, with no network involved."""
    app = build_app(tmp_path=tmp_path)
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    )


def selection(knob: list[str]) -> dict[str, object]:
    """A filter selection carrying these knob conditions and nothing else."""
    return {
        "kind": "filters",
        "scenario": [],
        "labels": [],
        "run_id_contains": None,
        "status": None,
        "contains_agent_id": None,
        "knob": knob,
    }


async def test_the_schema_endpoint_lists_a_scenarios_scalar_knobs(
    client: httpx.AsyncClient,
) -> None:
    """The runs list learns what it can filter on without knowing any knob names."""
    async with client:
        response = await client.get(f"/api/g/{GROUP}/scenarios/veyru/filterable-knobs")

    assert response.status_code == 200
    body = response.json()
    assert body["scenario_name"] == "veyru"
    by_name = {knob["name"]: knob for knob in body["knobs"]}
    assert by_name["round_count"]["knob_type"] == "integer"
    assert by_name["postmortem_enabled"]["knob_type"] == "boolean"
    assert by_name["judge_model"]["knob_type"] == "string"
    assert by_name["noise_replacement_mode"]["enum_values"] == ["mask", "random_letter"]
    # scheduled_events is a list of models, so it carries no comparison.
    assert "scheduled_events" not in by_name


async def test_the_schema_endpoint_404s_for_a_scenario_that_is_not_installed(
    client: httpx.AsyncClient,
) -> None:
    """A name nothing answers to is a missing resource, not an empty knob list."""
    async with client:
        response = await client.get(f"/api/g/{GROUP}/scenarios/no_such_scenario/filterable-knobs")

    assert response.status_code == 404


async def test_the_runs_list_refuses_a_malformed_condition(client: httpx.AsyncClient) -> None:
    """422, because the request is wrong. Dropping it would answer with extra runs."""
    async with client:
        response = await client.get(f"/api/g/{GROUP}/runs", params={"knob": "roundcount15"})

    assert response.status_code == 422


async def test_the_runs_list_accepts_a_well_formed_condition(client: httpx.AsyncClient) -> None:
    """Over an empty runs directory it selects nothing, which is a 200."""
    async with client:
        response = await client.get(
            f"/api/g/{GROUP}/runs", params={"knob": "round_time_budget_seconds>=200"}
        )

    assert response.status_code == 200
    assert response.json()["runs"] == []


async def test_a_condition_naming_an_unknown_knob_is_not_an_error(
    client: httpx.AsyncClient,
) -> None:
    """Knob names belong to a scenario's schema, and a selection may span scenarios."""
    async with client:
        response = await client.get(f"/api/g/{GROUP}/runs", params={"knob": "no_such_knob=1"})

    assert response.status_code == 200


@pytest.mark.parametrize("endpoint", ["preview", "csv", "raw"])
async def test_every_export_endpoint_refuses_a_malformed_condition(
    client: httpx.AsyncClient,
    endpoint: str,
) -> None:
    """The model validates the field, so all three answer 422 rather than 500.

    Parsing at each call site instead would raise a plain ValueError inside the
    handler, and only StarletteHTTPException has a handler, so the client would
    see a 500 for its own typo.
    """
    body: dict[str, object] = {
        "selection": selection(knob=["roundcount15"]),
        "frames": ["run_level"],
        "columns": ["status"],
        "metrics": [],
        "repeat_run_columns": False,
        "include_metric_summaries": False,
        "include_logs": False,
    }
    async with client:
        response = await client.post(f"/api/g/{GROUP}/runs/export/{endpoint}", json=body)

    assert response.status_code == 422
    assert "carries no operator" in response.text
