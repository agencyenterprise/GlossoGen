"""Runs a Python program a model wrote in a subprocess, apart from this process.

``run_python`` starts a fresh interpreter for each program and returns what it
printed. The child runs with ``-I -S``: no site packages, no current directory on the
import path, no ``PYTHON*`` environment variables, so the program has the standard
library and nothing of this process's packages. Its working directory is a new
temporary directory holding the files the caller passed as inputs, deleted when the
program ends, and its environment names only that directory. Before the program
runs, the child caps its own CPU seconds, the files it may write and the processes it
may start (one, itself, so ``fork`` and ``subprocess`` fail), and on Linux its address
space; macOS refuses the address-space limit, so the memory cap holds only there. A
wall-clock deadline kills the child and everything in its session. Output is kept up
to a byte limit per stream; past it the rest is read and dropped, and the program runs
on.

What this does not do: the child keeps the network and can read the rest of the file
system as the user running the simulation. The boundary protects the simulation
process and the run directory from a program's accidents, not from a program written
to get out.
"""

import asyncio
import os
import shutil
import signal
import sys
import tempfile
from asyncio.subprocess import PIPE, Process
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import NamedTuple

import aiofiles
import aiofiles.os
from pydantic import BaseModel

from glossogen.code_sandbox.stream_capture import read_capped

SANDBOX_FILENAME = "<sandbox>"
"""What a traceback names the program's source."""

_INTERPRETER_FLAGS = ("-I", "-S", "-X", "utf8")

_BOOTSTRAP = f"""
import resource
import sys

cpu_seconds, memory_bytes, file_bytes = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])


def cap(limit, value):
    soft, hard = resource.getrlimit(limit)
    if hard != resource.RLIM_INFINITY:
        value = min(value, hard)
    resource.setrlimit(limit, (value, hard))


cap(resource.RLIMIT_CPU, cpu_seconds)
cap(resource.RLIMIT_FSIZE, file_bytes)
cap(resource.RLIMIT_NPROC, 1)
if sys.platform == "linux":
    cap(resource.RLIMIT_AS, memory_bytes)
source = sys.stdin.read()
sys.argv = [{SANDBOX_FILENAME!r}]
exec(compile(source, {SANDBOX_FILENAME!r}, "exec"), {{"__name__": "__main__"}})
"""
"""Run with ``-c`` in the child: caps the child's own resources, then runs the program
read from stdin. The limits are applied by the child itself, so no ``preexec_fn`` runs
between fork and exec in this process."""


class SandboxLimits(NamedTuple):
    """What one program may spend.

    ``wall_seconds`` is the deadline after which the child is killed. ``cpu_seconds``
    is the child's CPU time, after which the operating system kills it.
    ``memory_bytes`` caps its address space where the operating system enforces that
    limit. ``file_bytes`` caps the size of any file it writes. ``output_bytes`` caps
    what is kept of each of stdout and stderr; the rest is read and dropped.
    """

    wall_seconds: float
    cpu_seconds: int
    memory_bytes: int
    file_bytes: int
    output_bytes: int


class PythonRunResult(BaseModel):
    """What one program did: its output, how it ended, and which limit it met."""

    stdout: str
    stderr: str
    exit_status: int
    timed_out: bool
    output_cut: bool


async def run_python(
    code: str, inputs: Mapping[str, bytes], limits: SandboxLimits
) -> PythonRunResult:
    """Run ``code`` in a fresh interpreter, with ``inputs`` as files in its working directory.

    ``inputs`` maps a relative path to the bytes the file holds; directories on the
    path are created. An absolute path or one containing ``..`` is refused, since
    it would leave the working directory.
    """
    for name in inputs:
        _require_relative(name=name)
    workdir = Path(await asyncio.to_thread(tempfile.mkdtemp, prefix="glossogen-sandbox-"))
    try:
        await _write_inputs(workdir=workdir, inputs=inputs)
        return await _run_in(workdir=workdir, code=code, limits=limits)
    finally:
        await asyncio.to_thread(shutil.rmtree, workdir, True)


def _require_relative(name: str) -> None:
    path = PurePosixPath(name)
    if name == "" or path.is_absolute() or ".." in path.parts:
        raise ValueError(
            f"an input path must be relative and stay in the working directory: {name!r}"
        )


async def _write_inputs(workdir: Path, inputs: Mapping[str, bytes]) -> None:
    for name, content in inputs.items():
        target = workdir / name
        await aiofiles.os.makedirs(target.parent, exist_ok=True)
        async with aiofiles.open(target, mode="wb") as handle:
            await handle.write(content)


def _environment(workdir: Path) -> dict[str, str]:
    """The child's whole environment: its working directory as home and temp, no path."""
    return {
        "HOME": str(workdir),
        "TMPDIR": str(workdir),
        "PATH": "",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
    }


async def _run_in(workdir: Path, code: str, limits: SandboxLimits) -> PythonRunResult:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        *_INTERPRETER_FLAGS,
        "-c",
        _BOOTSTRAP,
        str(limits.cpu_seconds),
        str(limits.memory_bytes),
        str(limits.file_bytes),
        stdin=PIPE,
        stdout=PIPE,
        stderr=PIPE,
        cwd=workdir,
        env=_environment(workdir=workdir),
        start_new_session=True,
    )
    assert process.stdin is not None
    assert process.stdout is not None
    assert process.stderr is not None
    stdout_task = asyncio.ensure_future(
        read_capped(stream=process.stdout, limit=limits.output_bytes)
    )
    stderr_task = asyncio.ensure_future(
        read_capped(stream=process.stderr, limit=limits.output_bytes)
    )
    timed_out = False
    try:
        async with asyncio.timeout(limits.wall_seconds):
            await _feed(process=process, code=code)
            await process.wait()
    except TimeoutError:
        timed_out = True
        _kill_session(process=process)
        await process.wait()
    stdout, stderr = await asyncio.gather(stdout_task, stderr_task)
    assert process.returncode is not None
    return PythonRunResult(
        stdout=stdout.kept.decode("utf-8", errors="replace"),
        stderr=stderr.kept.decode("utf-8", errors="replace"),
        exit_status=process.returncode,
        timed_out=timed_out,
        output_cut=stdout.cut or stderr.cut,
    )


async def _feed(process: Process, code: str) -> None:
    """Hand the program to the child's stdin; a child that died first is left to report why."""
    assert process.stdin is not None
    try:
        process.stdin.write(code.encode("utf-8"))
        await process.stdin.drain()
    except BrokenPipeError, ConnectionResetError:
        return
    finally:
        process.stdin.close()


def _kill_session(process: Process) -> None:
    """Kill the child and every process in its session; nothing when it already ended."""
    if process.returncode is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
