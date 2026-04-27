"""FastAPI router for forking simulation runs from a specific message.

Uses the git-backed run repository to clone the source run at the target
message's commit, apply edits, and launch a resumed simulation.
"""

import logging
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import orjson
from fastapi import APIRouter, HTTPException, Request

from schmidt.evaluation.log_reader import load_events
from schmidt.message_rewind import build_rewind_state
from schmidt.models.event import SimulationStarted
from schmidt.run_config_validation import validate_run_config
from schmidt.run_jsonl_rewriter import drop_all_agent_history, rewrite_run_jsonl
from schmidt.run_repository import RunRepository, claim_run_dir
from schmidt.scenarios import SCENARIO_REGISTRY
from schmidt.server.runs.discovery import compose_run_id, resolve_run
from schmidt.server.runs.models import ForkRequest, ForkResponse
from schmidt.token_pricing import list_providers

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


def _build_fork_config(
    scenario_config: dict[str, object],
    run_dir: Path,
) -> tuple[Path, list[str]]:
    """Build a --config file and override args for a forked simulation.

    Writes the fork scenario config to a single file and returns the path.
    """
    config: dict[str, Any] = dict(scenario_config)

    config_path = run_dir / "fork_config.json"
    config_path.write_bytes(orjson.dumps(config))
    return config_path, []


@router.post("/runs/{scenario}/{run_dir_name}/fork", response_model=ForkResponse)
async def fork_run(
    scenario: str,
    run_dir_name: str,
    body: ForkRequest,
    request: Request,
) -> ForkResponse:
    """Create a forked simulation run from a specific message.

    Clones the source run's git repository at the target message's commit,
    applies text edits to the JSONL, and launches the simulation as a
    background subprocess with ``--resume``.
    """
    runs_dir: Path = request.app.state.runs_dir
    try:
        resolved = resolve_run(
            runs_dir=runs_dir,
            scenario_name=scenario,
            run_dir_name=run_dir_name,
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="Run not found")

    source_run_dir = resolved.run_dir
    scenario_name = resolved.scenario_name
    source_run_id = compose_run_id(scenario_name=scenario, run_dir_name=run_dir_name)
    message_edits = {edit.message_id: edit.new_text for edit in body.message_edits}

    if body.provider not in list_providers():
        raise HTTPException(status_code=422, detail=f"Unknown provider: {body.provider}")
    if scenario_name not in SCENARIO_REGISTRY:
        raise HTTPException(status_code=422, detail=f"Unknown scenario: {scenario_name}")

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

    fork_run_id = compose_run_id(scenario_name=scenario_name, run_dir_name=new_run_dir.name)

    # The JSONL and all workspace files are now at the correct state.
    # Apply message edits and update the run ID in the first event.
    new_log_path = new_run_dir / f"{scenario_name}.jsonl"
    rewrite_run_jsonl(
        log_path=new_log_path,
        new_run_id=fork_run_id,
        message_edits=message_edits,
        should_drop_event=drop_all_agent_history,
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
        "source_run_id": source_run_id,
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

    # Build config file from source scenario config + optional knobs overrides.
    scenario_cls = SCENARIO_REGISTRY[scenario_name]
    first_event = events[0]
    if not isinstance(first_event, SimulationStarted):
        raise HTTPException(status_code=500, detail="First event is not SimulationStarted")
    source_scenario_config = dict(first_event.scenario_config)
    merged_scenario_config = dict(source_scenario_config)
    if body.knobs is not None:
        merged_scenario_config.update(body.knobs)

    try:
        validated = validate_run_config(
            scenario_cls=scenario_cls,
            scenario_config=merged_scenario_config,
            default_provider=body.provider,
            valid_providers=set(list_providers()),
        )
    except (SystemExit, ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid fork configuration: {exc}") from exc

    config_path, override_args = _build_fork_config(
        scenario_config=validated.scenario_config,
        run_dir=new_run_dir,
    )

    # Launch the forked simulation as a background subprocess.
    stdout_log = new_run_dir / f"{scenario_name}_stdout.log"
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


def _launch_subprocess(cmd: list[str], log_file: Any) -> None:
    """Launch a simulation subprocess in the background."""
    subprocess.Popen(
        cmd,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
