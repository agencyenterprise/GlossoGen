"""The HTTP app over a runs directory, and the run logs it serves.

``db_pool`` is None, so runs are resolved and listed from the directory on disk,
the way ``glossogen serve`` runs without Postgres. The client talks to the app in
process through the ASGI transport.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import orjson
from fastapi import FastAPI

from glossogen.models.agent_model_settings import AgentModelSettings
from glossogen.models.event import (
    AgentRegistered,
    MessageSent,
    RoundAdvanced,
    RunStatus,
    SimulationEnded,
    SimulationStarted,
)
from glossogen.models.event_base import EventBase
from glossogen.models.message import SimulationMessage
from glossogen.run_file_paths import event_log_path
from glossogen.server.app_factory import create_app
from glossogen.server.server_runtime_config import FeatureFlags, ServerRuntimeConfig

GROUP_API = "/api/g/local"
"""The URL prefix of every route the local group owns."""

RUN_START = datetime(2026, 1, 1, tzinfo=UTC)

UNREADABLE_EVENT_TYPE = "a_scenario_that_is_not_installed"
"""An ``event_type`` no class in this build declares."""


def at_second(seconds: int) -> datetime:
    """A timestamp ``seconds`` after ``RUN_START``, so tests order events explicitly."""
    return RUN_START + timedelta(seconds=seconds)


def build_local_app(runs_dir: Path) -> FastAPI:
    """An app serving ``runs_dir``, with MCP and the database both off."""
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


def local_client(app: FastAPI) -> httpx.AsyncClient:
    """An HTTP client bound to ``app`` in process."""
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")


def unreadable_record(event_id: str, seconds: int) -> bytes:
    """A log line of ``UNREADABLE_EVENT_TYPE`` in round 1."""
    return orjson.dumps(
        {
            "event_id": event_id,
            "event_type": UNREADABLE_EVENT_TYPE,
            "timestamp": at_second(seconds).isoformat(),
            "round_number": 1,
        }
    )


def one_round_run_events(scenario_name: str, run_dir_name: str, finished: bool) -> list[EventBase]:
    """A one-round run in which ``field_observer`` sends message ``m1`` on ``link``.

    The send is at second 3. A finished run ends at second 10.
    """
    events: list[EventBase] = [
        SimulationStarted(
            round_number=0,
            timestamp=at_second(0),
            run_id=f"{scenario_name}/{run_dir_name}",
            scenario_name=scenario_name,
            scenario_description="",
            channel_ids=["link"],
            provider="anthropic",
            scenario_config={},
        ),
        AgentRegistered(
            round_number=0,
            timestamp=at_second(0),
            agent_id="field_observer",
            role_name="Field Observer",
            model="claude-sonnet-4-6",
            provider="anthropic",
            system_prompt="",
            channel_ids=["link"],
            tool_names=["send_message"],
            model_settings=AgentModelSettings(max_tokens=1024),
        ),
        RoundAdvanced(round_number=1, timestamp=at_second(1), trigger="start"),
        MessageSent(
            round_number=1,
            timestamp=at_second(3),
            message=SimulationMessage(
                message_id="m1",
                channel_id="link",
                sender_agent_id="field_observer",
                sender_display_name="Field Observer",
                text="symptoms",
                timestamp=at_second(3),
                round_number=1,
            ),
            token_count=1,
        ),
    ]
    if finished:
        events.append(
            SimulationEnded(
                round_number=1,
                timestamp=at_second(10),
                reason=RunStatus.SCENARIO_COMPLETE,
                total_messages=1,
                total_cost_usd=0.0,
            )
        )
    return events


def write_event_log(
    runs_dir: Path,
    scenario_name: str,
    run_dir_name: str,
    events: list[EventBase],
    extra_records: list[tuple[int, bytes]],
) -> Path:
    """Write ``events`` as the run's JSONL log and return the run directory.

    ``extra_records`` are raw lines inserted before the event at each index, for
    records no event class in this build can produce.
    """
    run_dir = runs_dir / scenario_name / run_dir_name
    run_dir.mkdir(parents=True)
    lines = [event.model_dump_json().encode() for event in events]
    for index, raw in sorted(extra_records, key=lambda pair: pair[0], reverse=True):
        lines.insert(index, raw)
    log_path = event_log_path(run_dir=run_dir, scenario_name=scenario_name)
    log_path.write_bytes(b"".join(line + b"\n" for line in lines))
    return run_dir
