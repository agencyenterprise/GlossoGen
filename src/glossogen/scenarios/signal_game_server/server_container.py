"""The shared server of signal_game_server: a Linux container run through Docker.

One container per run for the players, built from ``server_image.dockerfile`` the
first time an image for that file's content is missing. It runs with no network, a
process limit and a memory limit, and is removed when the run stops or when this
process dies, since it reads its stdin from a pipe this process holds and exits at the
pipe's end. At start ``/proc`` is mounted so each user sees only its own processes,
which takes ``SYS_ADMIN`` and an unconfined AppArmor profile and leaves Docker's masked
``/proc`` paths open to root; the players are not root. The judge, which is root,
therefore gets a container of its own per round, under Docker's default profile with
no added capability, started from the round-end snapshot and thrown away after.
Both kinds create the player accounts from the scenario's agent ids.

Commands run through ``docker exec`` as a player or as root, each in a fresh bash
under ``timeout``, with the files the command may write capped by ``ulimit``. The
server's player-visible state travels as a tar: ``snapshot`` reads it and ``restore``
writes it back.
"""

import asyncio
import hashlib
import logging
import shutil
import subprocess
import tempfile
from asyncio.subprocess import PIPE, Process
from enum import Enum
from pathlib import Path
from typing import NamedTuple

from glossogen.code_sandbox.stream_capture import read_capped
from glossogen.scenarios.signal_game_server.server_snapshot import (
    ServerSnapshot,
    home_of,
    parse_tar,
    snapshot_roots,
    to_tar,
    user_id_of,
)

logger = logging.getLogger(__name__)

IMAGE_REPOSITORY = "glossogen-signal-server"
DOCKERFILE = Path(__file__).parent / "server_image.dockerfile"
CONTAINER_LABEL = "glossogen.signal_game_server.server"
CONTAINER_MEMORY = "256m"
CONTAINER_PIDS_LIMIT = 256
FILE_SIZE_ULIMIT_BLOCKS = 16
"""``ulimit -f`` for a player's command, in 512-byte blocks: 8 KiB, past any file the quota
lets a player keep, so a command cannot fill the container before the quota is checked."""
EXEC_GRACE_SECONDS = 5.0
"""Added to a command's timeout for the ``docker exec`` client to return after the
command was killed inside."""
KILLED_EXIT_STATUS = 137
OTHER_WRITABLE_DIRS = ("/var/tmp", "/run/lock", "/dev/shm")
"""Directories the image leaves world-writable besides ``/tmp``. Closed at start, so the
snapshot roots are the only places a player can write."""
CLOSE_OTHER_WRITABLE_DIRS = f"chmod 755 {' '.join(OTHER_WRITABLE_DIRS)}"
HIDE_OTHER_PROCESSES = "mount -t proc -o hidepid=2 proc /proc"
"""Run as root at start, so a player sees only its own processes in ``ps`` and ``/proc``:
the partner's command lines are not a channel. Mounting needs ``SYS_ADMIN`` and an
AppArmor profile that allows it, which the container is given; ``no-new-privileges``
keeps a player from gaining the capability through a setuid binary."""


class ContainerRole(str, Enum):
    """Whom a container serves: the players for a run, or the judge for one round."""

    PLAYERS = "players"
    JUDGE = "judge"


class ExecOutput(NamedTuple):
    """What one command printed and how it ended."""

    stdout: str
    stderr: str
    exit_status: int
    timed_out: bool


def _docker() -> str:
    """The ``docker`` executable, or the reason there is none."""
    found = shutil.which("docker")
    if found is None:
        raise RuntimeError("signal_game_server needs Docker: no `docker` executable is on PATH")
    return found


async def _run_docker(*arguments: str, stdin: bytes | None) -> ExecOutput:
    """Run one ``docker`` client command to completion and return its output."""
    process = await asyncio.create_subprocess_exec(
        _docker(), *arguments, stdin=PIPE, stdout=PIPE, stderr=PIPE
    )
    stdout, stderr = await process.communicate(input=stdin)
    assert process.returncode is not None
    return ExecOutput(
        stdout=stdout.decode("utf-8", errors="replace"),
        stderr=stderr.decode("utf-8", errors="replace"),
        exit_status=process.returncode,
        timed_out=False,
    )


async def _require_ok(*arguments: str, stdin: bytes | None) -> ExecOutput:
    output = await _run_docker(*arguments, stdin=stdin)
    if output.exit_status != 0:
        raise RuntimeError(
            f"docker {' '.join(arguments[:2])} failed with status {output.exit_status}: "
            f"{output.stderr.strip()}"
        )
    return output


def image_tag() -> str:
    """The image for the Dockerfile as it is now: its repository plus a hash of the file."""
    digest = hashlib.sha256(DOCKERFILE.read_bytes()).hexdigest()[:12]
    return f"{IMAGE_REPOSITORY}:{digest}"


async def ensure_image() -> str:
    """Build the server image when no image for the current Dockerfile exists; return its tag."""
    tag = image_tag()
    present = await _run_docker("image", "inspect", tag, stdin=None)
    if present.exit_status == 0:
        return tag
    logger.info("Building the signal_game_server image %s", tag)
    context = Path(tempfile.mkdtemp(prefix="glossogen-signal-image-"))
    try:
        await _require_ok(
            "build", "--quiet", "-t", tag, "-f", str(DOCKERFILE), str(context), stdin=None
        )
    finally:
        shutil.rmtree(context, ignore_errors=True)
    return tag


class ServerContainer:
    """One run's server. ``start`` brings it up; ``stop`` removes it."""

    def __init__(self, users: tuple[str, ...], name: str, role: ContainerRole) -> None:
        self.users = users
        self.name = name
        self.role = role
        self._holder: Process | None = None

    async def start(self) -> None:
        """Build the image if needed, run the container, and set it up.

        A players' container also hides other users' processes and closes the
        directories outside the snapshot roots; a judge's runs under Docker's defaults.
        A container that fails to start or to set up is removed before the error is
        raised.
        """
        tag = await ensure_image()
        self._holder = await asyncio.create_subprocess_exec(
            _docker(),
            "run",
            "--interactive",
            "--rm",
            "--network",
            "none",
            "--memory",
            CONTAINER_MEMORY,
            "--pids-limit",
            str(CONTAINER_PIDS_LIMIT),
            *self._security_flags(),
            "--label",
            CONTAINER_LABEL,
            "--name",
            self.name,
            tag,
            stdin=PIPE,
            stdout=PIPE,
            stderr=PIPE,
        )
        try:
            await self._wait_until_running()
            await self._set_up()
        except Exception:
            logger.exception("Removing the server container %s, which failed to start", self.name)
            await self.stop()
            raise

    async def _set_up(self) -> None:
        """Create the player accounts, and in a players' container hide other users'
        processes and close the directories outside the snapshot roots."""
        accounts = " && ".join(
            f"groupadd -g {user_id_of(user=user, users=self.users)} {user} && "
            f"useradd -m -u {user_id_of(user=user, users=self.users)} -g {user} -s /bin/bash {user}"
            f" && chmod 755 {home_of(user=user)}"
            for user in self.users
        )
        steps = [accounts]
        if self.role is ContainerRole.PLAYERS:
            steps = [HIDE_OTHER_PROCESSES, CLOSE_OTHER_WRITABLE_DIRS, accounts]
        setup = await self.exec_as_root(command=" && ".join(steps), timeout_s=30, output_bytes=4096)
        if setup.exit_status != 0:
            raise RuntimeError(f"setting up the server container failed: {setup.stderr.strip()}")

    def _security_flags(self) -> list[str]:
        """What the players' container needs for the ``/proc`` mount; nothing for the judge's."""
        if self.role is ContainerRole.JUDGE:
            return []
        return [
            "--cap-add",
            "SYS_ADMIN",
            "--security-opt",
            "no-new-privileges",
            "--security-opt",
            "apparmor=unconfined",
        ]

    async def _wait_until_running(self) -> None:
        assert self._holder is not None
        for _ in range(100):
            if self._holder.returncode is not None:
                stderr = b""
                if self._holder.stderr is not None:
                    stderr = await self._holder.stderr.read()
                raise RuntimeError(
                    f"the server container exited at start: {stderr.decode(errors='replace')}"
                )
            state = await _run_docker(
                "inspect", "--format", "{{.State.Running}}", self.name, stdin=None
            )
            if state.exit_status == 0 and state.stdout.strip() == "true":
                return
            await asyncio.sleep(0.1)
        raise RuntimeError(f"the server container {self.name} did not start")

    def stop_now(self) -> None:
        """Remove the container without waiting: closes the stdin it reads, and removes it."""
        holder = self._holder
        if holder is None:
            return
        self._holder = None
        if holder.stdin is not None:
            holder.stdin.close()
        subprocess.run([_docker(), "rm", "-f", self.name], capture_output=True, check=False)

    async def stop(self) -> None:
        """Remove the container and wait for it to be gone."""
        holder = self._holder
        if holder is None:
            return
        self._holder = None
        if holder.stdin is not None:
            holder.stdin.close()
        await _run_docker("rm", "-f", self.name, stdin=None)
        await holder.wait()

    async def exec_as(
        self, user: str, command: str, timeout_s: float, output_bytes: int
    ) -> ExecOutput:
        """Run ``command`` as ``user`` in a fresh bash in its home, killed after ``timeout_s``.

        stdout and stderr are each kept up to ``output_bytes``. A command the
        timeout killed, or that ``kill_user_processes`` killed, comes back with
        ``exit_status`` 137. Whatever the line left running is killed when it returns,
        so nothing of a line outlives it.
        """
        home = home_of(user=user)
        process = await asyncio.create_subprocess_exec(
            _docker(),
            "exec",
            "--user",
            user,
            "--workdir",
            home,
            "--env",
            f"HOME={home}",
            "--env",
            f"USER={user}",
            "--env",
            f"LOGNAME={user}",
            self.name,
            "bash",
            "-c",
            _player_command_line(command=command, timeout_s=timeout_s),
            stdin=PIPE,
            stdout=PIPE,
            stderr=PIPE,
        )
        assert process.stdin is not None
        assert process.stdout is not None
        assert process.stderr is not None
        process.stdin.close()
        stdout_task = asyncio.ensure_future(read_capped(stream=process.stdout, limit=output_bytes))
        stderr_task = asyncio.ensure_future(read_capped(stream=process.stderr, limit=output_bytes))
        timed_out = False
        try:
            async with asyncio.timeout(timeout_s + EXEC_GRACE_SECONDS):
                await process.wait()
        except TimeoutError:
            timed_out = True
            await self.kill_user_processes(user=user)
            process.kill()
            await process.wait()
        stdout, stderr = await asyncio.gather(stdout_task, stderr_task)
        await self.kill_user_processes(user=user)
        assert process.returncode is not None
        return ExecOutput(
            stdout=stdout.kept.decode("utf-8", errors="replace"),
            stderr=stderr.kept.decode("utf-8", errors="replace"),
            exit_status=process.returncode,
            timed_out=timed_out or process.returncode == KILLED_EXIT_STATUS,
        )

    async def exec_as_root(self, command: str, timeout_s: float, output_bytes: int) -> ExecOutput:
        """Run ``command`` as root, with no file-size cap."""
        process = await asyncio.create_subprocess_exec(
            _docker(),
            "exec",
            "--workdir",
            "/root",
            self.name,
            "timeout",
            "--signal=KILL",
            f"{timeout_s:g}",
            "bash",
            "-c",
            command,
            stdin=PIPE,
            stdout=PIPE,
            stderr=PIPE,
        )
        assert process.stdin is not None
        assert process.stdout is not None
        assert process.stderr is not None
        process.stdin.close()
        stdout_task = asyncio.ensure_future(read_capped(stream=process.stdout, limit=output_bytes))
        stderr_task = asyncio.ensure_future(read_capped(stream=process.stderr, limit=output_bytes))
        await process.wait()
        stdout, stderr = await asyncio.gather(stdout_task, stderr_task)
        assert process.returncode is not None
        return ExecOutput(
            stdout=stdout.kept.decode("utf-8", errors="replace"),
            stderr=stderr.kept.decode("utf-8", errors="replace"),
            exit_status=process.returncode,
            timed_out=process.returncode == KILLED_EXIT_STATUS,
        )

    async def kill_user_processes(self, user: str) -> None:
        """Kill every process ``user`` has in the container; nothing when it has none."""
        await _run_docker("exec", self.name, "pkill", "-KILL", "-u", user, stdin=None)

    async def snapshot(self) -> ServerSnapshot:
        """The player-visible state now: the homes and the shared roots, as root reads them."""
        roots = " ".join(root.lstrip("/") for root in snapshot_roots(users=self.users))
        output = await asyncio.create_subprocess_exec(
            _docker(),
            "exec",
            self.name,
            "tar",
            "-C",
            "/",
            "-cf",
            "-",
            *roots.split(),
            stdout=PIPE,
            stderr=PIPE,
        )
        data, stderr = await output.communicate()
        if output.returncode != 0:
            raise RuntimeError(f"snapshot of {self.name} failed: {stderr.decode(errors='replace')}")
        return parse_tar(data=data, users=self.users)

    async def restore(self, snapshot: ServerSnapshot) -> None:
        """Make the server's player-visible state ``snapshot``: empty the roots, extract the tar."""
        roots = " ".join(snapshot_roots(users=self.users))
        script = f"find {roots} -mindepth 1 -delete && tar -C / -xpf - --same-owner"
        await _require_ok(
            "exec", "--interactive", self.name, "sh", "-c", script, stdin=to_tar(snapshot=snapshot)
        )

    def __repr__(self) -> str:
        return f"ServerContainer({self.name!r})"


def _player_command_line(command: str, timeout_s: float) -> str:
    """``command`` under the file-size cap and the timeout, as the outer bash runs it."""
    return (
        f"ulimit -f {FILE_SIZE_ULIMIT_BLOCKS}; exec timeout --signal=KILL {timeout_s:g} "
        f"bash -c {_single_quoted(command)}"
    )


def _single_quoted(text: str) -> str:
    """``text`` as one single-quoted shell word."""
    return "'" + text.replace("'", "'\"'\"'") + "'"


def container_name(suffix: str) -> str:
    """A container name for one run: the label plus a suffix unique to the process."""
    return f"glossogen-signal-server-{suffix}"
