"""The Python sandbox: what a program gets, what it is refused, and how its limits end it."""

import asyncio
import os
import signal
from pathlib import Path

import pytest

from glossogen.code_sandbox import python_runner
from glossogen.code_sandbox.python_runner import SANDBOX_FILENAME, SandboxLimits, run_python

MEMORY_BYTES = 256 * 1024 * 1024
FILE_BYTES = 16 * 1024 * 1024
LIMITS = SandboxLimits(
    wall_seconds=20,
    cpu_seconds=5,
    memory_bytes=MEMORY_BYTES,
    file_bytes=FILE_BYTES,
    output_bytes=4000,
)


async def test_a_binary_input_arrives_byte_for_byte() -> None:
    result = await run_python(
        code="print(list(open('b.bin', 'rb').read()))",
        inputs={"b.bin": bytes([0xFF, 0x00, 0xC3, 0xFF])},
        limits=LIMITS,
    )
    assert result.stdout == "[255, 0, 195, 255]\n"


async def test_a_program_reads_its_inputs_and_prints() -> None:
    result = await run_python(
        code="import json\nprint(open('data/x').read(), json.loads(open('m.json').read())['n'])",
        inputs={"data/x": b"1011", "m.json": b'{"n": 7}'},
        limits=LIMITS,
    )
    assert (result.stdout, result.stderr, result.exit_status) == ("1011 7\n", "", 0)
    assert not result.timed_out
    assert not result.output_cut


async def test_an_exception_names_the_sandbox_and_fails() -> None:
    result = await run_python(code="raise ValueError('no')", inputs={}, limits=LIMITS)
    assert result.exit_status == 1
    assert f'File "{SANDBOX_FILENAME}", line 1' in result.stderr
    assert result.stderr.rstrip().endswith("ValueError: no")


async def test_this_processs_packages_are_not_importable() -> None:
    result = await run_python(code="import pydantic", inputs={}, limits=LIMITS)
    assert "ModuleNotFoundError: No module named 'pydantic'" in result.stderr


async def test_starting_a_process_is_refused() -> None:
    code = (
        "import subprocess\n"
        "try:\n"
        "    subprocess.run(['true'])\n"
        "except OSError:\n"
        "    print('refused')\n"
    )
    result = await run_python(code=code, inputs={}, limits=LIMITS)
    assert result.stdout == "refused\n"


async def test_output_past_the_limit_is_cut_and_the_program_runs_on() -> None:
    result = await run_python(
        code="import sys\nsys.stdout.write('x' * 5000)\nsys.stderr.write('after')\n",
        inputs={},
        limits=LIMITS,
    )
    assert result.output_cut
    assert result.stdout == "x" * LIMITS.output_bytes
    assert (result.stderr, result.exit_status) == ("after", 0)
    assert not result.timed_out


async def test_a_program_past_the_deadline_is_killed_keeping_what_it_printed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The test decides when the deadline falls: once the program has printed and marked
    a file, rather than after a span of wall-clock time."""
    ready = tmp_path / "ready"

    async def deadline_once_ready(task: asyncio.Future[None], seconds: float) -> bool:
        _ = seconds
        while not ready.exists():
            await asyncio.sleep(0.01)
        return task.done()

    monkeypatch.setattr(python_runner, "_finishes_within", deadline_once_ready)
    result = await run_python(
        code=(
            "import time\nprint('before', flush=True)\n"
            f"open({str(ready)!r}, 'w').close()\ntime.sleep(600)\n"
        ),
        inputs={},
        limits=LIMITS,
    )
    assert result.timed_out
    assert result.stdout == "before\n"
    assert result.exit_status == -signal.SIGKILL


async def test_cancelling_the_call_kills_the_program(tmp_path: Path) -> None:
    ready = tmp_path / "ready"
    call = asyncio.ensure_future(
        run_python(
            code=(
                "import os, time\n"
                f"open({str(ready)!r}, 'w').write(str(os.getpid()))\ntime.sleep(600)\n"
            ),
            inputs={},
            limits=LIMITS,
        )
    )
    while not ready.exists() or ready.read_text() == "":
        await asyncio.sleep(0.01)
    pid = int(ready.read_text())
    call.cancel()
    with pytest.raises(asyncio.CancelledError):
        await call
    while _alive(pid=pid):
        await asyncio.sleep(0.01)


def _alive(pid: int) -> bool:
    """Whether a process with ``pid`` exists and has not been reaped."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


async def test_a_program_past_its_cpu_seconds_is_killed() -> None:
    """The operating system's CPU limit ends the program, which no test clock can drive,
    so this one spends a CPU second. The wall deadline is sixty times longer, so it does
    not fall first on a loaded machine."""
    result = await run_python(
        code="while True:\n    pass\n",
        inputs={},
        limits=SandboxLimits(
            wall_seconds=60,
            cpu_seconds=1,
            memory_bytes=MEMORY_BYTES,
            file_bytes=FILE_BYTES,
            output_bytes=4000,
        ),
    )
    assert not result.timed_out
    assert result.exit_status == -signal.SIGXCPU


async def test_a_file_past_the_size_limit_is_refused() -> None:
    result = await run_python(
        code="open('big', 'w').write('x' * 2_000_000)",
        inputs={},
        limits=SandboxLimits(
            wall_seconds=20,
            cpu_seconds=5,
            memory_bytes=MEMORY_BYTES,
            file_bytes=1_000_000,
            output_bytes=4000,
        ),
    )
    assert "File too large" in result.stderr


@pytest.mark.parametrize("name", ["/etc/x", "../x", "a/../../x", ""])
async def test_an_input_outside_the_working_directory_is_refused(name: str) -> None:
    with pytest.raises(ValueError, match="relative"):
        await run_python(code="", inputs={name: b""}, limits=LIMITS)
