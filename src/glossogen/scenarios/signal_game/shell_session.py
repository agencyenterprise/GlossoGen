"""One player's shell under the ``file_system`` medium: a just-bash interpreter on the server.

The interpreter gets an allowlist of just-bash's commands plus this scenario's own:
``ls`` and ``stat`` (which show the server's owners and times), ``whoami``,
``hostname``, ``id``, the user listings ``who``, ``w`` and ``users``, a capped
``sleep``, and ``inotifywait``. Anything else answers ``command not found``.

Commands run one at a time per player. Shell state (working directory, variables)
persists between them for the whole run.

A command line stops, with its output discarded, when it reaches one of just-bash's
execution limits, such as the cap on loop iterations or on commands executed, or
when its round starts closing while it runs. In both cases the player reads why. The
command count is reset as each line starts: just-bash keeps it for the life of the
interpreter, which would refuse every later line once one line had spent it.

``awk`` is not offered: just-bash's does not evaluate user-defined functions, loses
array elements under numeric keys, and drops an addition after a call.

Importing this module wraps three just-bash functions. Where ``$(...)`` appears in an
array subscript or a substring's offset or length, just-bash evaluates it
synchronously: it calls ``nest_asyncio.apply()``, which patches the running event
loop, and runs the command on another thread against a filesystem this process
shares. It reads ``$((expr))`` there the same way, and gets the wrong element. The
first wrapper evaluates the arithmetic itself and stops the command line at a command
substitution, where the shell answers that the syntax is unsupported. The second runs
the interpreter's processing of a command's output redirections inside the view's
``appending`` span, and just-bash's ``tee`` runs there too, since both append by
reading the file first. The third runs glob expansion inside the view's ``globbing``
span, so a pattern reaching into a directory the player may not list skips it.
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
from just_bash.parser.parser import Parser
from just_bash.types import Command, CommandContext, ExecResult

from glossogen.scenarios.signal_game.server_activity import ServerActivity, Sleeper
from glossogen.scenarios.signal_game.server_shell_fs import RoundEnded, ServerShellFs
from glossogen.scenarios.signal_game.shared_server import RefusedPath, home_of, user_id_of
from glossogen.scenarios.signal_game.shell_listing_commands import LsCommand, StatCommand

HOSTNAME = "server"

ALLOWED_LIBRARY_COMMANDS: tuple[str, ...] = (
    "basename",
    "cat",
    "chmod",
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
"""just-bash commands a player may run. Anything else answers ``command not found``."""

APPENDING_LIBRARY_COMMANDS: tuple[str, ...] = ("tee",)
"""just-bash commands that append by reading a file and writing it back with the new text."""

logger = logging.getLogger(__name__)

INOTIFYWAIT_TIMEOUT_EXIT_CODE = 2
UNSUPPORTED_SYNTAX_EXIT_CODE = 2
EXECUTION_LIMIT_EXIT_CODE = 1
ROUND_ENDED_EXIT_CODE = 1

_SLEEP_UNIT_SECONDS = {"": 1.0, "s": 1.0, "m": 60.0, "h": 3600.0, "d": 86400.0}
_SLEEP_ARGUMENT = re.compile(r"^((?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?|inf|infinity)([smhd]?)$")
_LOGIN_DAY = "2026-10-20"
_LOGIN_CLOCK = "09:00"


class UnsupportedSyntax(BaseException):
    """Raised inside the interpreter where just-bash would evaluate ``$(...)`` synchronously.

    A ``BaseException``, so the interpreter's ``except Exception`` handlers let it
    through and the command line stops where it was raised.
    """


_library_expand_subscript_vars = just_bash_expansion._expand_subscript_vars  # pyright: ignore[reportPrivateUsage]  # fmt: skip


def _expand_subscript_without_command_substitution(ctx: InterpreterContext, subscript: str) -> str:
    """just-bash's subscript expansion, with ``$((...))`` evaluated first and ``$(...)`` refused.

    just-bash reads ``$((expr))`` in a subscript as a command substitution of
    ``(expr)``, which it runs synchronously and which gives the wrong element. The
    arithmetic is evaluated here with the library's own evaluator instead.
    """
    evaluated = _evaluate_arithmetic_in_subscript(ctx=ctx, subscript=subscript)
    if "$(" in evaluated:
        raise UnsupportedSyntax()
    return _library_expand_subscript_vars(ctx=ctx, subscript=evaluated)


def _evaluate_arithmetic_in_subscript(ctx: InterpreterContext, subscript: str) -> str:
    """``subscript`` with each ``$((expr))`` replaced by the value of ``expr``."""
    result = ""
    rest = subscript
    while True:
        start = rest.find("$((")
        if start < 0:
            return result + rest
        end = _closing_double_paren(text=rest, start=start + 3)
        if end is None:
            return result + rest
        inner = _evaluate_arithmetic_in_subscript(ctx=ctx, subscript=rest[start + 3 : end])
        value = just_bash_expansion.evaluate_arithmetic_sync(  # pyright: ignore[reportUnknownMemberType]
            ctx, Parser()._parse_arith_comma(inner)  # pyright: ignore[reportPrivateUsage]
        )
        result += rest[:start] + str(value)
        rest = rest[end + 2 :]


def _closing_double_paren(text: str, start: int) -> int | None:
    """The index of the ``))`` closing a ``$((`` whose content starts at ``start``."""
    depth = 0
    index = start
    while index < len(text):
        character = text[index]
        if character == "(":
            depth += 1
        elif character == ")":
            if depth == 0 and text.startswith("))", index):
                return index
            depth -= 1
        index += 1
    return None


just_bash_expansion._expand_subscript_vars = _expand_subscript_without_command_substitution  # pyright: ignore[reportPrivateUsage]  # fmt: skip

_library_process_output_redirections = Interpreter._process_output_redirections  # pyright: ignore[reportPrivateUsage, reportUnknownMemberType, reportUnknownVariableType]  # fmt: skip


async def _process_output_redirections_appending(
    self: Interpreter, redirections: list[RedirectionNode], result: ExecResult
) -> ExecResult:
    """just-bash's output redirections, inside a ``ServerShellFs``'s ``appending`` span."""
    fs = self._fs  # pyright: ignore[reportPrivateUsage]
    if not isinstance(fs, ServerShellFs):
        return await _library_process_output_redirections(
            self, redirections=redirections, result=result
        )
    async with fs.appending():
        return await _library_process_output_redirections(
            self, redirections=redirections, result=result
        )


Interpreter._process_output_redirections = _process_output_redirections_appending  # pyright: ignore[reportPrivateUsage]  # fmt: skip

_library_glob_expand = just_bash_expansion.glob_expand


async def _glob_expand_skipping_denied(ctx: InterpreterContext, pattern: str) -> list[str]:
    """just-bash's glob expansion, with a directory the player may not list read as empty."""
    fs = ctx.fs
    if not isinstance(fs, ServerShellFs):
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
        """Grant up to ``seconds`` of waiting from what is left, and return the grant."""
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


def _failed(stderr: str) -> ExecResult:
    return ExecResult(stdout="", stderr=stderr, exit_code=1)


class AppendingCommand:
    """A just-bash command run inside the view's ``appending`` span, such as ``tee -a``."""

    def __init__(self, inner: Command, view: ServerShellFs) -> None:
        self.name = inner.name
        self._inner = inner
        self._view = view

    async def execute(self, args: list[str], ctx: CommandContext) -> ExecResult:
        """Run the library command inside the span."""
        async with self._view.appending():
            return await self._inner.execute(args=args, ctx=ctx)


class FixedOutputCommand:
    """A command that prints fixed text, such as ``whoami`` or ``users``."""

    def __init__(self, name: str, output: str) -> None:
        self.name = name
        self._output = output

    async def execute(self, args: list[str], ctx: CommandContext) -> ExecResult:
        """Print the text."""
        _ = args, ctx
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


class IdCommand:
    """``id [-u|-g|-G] [-n] [USER...]``, for root and the players, each in a group of its own."""

    name = "id"

    def __init__(self, view: ServerShellFs, users: tuple[str, ...]) -> None:
        self._view = view
        self._users = users

    async def execute(self, args: list[str], ctx: CommandContext) -> ExecResult:
        """Print the ids of the users named, or of the player's own user."""
        _ = ctx
        self._view.require_open_round()
        request = _parse_id(args=args)
        if isinstance(request, ExecResult):
            return request
        named = request.users
        if not named:
            named = [self._view.user]
        stdout = ""
        stderr = ""
        for user in named:
            if user != "root" and user not in self._users:
                stderr += f"id: '{user}': no such user\n"
                continue
            user_id = user_id_of(user=user, users=self._users)
            stdout += _id_line(name=user, user_id=user_id, request=request) + "\n"
        exit_code = 0
        if stderr:
            exit_code = 1
        return ExecResult(stdout=stdout, stderr=stderr, exit_code=exit_code)


def _id_line(name: str, user_id: int, request: IdRequest) -> str:
    """One user's answer."""
    if not request.single:
        return f"uid={user_id}({name}) gid={user_id}({name}) groups={user_id}({name})"
    if request.names:
        return name
    return str(user_id)


def _user_listings(users: tuple[str, ...]) -> dict[str, str]:
    """What ``who``, ``w`` and ``users`` print: both players, logged in since the session began."""
    who = "".join(
        f"{user:<8} pts/{index:<8} {_LOGIN_DAY} {_LOGIN_CLOCK}\n"
        for index, user in enumerate(users)
    )
    w = (
        f" {_LOGIN_CLOCK}:00 up 1 day,  {len(users)} users,  load average: 0.00, 0.00, 0.00\n"
        "USER     TTY      LOGIN@   IDLE WHAT\n"
        + "".join(
            f"{user:<8} pts/{index:<5} {_LOGIN_CLOCK}    0.00s -bash\n"
            for index, user in enumerate(users)
        )
    )
    return {"who": who, "w": w, "users": " ".join(users) + "\n"}


class SleepCommand:
    """``sleep``: waits on the sleeper, within the command line's wait budget."""

    name = "sleep"

    def __init__(self, view: ServerShellFs, budget: WaitBudget, sleeper: Sleeper) -> None:
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
    if re.fullmatch(r"\d+(?:\.\d*)?|\.\d+", text) is None:
        return None
    return float(text)


_INOTIFYWAIT_VALUE_FLAGS = frozenset("te")
"""Short flags that take a value: the rest of the argument, or the next one."""


def _parse_inotifywait(args: list[str], ctx: CommandContext) -> InotifywaitRequest | ExecResult:
    """The request ``args`` make, or the error to answer with.

    ``-t 0``, like no ``-t``, waits for an event, as inotifywait does. ``-e``,
    ``--format`` and the flags without a value, such as ``-m`` and ``-r``, are
    accepted and change nothing. Short flags combine, so ``-qt 5`` and ``-rt5`` set
    the timeout. A flag that takes a value and gets none is refused.
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
    """Consume one cluster of short flags, such as ``-qt5``, and return the timeout text."""
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
    """``inotifywait [-t seconds] path``: returns at the partner's first change below path."""

    name = "inotifywait"

    def __init__(
        self, view: ServerShellFs, activity: ServerActivity, budget: WaitBudget, sleeper: Sleeper
    ) -> None:
        self._view = view
        self._activity = activity
        self._budget = budget
        self._sleeper = sleeper

    async def execute(self, args: list[str], ctx: CommandContext) -> ExecResult:
        """Wait for a change, or answer exit status 2 at the timeout.

        The wait is taken from the budget up front: the timeout, or all that is left
        when there is none. A path the player cannot reach is refused, and so is a
        directory it may not list. The command line stops when its round starts
        closing during the wait.
        """
        request = _parse_inotifywait(args=args, ctx=ctx)
        if isinstance(request, ExecResult):
            return request
        looked = self._view.look(path=request.path)
        if isinstance(looked, str):
            return _failed(stderr=f"Couldn't watch {request.path}: {looked}\n")
        if not self._view.may_list(path=request.path) and await self._view.is_directory(
            path=request.path
        ):
            return _failed(stderr=f"Couldn't watch {request.path}: Permission denied\n")
        wanted = self._budget.remaining
        if request.timeout_s is not None:
            wanted = request.timeout_s
        granted = self._budget.take(seconds=wanted)
        capped = request.timeout_s is None or granted < request.timeout_s
        line: str | None = None
        if granted > 0:
            line = await self._activity.wait_for_change(
                agent_id=self._view.user,
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


def build_commands(
    view: ServerShellFs,
    activity: ServerActivity,
    users: tuple[str, ...],
    wait_budget: WaitBudget,
    sleeper: Sleeper,
) -> dict[str, Command]:
    """The command registry for one player's shell, its waiting drawn from ``wait_budget``."""
    commands: dict[str, Command] = dict(
        create_command_registry(filter_names=list(ALLOWED_LIBRARY_COMMANDS), include_network=False)
    )
    for name in APPENDING_LIBRARY_COMMANDS:
        commands[name] = AppendingCommand(inner=commands[name], view=view)
    scenario_commands: list[Command] = [
        LsCommand(),
        StatCommand(users=users),
        FixedOutputCommand(name="whoami", output=f"{view.user}\n"),
        FixedOutputCommand(name="hostname", output=f"{HOSTNAME}\n"),
        IdCommand(view=view, users=users),
        SleepCommand(view=view, budget=wait_budget, sleeper=sleeper),
        InotifywaitCommand(view=view, activity=activity, budget=wait_budget, sleeper=sleeper),
    ]
    scenario_commands.extend(
        FixedOutputCommand(name=name, output=output)
        for name, output in _user_listings(users=users).items()
    )
    for command in scenario_commands:
        commands[command.name] = command
    return commands


def format_output(result: ExecResult, char_limit: int) -> str:
    """What the player reads: stdout, stderr, a non-zero exit status, within ``char_limit``.

    Past the limit stdout is cut and marked as cut. Stderr and the status are kept
    whole when they fit, so an error printed after a long output stays visible.
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


def _escaped(error: OSError) -> str:
    """How bash prints a filesystem error: ``bash: PATH: reason``, or the reason alone."""
    if isinstance(error, RefusedPath):
        return f"bash: {error.path}: {error}\n"
    return f"bash: {error}\n"


class ShellSession:
    """``view.user``'s shell; ``run`` executes one command line."""

    def __init__(
        self,
        view: ServerShellFs,
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
                # printing it; the player reads it the way bash would print it.
                logger.exception("A filesystem error escaped the interpreter: %s", command)
                result = ExecResult(stdout="", stderr=_escaped(error=error), exit_code=1)
        return format_output(result=result, char_limit=self._output_char_limit)

    def _new_bash(self) -> Bash:
        user = self._view.user
        home = home_of(user=user)
        return Bash(
            fs=self._view,
            cwd=home,
            env={
                "USER": user,
                "LOGNAME": user,
                "HOME": home,
                "HOSTNAME": HOSTNAME,
                "SHELL": "/bin/bash",
                "PATH": "/usr/bin:/bin",
            },
            commands=self._commands,
        )
