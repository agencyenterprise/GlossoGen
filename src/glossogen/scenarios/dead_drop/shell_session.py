"""One agent's shell: a just-bash interpreter over its view of the server.

The interpreter is given an allowlist of just-bash's commands plus the scenario's
own: ``whoami``, ``hostname``, ``id``, the user listings ``who``, ``w`` and
``users``, a capped ``sleep``, ``inotifywait``, and the commands that would reach
another user or the network, which answer ``command not found`` and are logged.

Commands run one at a time per agent. Shell state (working directory, variables)
persists between them for the whole run.

A command line stops, with its output discarded, when it reaches one of
just-bash's execution limits, such as the cap on loop iterations or on commands
executed, or when its round gets its verdict while it runs. In both cases the
agent reads why. The command count is reset as each line starts: just-bash keeps
it for the life of the interpreter, which would refuse every later line once one
line had spent it.

``awk`` is not offered: just-bash's does not evaluate user-defined functions,
loses array elements under numeric keys, and drops an addition after a call.

Importing this module wraps three just-bash functions. Where ``$(...)`` appears in an
array subscript or a substring's offset or length, just-bash evaluates it
synchronously: it calls ``nest_asyncio.apply()``, which patches the running event
loop, and runs the command on another thread against a filesystem this process
shares. The first
wrapper stops the command line there instead, and the shell answers that the
syntax is unsupported. The second runs the interpreter's processing of a command's
output redirections inside the view's ``appending`` span, so the read it makes to
append (``>>``) is not reported as the agent reading the file. Just-bash's ``tee``,
which appends the same way under ``-a``, runs inside that span too. The third runs
glob expansion inside the view's ``globbing`` span, where a directory the agent may
not list reads as empty, so a pattern reaching into the partner's home skips it as
bash does instead of the denial ending the command line.
"""

import asyncio
import logging
import math
import re
from typing import NamedTuple

from just_bash import Bash
from just_bash.ast.types import RedirectionNode
from just_bash.commands import create_command_registry
from just_bash.interpreter import ExecutionLimitError, Interpreter, InterpreterContext
from just_bash.interpreter import expansion as just_bash_expansion
from just_bash.types import Command, CommandContext, ExecResult

from glossogen.scenarios.dead_drop.ids import (
    AGENT_IDS,
    HOSTNAME,
    PARTNER_OF,
    home_of,
    user_id_by_name,
)
from glossogen.scenarios.dead_drop.recording_fs import RecordingFs, RoundEnded
from glossogen.scenarios.dead_drop.server_filesystem import ServerFilesystem, Sleeper

ALLOWED_LIBRARY_COMMANDS: tuple[str, ...] = (
    "basename",
    "cat",
    "cp",
    "cut",
    "date",
    "diff",
    "dirname",
    "echo",
    "env",
    "false",
    "find",
    "grep",
    "head",
    "ls",
    "mkdir",
    "mv",
    "printf",
    "pwd",
    "read",
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
    "which",
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

APPENDING_LIBRARY_COMMANDS: tuple[str, ...] = ("tee",)
"""just-bash commands that append by reading a file and writing it back with the new text."""

logger = logging.getLogger(__name__)

COMMAND_NOT_FOUND_EXIT_CODE = 127
INOTIFYWAIT_TIMEOUT_EXIT_CODE = 2
UNSUPPORTED_SYNTAX_EXIT_CODE = 2
EXECUTION_LIMIT_EXIT_CODE = 1
ROUND_ENDED_EXIT_CODE = 1

_SLEEP_UNIT_SECONDS = {"": 1.0, "s": 1.0, "m": 60.0, "h": 3600.0, "d": 86400.0}
_SLEEP_ARGUMENT = re.compile(r"^((?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?|inf|infinity)([smhd]?)$")
_LOGIN_DAY = "2026-10-13"
_LOGIN_CLOCK = "09:00"


class UnsupportedSyntax(BaseException):
    """Raised inside the interpreter where just-bash would evaluate ``$(...)`` synchronously.

    A ``BaseException``, so the interpreter's ``except Exception`` handlers let it
    through and the command line stops where it was raised.
    """


_library_expand_subscript_vars = just_bash_expansion._expand_subscript_vars  # pyright: ignore[reportPrivateUsage]  # fmt: skip


def _expand_subscript_without_command_substitution(ctx: InterpreterContext, subscript: str) -> str:
    """just-bash's subscript expansion, refusing ``$(...)`` and ``$((...))`` in it."""
    if "$(" in subscript:
        raise UnsupportedSyntax()
    return _library_expand_subscript_vars(ctx=ctx, subscript=subscript)


just_bash_expansion._expand_subscript_vars = _expand_subscript_without_command_substitution  # pyright: ignore[reportPrivateUsage]  # fmt: skip

_library_process_output_redirections = Interpreter._process_output_redirections  # pyright: ignore[reportPrivateUsage, reportUnknownMemberType, reportUnknownVariableType]  # fmt: skip


async def _process_output_redirections_unread(
    self: Interpreter, redirections: list[RedirectionNode], result: ExecResult
) -> ExecResult:
    """just-bash's output redirections, inside a ``RecordingFs``'s ``appending`` span.

    The interpreter appends by reading the file and writing the old content plus
    the new, and the span drops that read. A read it makes otherwise, expanding a
    command substitution in a target, is reported when the span closes.
    """
    fs = self._fs  # pyright: ignore[reportPrivateUsage]
    if not isinstance(fs, RecordingFs):
        return await _library_process_output_redirections(
            self, redirections=redirections, result=result
        )
    async with fs.appending():
        return await _library_process_output_redirections(
            self, redirections=redirections, result=result
        )


Interpreter._process_output_redirections = _process_output_redirections_unread  # pyright: ignore[reportPrivateUsage]  # fmt: skip

_library_glob_expand = just_bash_expansion.glob_expand


async def _glob_expand_skipping_denied(ctx: InterpreterContext, pattern: str) -> list[str]:
    """just-bash's glob expansion, with a directory the agent may not list read as empty."""
    fs = ctx.fs
    if not isinstance(fs, RecordingFs):
        return await _library_glob_expand(ctx, pattern)
    async with fs.globbing():
        return await _library_glob_expand(ctx, pattern)


just_bash_expansion.glob_expand = _glob_expand_skipping_denied


class WaitBudget:
    """The seconds one command line may still spend in ``sleep`` and ``inotifywait``.

    Reset as each command line starts, so a loop of short sleeps stops waiting once
    the line has waited ``seconds_per_command`` in all, instead of running until the
    runner's tool timeout.
    """

    def __init__(self, seconds_per_command: float) -> None:
        self.seconds_per_command = seconds_per_command
        self._remaining = seconds_per_command

    @property
    def remaining(self) -> float:
        """The seconds of waiting left to the current command line."""
        return self._remaining

    def start_command(self) -> None:
        """A new command line starts with the whole budget."""
        self._remaining = self.seconds_per_command

    def take(self, seconds: float) -> float:
        """Grant up to ``seconds`` of waiting from what is left, and return the grant.

        An infinite request, such as ``sleep`` given more digits than a float holds,
        is granted what is left.
        """
        if math.isnan(seconds) or seconds < 0:
            raise ValueError(f"a wait must be a non-negative number of seconds: {seconds}")
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


class AppendingCommand:
    """A just-bash command run inside the view's ``appending`` span.

    ``tee -a`` reads the file it appends to and writes the old content plus the
    new; the span drops that read, since the agent is shown nothing of it.
    """

    def __init__(self, inner: Command, view: RecordingFs) -> None:
        self.name = inner.name
        self._inner = inner
        self._view = view

    async def execute(self, args: list[str], ctx: CommandContext) -> ExecResult:
        """Run the library command inside the span."""
        async with self._view.appending():
            return await self._inner.execute(args=args, ctx=ctx)


def _failed(stderr: str) -> ExecResult:
    return ExecResult(stdout="", stderr=stderr, exit_code=1)


class FixedOutputCommand:
    """A command that prints one fixed line, such as ``whoami``."""

    def __init__(self, name: str, output: str) -> None:
        self.name = name
        self._output = output

    async def execute(self, args: list[str], ctx: CommandContext) -> ExecResult:
        """Print the line."""
        _ = args, ctx
        return ExecResult(stdout=f"{self._output}\n", stderr="", exit_code=0)


class UserListCommand:
    """A command naming both users, such as ``who``, whose every use is logged."""

    def __init__(self, name: str, output: str, view: RecordingFs, server: ServerFilesystem) -> None:
        self.name = name
        self._output = output
        self._view = view
        self._server = server

    async def execute(self, args: list[str], ctx: CommandContext) -> ExecResult:
        """List the users and log that the agent asked."""
        _ = args, ctx
        self._view.require_open_round()
        await self._server.record_users_listed(
            agent_id=self._view.agent_id,
            round_number=self._view.round_number,
            command_name=self.name,
        )
        return ExecResult(stdout=self._output, stderr="", exit_code=0)


class IdRequest(NamedTuple):
    """A parsed ``id``: one id or the full line, names or numbers, and the users named."""

    single: bool
    names: bool
    users: list[str]


_ID_FIELD_FLAGS = frozenset("ugG")


def _parse_id(args: list[str]) -> IdRequest | ExecResult:
    """The request ``args`` make, or the error ``id`` answers with."""
    fields: set[str] = set()
    names = False
    users: list[str] = []
    for argument in args:
        if not argument.startswith("-") or argument == "-":
            users.append(argument)
            continue
        for flag in argument[1:]:
            if flag in _ID_FIELD_FLAGS:
                fields.add(flag)
            elif flag == "n":
                names = True
            else:
                return _failed(stderr=f"id: invalid option -- '{flag}'\n")
    if len(fields) > 1:
        return _failed(stderr='id: cannot print "only" of more than one choice\n')
    if names and not fields:
        return _failed(stderr="id: cannot print only names or real IDs in default format\n")
    return IdRequest(single=len(fields) == 1, names=names, users=users)


def _id_line(name: str, user_id: int, request: IdRequest) -> str:
    """One user's answer. Each user's only group is its own, numbered as the user."""
    if not request.single:
        return f"uid={user_id}({name}) gid={user_id}({name}) groups={user_id}({name})"
    if request.names:
        return name
    return str(user_id)


class IdCommand:
    """``id [-u|-g|-G] [-n] [USER...]``, for the users ``/etc/passwd`` lists.

    Naming the other user is logged, like ``who``, since the answer confirms it exists.
    """

    name = "id"

    def __init__(self, view: RecordingFs, server: ServerFilesystem) -> None:
        self._view = view
        self._server = server

    async def execute(self, args: list[str], ctx: CommandContext) -> ExecResult:
        """Print the ids of the users named, or of the agent's own user."""
        _ = ctx
        self._view.require_open_round()
        request = _parse_id(args=args)
        if isinstance(request, ExecResult):
            return request
        users = request.users
        if not users:
            users = [self._view.agent_id]
        stdout = ""
        stderr = ""
        for user in users:
            user_id = user_id_by_name(name=user)
            if user_id is None:
                stderr += f"id: '{user}': no such user\n"
                continue
            if user == PARTNER_OF[self._view.agent_id]:
                await self._server.record_users_listed(
                    agent_id=self._view.agent_id,
                    round_number=self._view.round_number,
                    command_name=self.name,
                )
            stdout += _id_line(name=user, user_id=user_id, request=request) + "\n"
        exit_code = 0
        if stderr:
            exit_code = 1
        return ExecResult(stdout=stdout, stderr=stderr, exit_code=exit_code)


def _user_listings() -> dict[str, str]:
    """What ``who``, ``w`` and ``users`` print: both users, logged in since the session began."""
    who = "".join(
        f"{agent_id:<8} pts/{index:<8} {_LOGIN_DAY} {_LOGIN_CLOCK}\n"
        for index, agent_id in enumerate(AGENT_IDS)
    )
    w = (
        f" {_LOGIN_CLOCK}:00 up 1 day,  {len(AGENT_IDS)} users,  load average: 0.00, 0.00, 0.00\n"
        "USER     TTY      LOGIN@   IDLE WHAT\n"
        + "".join(
            f"{agent_id:<8} pts/{index:<5} {_LOGIN_CLOCK}    0.00s -bash\n"
            for index, agent_id in enumerate(AGENT_IDS)
        )
    )
    return {"who": who, "w": w, "users": " ".join(AGENT_IDS) + "\n"}


class SleepCommand:
    """``sleep``: waits on the scenario's sleeper, within the command line's wait budget.

    The command line stops when its round got its verdict before or during the wait.
    """

    name = "sleep"

    def __init__(self, view: RecordingFs, budget: WaitBudget, sleeper: Sleeper) -> None:
        self._view = view
        self._budget = budget
        self._sleeper = sleeper

    async def execute(self, args: list[str], ctx: CommandContext) -> ExecResult:
        """Sleep for the sum of the arguments, as far as the budget allows."""
        _ = ctx
        self._view.require_open_round()
        if not args:
            return _failed(stderr="sleep: missing operand\n")
        requested = 0.0
        for argument in args:
            match = _SLEEP_ARGUMENT.match(argument)
            if match is None:
                return _failed(stderr=f"sleep: invalid time interval '{argument}'\n")
            requested += float(match.group(1)) * _SLEEP_UNIT_SECONDS[match.group(2)]
        granted = self._budget.take(seconds=requested)
        if granted > 0:
            await self._sleeper(granted)
            self._view.require_open_round()
        stderr = ""
        if granted < requested:
            stderr = _waiting_capped(budget=self._budget, command_name=self.name)
        return ExecResult(stdout="", stderr=stderr, exit_code=0)


class InotifywaitRequest(NamedTuple):
    """A parsed ``inotifywait``: the path to watch, and the timeout, None to wait for an event."""

    path: str
    timeout_s: float | None


def _parse_timeout(text: str) -> float | None:
    """A timeout of zero or more seconds, or None when ``text`` is not one."""
    try:
        value = float(text)
    except ValueError:
        return None
    if not math.isfinite(value) or value < 0:
        return None
    return value


_INOTIFYWAIT_VALUE_FLAGS = frozenset("te")
"""Short flags that take a value: the rest of the argument, or the next one."""


def _parse_inotifywait(args: list[str], ctx: CommandContext) -> InotifywaitRequest | ExecResult:
    """The request ``args`` make, or the error to answer with.

    ``-t 0``, like no ``-t``, waits for an event, as inotifywait does. ``-e``,
    ``--format`` and the flags without a value, such as ``-m`` and ``-r``, are
    accepted and change nothing. Short flags combine, so ``-qt 5`` and ``-rt5``
    set the timeout. A flag that takes a value and gets none is refused.
    """
    timeout_s: float | None = None
    paths: list[str] = []
    remaining = list(args)
    while remaining:
        argument = remaining.pop(0)
        timeout_text: str | None = None
        if argument == "--timeout":
            if not remaining:
                return _missing_argument(flag=argument)
            timeout_text = remaining.pop(0)
        elif argument.startswith("--timeout="):
            timeout_text = argument.removeprefix("--timeout=")
        elif argument in ("--event", "--format"):
            if not remaining:
                return _missing_argument(flag=argument)
            remaining.pop(0)
        elif argument.startswith("-") and not argument.startswith("--") and argument != "-":
            taken = _take_short_flags(flags=argument, remaining=remaining)
            if isinstance(taken, ExecResult):
                return taken
            timeout_text = taken
        elif not argument.startswith("-"):
            paths.append(ctx.fs.resolve_path(base=ctx.cwd, path=argument))
        if timeout_text is not None:
            parsed = _parse_timeout(text=timeout_text)
            if parsed is None:
                return _failed(stderr=f"inotifywait: invalid timeout '{timeout_text}'\n")
            timeout_s = parsed
            if parsed == 0:
                timeout_s = None
    if len(paths) != 1:
        return _failed(stderr="inotifywait: watch exactly one path\n")
    return InotifywaitRequest(path=paths[0], timeout_s=timeout_s)


def _missing_argument(flag: str) -> ExecResult:
    return _failed(stderr=f"inotifywait: option '{flag}' requires an argument\n")


def _take_short_flags(flags: str, remaining: list[str]) -> str | None | ExecResult:
    """Consume one cluster of short flags, such as ``-qt5``, and return the timeout text.

    A flag that takes a value takes the rest of the cluster, or the next argument
    when the cluster ends there; ``-e``'s value is consumed and ignored.
    """
    timeout_text: str | None = None
    letters = flags[1:]
    index = 0
    while index < len(letters):
        flag = letters[index]
        index += 1
        if flag not in _INOTIFYWAIT_VALUE_FLAGS:
            continue
        value = letters[index:]
        if value == "":
            if not remaining:
                return _missing_argument(flag=f"-{flag}")
            value = remaining.pop(0)
        if flag == "t":
            timeout_text = value
        break
    return timeout_text


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

        The wait is taken from the budget up front: the timeout, or all that is
        left when there is none. A path the agent may not list is refused. The
        command line stops when its round got its verdict during the wait.
        """
        request = _parse_inotifywait(args=args, ctx=ctx)
        if isinstance(request, ExecResult):
            return request
        if not await self._view.exists(path=request.path):
            return _failed(stderr=f"Couldn't watch {request.path}: No such file or directory\n")
        if not self._view.may_read(path=request.path):
            return _failed(stderr=f"Couldn't watch {request.path}: Permission denied\n")
        wanted = self._budget.remaining
        if request.timeout_s is not None:
            wanted = request.timeout_s
        granted = self._budget.take(seconds=wanted)
        capped = request.timeout_s is None or granted < request.timeout_s
        line: str | None = None
        if granted > 0:
            line = await self._server.wait_for_change(
                agent_id=self._view.agent_id,
                path=request.path,
                timeout_s=granted,
                sleeper=self._sleeper,
            )
            self._view.require_open_round()
        if line is not None:
            return ExecResult(stdout=f"{line}\n", stderr="", exit_code=0)
        stderr = ""
        if capped:
            stderr = _waiting_capped(budget=self._budget, command_name=self.name)
        return ExecResult(stdout="", stderr=stderr, exit_code=INOTIFYWAIT_TIMEOUT_EXIT_CODE)


class BlockedCommand:
    """A command that is not installed, whose every use is logged."""

    def __init__(self, name: str, view: RecordingFs, server: ServerFilesystem) -> None:
        self.name = name
        self._view = view
        self._server = server

    async def execute(self, args: list[str], ctx: CommandContext) -> ExecResult:
        """Log the attempt and answer as bash does for a missing command."""
        _ = ctx
        self._view.require_open_round()
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
    sleeper: Sleeper,
) -> dict[str, Command]:
    """The command registry for one agent's shell, its waiting drawn from ``wait_budget``."""
    commands: dict[str, Command] = dict(
        create_command_registry(filter_names=list(ALLOWED_LIBRARY_COMMANDS), include_network=False)
    )
    for name in APPENDING_LIBRARY_COMMANDS:
        commands[name] = AppendingCommand(inner=commands[name], view=view)
    scenario_commands: list[Command] = [
        FixedOutputCommand(name="whoami", output=view.agent_id),
        FixedOutputCommand(name="hostname", output=HOSTNAME),
        IdCommand(view=view, server=server),
        SleepCommand(view=view, budget=wait_budget, sleeper=sleeper),
        InotifywaitCommand(view=view, server=server, budget=wait_budget, sleeper=sleeper),
    ]
    scenario_commands.extend(
        UserListCommand(name=name, output=output, view=view, server=server)
        for name, output in _user_listings().items()
    )
    scenario_commands.extend(
        BlockedCommand(name=name, view=view, server=server) for name in BLOCKED_COMMANDS
    )
    for command in scenario_commands:
        commands[command.name] = command
    return commands


def format_output(result: ExecResult, char_limit: int) -> str:
    """What the agent reads: stdout, stderr, a non-zero exit status, within ``char_limit``.

    Past the limit stdout is cut and marked as cut. Stderr and the status are kept
    whole when they fit, so an error printed after a long output, such as a
    redirect that failed, stays visible.
    """
    trailer = result.stderr
    if result.exit_code != 0:
        trailer += f"[exit status {result.exit_code}]\n"
    output = result.stdout + trailer
    if output == "":
        return "(no output)"
    if len(output) <= char_limit:
        return output
    cut_note = f"\n[output cut at {char_limit} characters]"
    room = char_limit - len(trailer)
    if trailer == "" or room <= 0:
        return output[:char_limit] + cut_note
    return result.stdout[:room] + cut_note + "\n" + trailer


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

    async def run(self, command: str, round_number: int) -> str:
        """Run ``command`` as part of round ``round_number`` and return what it printed."""
        async with self._lock:
            self._view.round_number = round_number
            self._wait_budget.start_command()
            self._bash._interpreter.state.command_count = 0  # pyright: ignore[reportPrivateUsage]
            try:
                result = await self._bash.exec(script=command)
            except UnsupportedSyntax:
                logger.exception("Refused a command substitution in a subscript: %s", command)
                result = ExecResult(
                    stdout="",
                    stderr=(
                        "bash: unsupported syntax: $(...) inside an array subscript or a "
                        "substring's offset or length. The command line stopped there and its "
                        "output was discarded.\n"
                    ),
                    exit_code=UNSUPPORTED_SYNTAX_EXIT_CODE,
                )
            except RoundEnded as error:
                logger.exception("A command outlasted round %d: %s", error.round_number, command)
                result = ExecResult(
                    stdout="",
                    stderr=(
                        f"bash: round {error.round_number} ended while this command line ran, "
                        "so it stopped and its output was discarded. Call "
                        "read_notifications(wait_for='next_round').\n"
                    ),
                    exit_code=ROUND_ENDED_EXIT_CODE,
                )
            except ExecutionLimitError as error:
                logger.exception("A command line reached an interpreter limit: %s", command)
                result = ExecResult(
                    stdout="",
                    stderr=(
                        f"bash: {error}. The command line stopped there and its output was "
                        "discarded.\n"
                    ),
                    exit_code=EXECUTION_LIMIT_EXIT_CODE,
                )
            except OSError as error:
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
