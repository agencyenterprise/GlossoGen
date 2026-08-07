"""Concurrency limits for the paid background work the server spawns.

Starting a simulation or an evaluation launches a detached subprocess that
makes LLM API calls, so every launch spends real money against the operator's
provider keys. Without a ceiling, a retry loop in a client — or an operator who
simply clicks the button too many times — can run up an unbounded bill before
anyone notices.

Both limits are counted from the filesystem rather than the database, because
the marker files are written by the subprocess itself and are the same signal
the rest of the server already trusts:

- simulations write ``stream.json`` and delete it when they end. ``read_manifest``
  returns ``None`` for a manifest whose PID is gone, so a crashed run frees its
  slot without any cleanup step.
- evaluations write ``eval_in_progress.json`` for the same purpose.

The counts glob for those marker files rather than walking every run directory,
so the cost does not grow with the size of the run archive.
"""

import logging
import os
from pathlib import Path

from glossogen.eval_manifest import read_eval_manifest
from glossogen.stream_manifest import read_manifest

logger = logging.getLogger(__name__)

DEFAULT_MAX_CONCURRENT_RUNS = 4
DEFAULT_MAX_CONCURRENT_EVALUATIONS = 4

MAX_CONCURRENT_RUNS_VAR = "MAX_CONCURRENT_RUNS"
MAX_CONCURRENT_EVALUATIONS_VAR = "MAX_CONCURRENT_EVALUATIONS"


class LaunchCapacityExceeded(RuntimeError):
    """Raised when a launch would exceed the configured concurrency limit.

    Carries the limit and the observed count so the caller can build an
    actionable message without recomputing either.
    """

    def __init__(self, kind: str, running: int, limit: int, env_var: str) -> None:
        self.kind = kind
        self.running = running
        self.limit = limit
        self.env_var = env_var
        super().__init__(
            f"{running} {kind} already running, which is the configured limit "
            f"of {limit}. Wait for one to finish, or raise {env_var}."
        )


def _read_positive_int(name: str, default: int) -> int:
    """Read a positive integer environment variable, falling back to ``default``.

    A malformed or non-positive value falls back with a warning rather than
    failing the request: an unparseable limit should not take the server down,
    but it must not silently disable the cap either.
    """
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning("%s is not an integer (%r); using default %d", name, raw, default)
        return default
    if value < 1:
        logger.warning("%s must be >= 1 (got %d); using default %d", name, value, default)
        return default
    return value


def max_concurrent_runs() -> int:
    """Configured ceiling on simultaneously running simulations."""
    return _read_positive_int(name=MAX_CONCURRENT_RUNS_VAR, default=DEFAULT_MAX_CONCURRENT_RUNS)


def max_concurrent_evaluations() -> int:
    """Configured ceiling on simultaneously running evaluations."""
    return _read_positive_int(
        name=MAX_CONCURRENT_EVALUATIONS_VAR,
        default=DEFAULT_MAX_CONCURRENT_EVALUATIONS,
    )


def count_running_simulations(runs_dir: Path) -> int:
    """Count simulations with a live stream manifest under ``runs_dir``.

    Manifests whose process is gone are ignored, so a crashed simulation does
    not hold a slot.
    """
    running = 0
    for manifest_path in runs_dir.glob("*/*/stream.json"):
        if read_manifest(run_dir=manifest_path.parent) is not None:
            running += 1
    return running


def count_running_evaluations(runs_dir: Path) -> int:
    """Count evaluations with a live manifest under ``runs_dir``."""
    running = 0
    for manifest_path in runs_dir.glob("*/*/eval_in_progress.json"):
        if read_eval_manifest(run_dir=manifest_path.parent) is not None:
            running += 1
    return running


def assert_simulation_capacity(runs_dir: Path) -> None:
    """Raise ``LaunchCapacityExceeded`` if no simulation slot is free."""
    limit = max_concurrent_runs()
    running = count_running_simulations(runs_dir=runs_dir)
    if running >= limit:
        raise LaunchCapacityExceeded(
            kind="simulations",
            running=running,
            limit=limit,
            env_var=MAX_CONCURRENT_RUNS_VAR,
        )


def assert_evaluation_capacity(runs_dir: Path) -> None:
    """Raise ``LaunchCapacityExceeded`` if no evaluation slot is free."""
    limit = max_concurrent_evaluations()
    running = count_running_evaluations(runs_dir=runs_dir)
    if running >= limit:
        raise LaunchCapacityExceeded(
            kind="evaluations",
            running=running,
            limit=limit,
            env_var=MAX_CONCURRENT_EVALUATIONS_VAR,
        )
