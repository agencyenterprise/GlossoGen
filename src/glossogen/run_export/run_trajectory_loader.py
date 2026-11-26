"""Loading every agent's ATIF trajectory from one run directory, for the run exports."""

import logging
from pathlib import Path

import orjson
from pydantic import ValidationError

from glossogen.atif_export.atif_models import AtifTrajectory
from glossogen.atif_export.atif_run_context import load_atif_run_context_blocking
from glossogen.atif_export.atif_trajectory_builder import build_run_trajectories
from glossogen.run_storage.run_file_paths import event_log_path

logger = logging.getLogger(__name__)


def load_run_trajectories(run_dir: Path, scenario_name: str) -> list[AtifTrajectory]:
    """Every agent generation's trajectory, built from the run's event log.

    A run with no event log yet (claimed, never started) has no agents. Neither
    does a run whose log this build cannot parse, such as an old run whose events
    have since gained required fields: the caller exports its other files without
    trajectories rather than failing.
    """
    log_path = event_log_path(run_dir=run_dir, scenario_name=scenario_name)
    if not log_path.exists():
        return []
    try:
        context = load_atif_run_context_blocking(run_dir=run_dir, scenario_name=scenario_name)
    except ValidationError, orjson.JSONDecodeError:
        logger.exception("Exporting %s without trajectories: its event log does not parse", run_dir)
        return []
    return build_run_trajectories(context=context, cutoff_round=None)
