"""One agent's shell: a just-bash interpreter over its view of the server.

The interpreter is given an allowlist of just-bash's commands plus the scenario's
own: ``whoami``, ``hostname``, ``who``, a capped ``sleep``, ``inotifywait`` when the
run offers it, and the commands that would reach another user or the network,
which answer ``command not found`` and are logged.

Commands run one at a time per agent. Shell state (working directory, variables)
persists between them until ``restart``.
"""

import asyncio
import logging
import re

from just_bash import Bash
from just_bash.commands import create_command_registry
from just_bash.types import Command, CommandContext, ExecResult

from glossogen.scenarios.dead_drop.ids import AGENT_IDS, HOSTNAME, home_of
from glossogen.scenarios.dead_drop.recording_fs import RecordingFs
from glossogen.scenarios.dead_drop.server_filesystem import ServerFilesystem, Sleeper

ALLOWED_LIBRARY_COMMANDS: tuple[str, ...] = (
    "awk",
    "basename",
    "cat",
    "cp",
    "cut",
    "date",
    "diff",
    "dirname",
    "echo",
    "find",
    "grep",
    "head",
    "ls",
    "mkdir",
    "mv",
    "printf",
    "pwd",
    "rm",
    "rmdir",
    "sed",
    "seq",
    "sort",
    "stat",
    "tail",
    "tee",
    "touch",
    "tr",
    "tree",
    "true",
    "uniq",
    "wc",
    "xargs",
)
"""just-bash commands an agent may run. Anything else answers ``command not found``."""

BLOCKED_COMMANDS: tuple[str, ...] = (
    "curl",
    "ftp",
    "mail",
    "mailx",
    "mesg",
    "nc",
    "scp",
    "sendmail",
    "ssh",
    "talk",
    "telnet",
    "wall",
    "wget",
    "write",
)
"""Commands that would reach another user or the network: not installed, and logged."""

logger = logging.getLogger(__name__)

_ESCAPED_FILESYSTEM_ERRORS = (
    PermissionError,
    FileNotFoundError,
    FileExistsError,
    IsADirectoryError,
    NotADirectoryError,
)

COMMAND_NOT_FOUND_EXIT_CODE = 127
INOTIFYWAIT_TIMEOUT_EXIT_CODE = 2
UNSUPPORTED_SYNTAX_EXIT_CODE = 2

_SUBSCRIPT_COMMAND_SUBSTITUTION = re.compile(
    r"(?<![A-Za-z0-9_$])[A-Za-z_][A-Za-z0-9_]*\[[^\]]*\$\("
)
"""``name[ ... $(`` : command substitution inside an array subscript.

just-bash evaluates that by patching the running event loop and running the
command on another thread, against a filesystem this process shares, so the
shell refuses it before the interpreter sees it.
"""

_SLEEP_UNIT_SECONDS = {"": 1.0, "s": 1.0, "m": 60.0, "h": 3600.0, "d": 86400.0}
_SLEEP_ARGUMENT = re.compile(r"^(\d+(?:\.\d+)?)([smhd]?)$")
_LOGIN_TIME = "2026-10-13 09:00"


class WaitBudget:
    """The seconds one command line may still spend in ``sleep`` and ``inotifywait``.

    Reset as each command line starts, so a loop of short sleeps stops waiting once
    the line has waited ``seconds_per_command`` in all, instead of running until the
    runner's tool timeout.
    """

    def __init__(self, seconds_per_command: float) -> None:
        self.seconds_per_command = seconds_per_command
        self._remaining = seconds_per_command

    def start_command(self) -> None:
        """A new command line starts with the whole budget."""
        self._remaining = self.seconds_per_command

    def take(self, seconds: float) -> float:
        """Grant up to ``seconds`` of waiting from what is left, and return the grant."""
        granted = min(seconds, self._remaining)
        self._remaining -= granted
        return granted


def _waiting_capped(budget: WaitBudget, command_name: str) -> str:
    return (
        f"{command_name}: waiting is capped at {budget.seconds_per_command:g} seconds "
        "per command line\n"
    )


def _not_found(name: str) -> ExecResult:
    return ExecResult(
        stdout="",
        stderr=f"bash: {name}: command not found\n",
        exit_code=COMMAND_NOT_FOUND_EXIT_CODE,
    )


class FixedOutputCommand:
    """A command that prints one fixed line, such as ``whoami``."""

    def __init__(self, name: str, output: str) -> None:
        self.name = name
        self._output = output

    async def execute(self, args: list[str], ctx: CommandContext) -> ExecResult:
        """Print the line."""
        _ = args, ctx
        return ExecResult(stdout=f"{self._output}\n", stderr="", exit_code=0)


class WhoCommand:
    """``who``: both users, logged in on the server."""

    name = "who"

    def __init__(self, view: RecordingFs, server: ServerFilesystem) -> None:
        self._view = view
        self._server = server

    async def execute(self, args: list[str], ctx: CommandContext) -> ExecResult:
        """List both users and log that the agent asked."""
        _ = args, ctx
        await self._server.record_users_listed(
            agent_id=self._view.agent_id, round_number=self._view.round_number
        )
        lines = [
            f"{agent_id:<8} pts/{index:<8} {_LOGIN_TIME}"
            for index, agent_id in enumerate(AGENT_IDS)
        ]
        return ExecResult(stdout="\n".join(lines) + "\n", stderr="", exit_code=0)


class SleepCommand:
    """``sleep``: waits on the scenario's sleeper, within the command line's wait budget."""

    name = "sleep"

    def __init__(self, budget: WaitBudget, sleeper: Sleeper) -> None:
        self._budget = budget
        self._sleeper = sleeper

    async def execute(self, args: list[str], ctx: CommandContext) -> ExecResult:
        """Sleep for the sum of the arguments, as far as the budget allows."""
        _ = ctx
        if not args:
            return ExecResult(stdout="", stderr="sleep: missing operand\n", exit_code=1)
        requested = 0.0
        for argument in args:
            match = _SLEEP_ARGUMENT.match(argument)
            if match is None:
                return ExecResult(
                    stdout="", stderr=f"sleep: invalid time interval '{argument}'\n", exit_code=1
                )
            requested += float(match.group(1)) * _SLEEP_UNIT_SECONDS[match.group(2)]
        granted = self._budget.take(seconds=requested)
        if granted > 0:
            await self._sleeper(granted)
        stderr = ""
        if granted < requested:
            stderr = _waiting_capped(budget=self._budget, command_name=self.name)
        return ExecResult(stdout="", stderr=stderr, exit_code=0)


class InotifywaitCommand:
    """``inotifywait [-t seconds] path``: returns at the other user's first change below path."""

    name = "inotifywait"

    def __init__(
        self, view: RecordingFs, server: ServerFilesystem, budget: WaitBudget, sleeper: Sleeper
    ) -> None:
        self._view = view
        self._server = server
        self._budget = budget
        self._sleeper = sleeper

    async def execute(self, args: list[str], ctx: CommandContext) -> ExecResult:
        """Wait for a change, or answer exit status 2 at the timeout.

        The whole timeout is taken from the wait budget up front.
        """
        timeout_s = self._budget.seconds_per_command
        paths: list[str] = []
        remaining = list(args)
        while remaining:
            argument = remaining.pop(0)
            if argument in ("-t", "--timeout") and remaining:
                try:
                    timeout_s = float(remaining.pop(0))
                except ValueError:
                    return ExecResult(
                        stdout="", stderr="inotifywait: invalid timeout\n", exit_code=1
                    )
            elif argument in ("-e", "--event", "--format") and remaining:
                remaining.pop(0)
            elif argument.startswith("-"):
                continue
            else:
                paths.append(ctx.fs.resolve_path(base=ctx.cwd, path=argument))
        if len(paths) != 1:
            return ExecResult(
                stdout="", stderr="inotifywait: watch exactly one path\n", exit_code=1
            )
        if not await self._view.exists(path=paths[0]):
            return ExecResult(
                stdout="",
                stderr=f"Couldn't watch {paths[0]}: No such file or directory\n",
                exit_code=1,
            )
        granted = self._budget.take(seconds=timeout_s)
        if granted <= 0:
            return ExecResult(
                stdout="",
                stderr=_waiting_capped(budget=self._budget, command_name=self.name),
                exit_code=INOTIFYWAIT_TIMEOUT_EXIT_CODE,
            )
        line = await self._server.wait_for_change(
            agent_id=self._view.agent_id, path=paths[0], timeout_s=granted, sleeper=self._sleeper
        )
        if line is None:
            return ExecResult(stdout="", stderr="", exit_code=INOTIFYWAIT_TIMEOUT_EXIT_CODE)
        return ExecResult(stdout=f"{line}\n", stderr="", exit_code=0)


class BlockedCommand:
    """A command that is not installed, whose every use is logged."""

    def __init__(self, name: str, view: RecordingFs, server: ServerFilesystem) -> None:
        self.name = name
        self._view = view
        self._server = server

    async def execute(self, args: list[str], ctx: CommandContext) -> ExecResult:
        """Log the attempt and answer as bash does for a missing command."""
        _ = ctx
        await self._server.record_blocked_command(
            agent_id=self._view.agent_id,
            round_number=self._view.round_number,
            command_name=self.name,
            arguments=list(args),
        )
        return _not_found(name=self.name)


def build_commands(
    view: RecordingFs,
    server: ServerFilesystem,
    wait_budget: WaitBudget,
    inotifywait_enabled: bool,
    sleeper: Sleeper,
) -> dict[str, Command]:
    """The command registry for one agent's shell, its waiting drawn from ``wait_budget``."""
    commands: dict[str, Command] = dict(
        create_command_registry(filter_names=list(ALLOWED_LIBRARY_COMMANDS), include_network=False)
    )
    scenario_commands: list[Command] = [
        FixedOutputCommand(name="whoami", output=view.agent_id),
        FixedOutputCommand(name="hostname", output=HOSTNAME),
        WhoCommand(view=view, server=server),
        SleepCommand(budget=wait_budget, sleeper=sleeper),
    ]
    if inotifywait_enabled:
        scenario_commands.append(
            InotifywaitCommand(view=view, server=server, budget=wait_budget, sleeper=sleeper)
        )
    scenario_commands.extend(
        BlockedCommand(name=name, view=view, server=server) for name in BLOCKED_COMMANDS
    )
    for command in scenario_commands:
        commands[command.name] = command
    return commands


def format_output(result: ExecResult, char_limit: int) -> str:
    """What the agent reads: stdout, stderr, a non-zero exit status, cut at ``char_limit``."""
    output = result.stdout + result.stderr
    if result.exit_code != 0:
        output += f"[exit status {result.exit_code}]\n"
    if output == "":
        return "(no output)"
    if len(output) > char_limit:
        return output[:char_limit] + f"\n[output cut at {char_limit} characters]"
    return output


class ShellSession:
    """``view.agent_id``'s shell; ``run`` executes one command line."""

    def __init__(
        self,
        view: RecordingFs,
        commands: dict[str, Command],
        wait_budget: WaitBudget,
        output_char_limit: int,
    ) -> None:
        self._view = view
        self._commands = commands
        self._wait_budget = wait_budget
        self._output_char_limit = output_char_limit
        self._lock = asyncio.Lock()
        self._bash = self._new_bash()

    def restart(self) -> None:
        """A fresh shell in the home directory, as after a filesystem rebuild."""
        self._bash = self._new_bash()

    async def run(self, command: str, round_number: int) -> str:
        """Run ``command`` as part of round ``round_number`` and return what it printed."""
        if _SUBSCRIPT_COMMAND_SUBSTITUTION.search(command) is not None:
            return format_output(
                result=ExecResult(
                    stdout="",
                    stderr="bash: unsupported syntax: command substitution inside an array "
                    "subscript\n",
                    exit_code=UNSUPPORTED_SYNTAX_EXIT_CODE,
                ),
                char_limit=self._output_char_limit,
            )
        async with self._lock:
            self._view.round_number = round_number
            self._wait_budget.start_command()
            try:
                result = await self._bash.exec(script=command)
            except _ESCAPED_FILESYSTEM_ERRORS as error:
                # Some just-bash commands let a filesystem error escape instead of
                # printing it; the agent reads it the way bash would print it.
                logger.exception("A filesystem error escaped the interpreter: %s", command)
                result = ExecResult(stdout="", stderr=f"bash: {error}\n", exit_code=1)
        return format_output(result=result, char_limit=self._output_char_limit)

    def _new_bash(self) -> Bash:
        agent_id = self._view.agent_id
        home = home_of(agent_id=agent_id)
        return Bash(
            fs=self._view,
            cwd=home,
            env={
                "USER": agent_id,
                "LOGNAME": agent_id,
                "HOME": home,
                "HOSTNAME": HOSTNAME,
                "SHELL": "/bin/bash",
                "PATH": "/usr/bin:/bin",
            },
            commands=self._commands,
        )
