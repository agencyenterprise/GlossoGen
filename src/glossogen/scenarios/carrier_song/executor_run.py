"""Runs a sender's executor on a song in the Python sandbox and checks what it returned.

The executor is the sender's Python source defining ``noise(song)``. It runs through
``noise_harness`` in a fresh sandboxed interpreter, and its return value must be a
list of whole numbers as long as the song. Values past ``±max_volume`` are clipped.
"""

import json
import logging
from pathlib import Path
from typing import NamedTuple, cast

import aiofiles

from glossogen.code_sandbox.python_runner import SandboxLimits, run_python
from glossogen.scenarios.carrier_song.noise_harness import RESULT_MARKER

logger = logging.getLogger(__name__)

HARNESS_PATH = Path(__file__).parent / "noise_harness.py"

SANDBOX_LIMITS = SandboxLimits(
    wall_seconds=10.0,
    cpu_seconds=5,
    memory_bytes=256 * 1024 * 1024,
    file_bytes=1024 * 1024,
    output_bytes=16_000,
)
"""What one executor run, or one run_python program, may spend."""


class ExecutorRun(NamedTuple):
    """One executor run: the clipped noise, or the error that stopped it, and what it printed.

    ``noise`` is None exactly when ``error`` is set. ``clipped_ticks`` counts the ticks
    whose value was past ``±max_volume``.
    """

    noise: list[int] | None
    clipped_ticks: int
    printed: str
    error: str | None


class _Output(NamedTuple):
    printed: str
    result_line: str | None


async def run_executor(code: str, song: list[int], max_volume: int) -> ExecutorRun:
    """Run ``code``'s ``noise`` on ``song`` and return its noise clipped to ``±max_volume``."""
    async with aiofiles.open(HARNESS_PATH, encoding="utf-8") as handle:
        harness = await handle.read()
    result = await run_python(
        code=harness,
        inputs={"noise.py": code.encode("utf-8"), "song.json": json.dumps(song).encode("utf-8")},
        limits=SANDBOX_LIMITS,
    )
    output = _split_output(stdout=result.stdout)
    error: str | None = None
    if result.timed_out:
        error = f"the executor was stopped after {SANDBOX_LIMITS.wall_seconds:g} seconds"
    elif result.exit_status != 0:
        error = result.stderr.strip()
        if error == "":
            error = f"the executor exited with status {result.exit_status}"
    elif result.output_cut:
        error = f"the executor printed more than {SANDBOX_LIMITS.output_bytes} bytes"
    elif output.result_line is None:
        error = "the executor printed no result"
    if error is not None or output.result_line is None:
        return ExecutorRun(noise=None, clipped_ticks=0, printed=output.printed, error=error)
    try:
        returned: object = json.loads(output.result_line)
    except json.JSONDecodeError:
        logger.exception("An executor's result line is not JSON")
        return ExecutorRun(
            noise=None,
            clipped_ticks=0,
            printed=output.printed,
            error="the executor's result could not be read",
        )
    problem = _noise_problem(value=returned, length=len(song))
    if problem is not None:
        return ExecutorRun(noise=None, clipped_ticks=0, printed=output.printed, error=problem)
    values = cast(list[int], returned)
    clipped = [max(-max_volume, min(max_volume, value)) for value in values]
    return ExecutorRun(
        noise=clipped,
        clipped_ticks=sum(value != kept for value, kept in zip(values, clipped, strict=True)),
        printed=output.printed,
        error=None,
    )


def _split_output(stdout: str) -> _Output:
    """What the executor printed itself, and the harness's result line after the marker."""
    marker_at = stdout.rfind(RESULT_MARKER)
    if marker_at == -1:
        return _Output(printed=stdout, result_line=None)
    return _Output(
        printed=stdout[:marker_at],
        result_line=stdout[marker_at + len(RESULT_MARKER) :].strip(),
    )


def _noise_problem(value: object, length: int) -> str | None:
    """Why ``value`` is not a song's worth of noise, or None when it is."""
    if not isinstance(value, list):
        return f"noise(song) must return a list, not {type(value).__name__}"
    items = cast(list[object], value)
    if len(items) != length:
        return f"noise(song) returned {len(items)} values; the song has {length} ticks"
    for tick, item in enumerate(items):
        if isinstance(item, bool) or not isinstance(item, int):
            return f"noise(song)[{tick}] is {item!r}; every value must be a whole number"
    return None
