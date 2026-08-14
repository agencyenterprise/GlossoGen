"""Shared utilities for launching simulation subprocesses.

Used by the MCP browser to start new simulation runs as background processes.
"""

import logging
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import orjson

from glossogen.provider_credentials import require_reachable_models
from glossogen.run_config_validation import validate_run_config
from glossogen.scenario_protocol import SimulationScenario
from glossogen.token_pricing import list_providers

logger = logging.getLogger(__name__)


def build_config_file(knobs: dict[str, Any]) -> Path:
    """Write validated knobs to a temporary JSON config file.

    Written even when the knobs are empty, because ``run`` requires
    ``--config``: a launcher that omitted the flag for an empty config would
    build a command the CLI refuses to parse. An empty file instead reaches the
    scenario's knobs model, which says which fields are missing.

    The file is left for the operating system to reclaim. It cannot be deleted
    at launch time because the subprocess reads it at startup, and it is a few
    hundred bytes in a directory the OS already manages, which is not worth the risk of
    pattern-matching deletes in shared temp space.
    """
    fd, tmp_path = tempfile.mkstemp(suffix=".json", prefix="glossogen_config_")
    os.close(fd)
    config_path = Path(tmp_path)
    config_path.write_bytes(orjson.dumps(knobs))
    return config_path


def launch_simulation(
    scenario_name: str,
    model: str,
    provider: str,
    scenario_cls: type[SimulationScenario],
    knobs: dict[str, Any] | None,
    runs_dir: Path,
    group_slug: str,
) -> None:
    """Validate config and launch a simulation as a background subprocess.

    ``group_slug`` is forwarded to the CLI so the subprocess registers the
    new run row under the right tenant after ``claim_run_dir`` succeeds.

    Raises ``ValueError`` for invalid config.
    """
    if provider not in list_providers():
        raise ValueError(f"Unknown provider: {provider}")

    raw_config = dict(knobs) if knobs is not None else {}

    validated = validate_run_config(
        scenario_cls=scenario_cls,
        scenario_config=raw_config,
        default_provider=provider,
        valid_providers=set(list_providers()),
    )

    require_reachable_models(
        scenario_cls=scenario_cls,
        scenario_config=validated.scenario_config,
        agent_overrides=validated.normalized_agent_overrides,
        default_model=model,
        default_provider=provider,
    )

    cmd = [
        sys.executable,
        "-m",
        "glossogen",
        "run",
        scenario_name,
        "--model",
        model,
        "--provider",
        provider,
        "--runs-dir",
        str(runs_dir),
        "--group-slug",
        group_slug,
    ]

    cmd.extend(["--config", str(build_config_file(knobs=validated.scenario_config))])

    logger.info("Launching new simulation: %s", " ".join(cmd))

    # One log file per launch. A single shared path truncates whenever two
    # launches overlap, so the surviving log describes neither run.
    launch_log_dir = runs_dir / "_launch_logs"
    launch_log_dir.mkdir(parents=True, exist_ok=True)
    stdout_log = launch_log_dir / f"{scenario_name}_{time.time_ns()}.log"
    with open(stdout_log, "w") as log_file:
        process = subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    logger.info(
        "Launched simulation pid=%d scenario=%s log=%s",
        process.pid,
        scenario_name,
        stdout_log,
    )
