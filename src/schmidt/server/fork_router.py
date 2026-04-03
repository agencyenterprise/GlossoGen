"""FastAPI router for forking simulation runs from a specific message.

Uses the git-backed run repository to clone the source run at the target
message's commit, apply edits, and launch a resumed simulation.
"""

import logging
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import orjson
from fastapi import APIRouter, HTTPException, Request

from schmidt.evaluation.log_reader import load_events
from schmidt.message_rewind import build_rewind_state
from schmidt.run_repository import RunRepository, claim_run_dir
from schmidt.server.response_models import ForkRequest, ForkResponse
from schmidt.server.run_discovery import discover_runs

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


def _build_fork_config(
    scenario_config: dict[str, object],
    model_overrides: dict[str, Any] | None,
    run_dir: Path,
) -> tuple[Path, list[str]]:
    """Build a --config file and override args for a forked simulation.

    Merges the source run's scenario config with any new model overrides
    into a single config file. Returns the config file path and any
    extra override args.
    """
    config: dict[str, Any] = dict(scenario_config)

    if model_overrides:
        agents: dict[str, Any] = {}
        for agent_id, entry in model_overrides.items():
            agents[agent_id] = entry
        config["agents"] = agents

    config_path = run_dir / "fork_config.json"
    config_path.write_bytes(orjson.dumps(config))
    return config_path, []


@router.post("/runs/{run_id}/fork", response_model=ForkResponse)
async def fork_run(run_id: str, body: ForkRequest, request: Request) -> ForkResponse:
    """Create a forked simulation run from a specific message.

    Clones the source run's git repository at the target message's commit,
    applies text edits to the JSONL, and launches the simulation as a
    background subprocess with ``--resume``.
    """
    runs_dir: Path = request.app.state.runs_dir
    summaries = await discover_runs(runs_dir=runs_dir)

    matching = [s for s in summaries if s.run_id == run_id]
    if not matching:
        raise HTTPException(status_code=404, detail="Run not found")

    source_run_dir = Path(matching[0].run_dir)
    scenario_name = matching[0].scenario_name
    message_edits = {edit.message_id: edit.new_text for edit in body.message_edits}

    # Find the git commit for the target message.
    source_repo = RunRepository(run_dir=source_run_dir)
    target_sha = await source_repo.find_commit_for_message(message_id=body.target_message_id)
    if target_sha is None:
        raise HTTPException(
            status_code=404,
            detail=f"No git commit found for message {body.target_message_id}",
        )

    # Clone to new run directory and check out the target commit.
    new_run_dir = claim_run_dir(runs_dir=runs_dir, scenario_name=scenario_name)
    forked_repo = await source_repo.clone_to(target_dir=new_run_dir)
    await forked_repo.checkout(sha=target_sha)

    # The JSONL and all workspace files are now at the correct state.
    # Apply message edits and assign a new run ID.
    new_log_path = new_run_dir / f"{scenario_name}.jsonl"
    fork_run_id = _apply_edits_and_new_run_id(
        log_path=new_log_path,
        message_edits=message_edits,
    )

    # Verify the target message exists in the truncated log.
    events = await load_events(log_path=new_log_path)
    build_rewind_state(
        events=events,
        target_message_id=body.target_message_id,
        message_edits=message_edits,
    )

    # Write fork manifest for provenance tracking.
    manifest = {
        "source_run_id": run_id,
        "source_run_dir": str(source_run_dir),
        "target_message_id": body.target_message_id,
        "forked_at": time.time(),
    }
    manifest_path = new_run_dir / "fork_manifest.json"
    manifest_path.write_bytes(orjson.dumps(manifest))

    # Commit the edits and manifest.
    await forked_repo.commit(
        message="fork: applied message edits and new run_id",
        paths=None,
    )

    # Build config file from source scenario config + model overrides.
    overrides_for_model = None
    if body.model_overrides:
        overrides_for_model = {
            agent_id: entry.model_dump() for agent_id, entry in body.model_overrides.items()
        }

    config_path, override_args = _build_fork_config(
        scenario_config=matching[0].scenario_config,
        model_overrides=overrides_for_model,
        run_dir=new_run_dir,
    )

    # Launch the forked simulation as a background subprocess.
    stdout_log = new_run_dir / f"{scenario_name}_stdout.log"
    mcp_port = _find_free_port()
    cmd = [
        sys.executable,
        "-m",
        "schmidt",
        "run",
        scenario_name,
        "--model",
        body.model,
        "--provider",
        body.provider,
        "--mcp-port",
        str(mcp_port),
        "--resume",
        str(new_run_dir),
        "--runs-dir",
        str(runs_dir),
        "--config",
        str(config_path),
        *override_args,
    ]

    logger.info("Launching forked simulation: %s", " ".join(cmd))

    with open(stdout_log, "w") as log_file:
        _launch_subprocess(cmd=cmd, log_file=log_file)

    return ForkResponse(
        fork_run_id=fork_run_id,
        fork_run_dir=str(new_run_dir),
    )


def _apply_edits_and_new_run_id(
    log_path: Path,
    message_edits: dict[str, str],
) -> str:
    """Rewrite the JSONL in-place, applying message edits and a new run ID.

    Returns the new fork run ID.
    """
    fork_run_id = str(uuid4())
    raw_bytes = log_path.read_bytes()
    lines = raw_bytes.split(b"\n")
    output_lines: list[bytes] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        event_dict = orjson.loads(stripped)

        if event_dict.get("event_type") == "simulation_started":
            event_dict["run_id"] = fork_run_id

        if event_dict.get("event_type") == "message_sent":
            msg = event_dict.get("message", {})
            msg_id = msg.get("message_id", "")
            if msg_id in message_edits:
                msg["text"] = message_edits[msg_id]

        output_lines.append(orjson.dumps(event_dict))

    log_path.write_bytes(b"\n".join(output_lines) + b"\n")

    logger.info(
        "Fork edits applied: %d lines, run_id=%s, %d message edits",
        len(output_lines),
        fork_run_id,
        len(message_edits),
    )
    return fork_run_id


def _find_free_port() -> int:
    """Find an available TCP port by briefly binding to port 0."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


def _launch_subprocess(cmd: list[str], log_file: Any) -> None:
    """Launch a simulation subprocess in the background."""
    subprocess.Popen(
        cmd,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
