"""Shared utilities for launching simulation subprocesses.

Used by both the scenarios REST router and the MCP browser to start
new simulation runs as background processes.
"""

import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import orjson

from schmidt.run_config_validation import validate_run_config
from schmidt.scenario_protocol import SimulationScenario
from schmidt.token_pricing import list_providers

logger = logging.getLogger(__name__)


def build_config_file(knobs: dict[str, Any] | None) -> Path | None:
    """Write validated knobs to a temporary JSON config file.

    Returns the file path, or None if knobs is empty/None.
    """
    config: dict[str, Any] = {}
    if knobs:
        config.update(knobs)

    if not config:
        return None

    fd, tmp_path = tempfile.mkstemp(suffix=".json", prefix="config_")
    os.close(fd)
    config_path = Path(tmp_path)
    config_path.write_bytes(orjson.dumps(config))
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
    Raises ValueError for invalid config, RuntimeError for launch failures.
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

    cmd = [
        sys.executable,
        "-m",
        "schmidt",
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

    config_path = build_config_file(knobs=validated.scenario_config)
    if config_path is not None:
        cmd.extend(["--config", str(config_path)])

    logger.info("Launching new simulation: %s", " ".join(cmd))

    stdout_log = runs_dir / f"{scenario_name}_start.log"
    with open(stdout_log, "w") as log_file:
        subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
